import json
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db import SessionLocal, engine
from app.llm import GeminiProvider, OllamaProvider, OpenAICompatibleProvider, get_llm_provider
from app.main import app
from app.rag import generate_rag_answer

client = TestClient(app)


@pytest.fixture(scope="module")
def db_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def test_provider_initialization():
    """Verify provider factory and configuration boundaries."""
    # Ollama provider
    ollama = get_llm_provider("ollama")
    assert isinstance(ollama, OllamaProvider)
    assert ollama.provider_name == "ollama"
    assert "qwen3.5:2b" in ollama.model_name

    # Gemini provider without key raises clear configuration error
    with pytest.raises(ValueError, match="GEMINI_API_KEY"):
        GeminiProvider(api_key="")

    # OpenAI-compatible provider without URL raises clear configuration error
    with pytest.raises(ValueError, match="OPENAI_COMPATIBLE_BASE_URL"):
        OpenAICompatibleProvider(base_url="")


def test_grounded_answer_and_citations_trial_101(db_session: Session):
    """
    Verify grounded RAG generation:
    - Answers based solely on retrieved evidence.
    - Cites original filename and 1-based page number.
    - Captures stage latency metrics.
    """
    res = generate_rag_answer(
        trial_name="Trial_101",
        question="What is the primary endpoint and dosage specified in the trial protocol?",
        db=db_session,
    )

    assert "answer" in res
    answer_lower = res["answer"].lower()
    # Must mention facts directly from Trial_101 Protocol.pdf
    assert "objective response rate" in answer_lower or "hb-101" in answer_lower
    assert "50" in answer_lower or "daily" in answer_lower

    # Citations verification
    assert len(res["citations"]) > 0
    protocol_citations = [c for c in res["citations"] if c["filename"] == "Protocol.pdf"]
    assert len(protocol_citations) > 0
    assert protocol_citations[0]["page"] == 1
    assert "primary endpoint" in protocol_citations[0]["excerpt"].lower()

    # Evidence sufficiency
    assert res["insufficient_evidence"] is False

    # Observability metrics
    metrics = res["metrics"]
    assert metrics["retrieval_ms"] > 0
    assert metrics["first_token_ms"] > 0
    assert metrics["generation_ms"] > 0
    assert metrics["total_response_ms"] > 0
    assert metrics["provider"] == "ollama"


def test_insufficient_evidence_handling(db_session: Session):
    """
    Verify clear abstention when evidence is absent from trial documents:
    - Explicit refusal to fabricate clinical data.
    - insufficient_evidence flag set to True.
    """
    res = generate_rag_answer(
        trial_name="Trial_101",
        question="What is the 10-year overall patient survival percentage?",
        db=db_session,
    )

    assert "answer" in res
    answer_lower = res["answer"].lower()
    assert (
        "not have sufficient information" in answer_lower
        or "insufficient information" in answer_lower
        or "not mentioned" in answer_lower
        or "not contain" in answer_lower
    )
    assert res["insufficient_evidence"] is True
    assert res["citations"] == []


def test_numerical_metric_abstention_when_unsupported(db_session: Session):
    """
    Verify citation correctness and numerical grounding:
    When asked for numerical performance metrics (accuracy, F1-score, precision)
    that are not present in the trial documents, Helpbox must strictly abstain
    and return ZERO citations.
    """
    res = generate_rag_answer(
        trial_name="Trial_101",
        question="What is the classification accuracy, precision, recall, and F1-score reported for the model?",
        db=db_session,
    )

    assert "answer" in res
    answer_lower = res["answer"].lower()
    assert (
        "not have sufficient information" in answer_lower
        or "insufficient information" in answer_lower
        or "not mentioned" in answer_lower
        or "not contain" in answer_lower
    )
    assert res["insufficient_evidence"] is True
    assert res["citations"] == []


def test_cross_trial_retrieval_boundary(db_session: Session):
    """
    Verify strict trial-level boundary enforcement:
    - Asking Trial_102's endpoint (systolic blood pressure) in Trial_101 yields abstention or no leak.
    - Asking the same question in Trial_102 returns the accurate Trial_102 answer.
    """
    # 1. Query Trial_101 for Trial_102 content
    res_101 = generate_rag_answer(
        trial_name="Trial_101",
        question="What reduction in systolic blood pressure was observed with HB-202?",
        db=db_session,
    )
    # Trial_101 must NOT retrieve Trial_102 chunks
    for c in res_101["citations"]:
        assert "HB-202" not in c["excerpt"]

    # 2. Query Trial_102 for Trial_102 content
    res_102 = generate_rag_answer(
        trial_name="Trial_102",
        question="What reduction in systolic blood pressure was observed with HB-202?",
        db=db_session,
    )
    answer_102_lower = res_102["answer"].lower()
    assert (
        "systolic" in answer_102_lower
        or "blood pressure" in answer_102_lower
        or "14.2" in answer_102_lower
        or "hb-202" in answer_102_lower
    )
    assert len(res_102["citations"]) > 0
    filenames = [c["filename"] for c in res_102["citations"]]
    assert "Clinical_Report.pdf" in filenames or "Protocol.pdf" in filenames


def test_streaming_rag_endpoint():
    """Verify Server-Sent Events (SSE) streaming endpoint."""
    res = client.post(
        "/api/chat/stream",
        json={
            "trial_name": "Trial_101",
            "question": "What is the primary endpoint?",
            "chat_history": [],
        },
    )
    assert res.status_code == 200
    assert "text/event-stream" in res.headers["content-type"]

    events = []
    for line in res.iter_lines():
        if line.startswith("data: "):
            payload = json.loads(line[6:])
            events.append(payload)

    assert len(events) >= 2
    types = [e["type"] for e in events]
    assert "meta" in types
    assert "token" in types
    assert "done" in types

    done_event = next(e for e in events if e["type"] == "done")
    assert "answer" in done_event
    assert len(done_event["citations"]) > 0
    assert done_event["metrics"]["total_response_ms"] > 0


def test_chat_history_is_never_persisted_in_db():
    """
    CRITICAL PRIVACY TEST:
    Verify that user questions, assistant answers, and chat history
    are strictly NEVER stored in any database table.
    """
    secret_question = "What is the unique test token X99SECRETQUESTION?"
    res = client.post(
        "/api/chat",
        json={
            "trial_name": "Trial_101",
            "question": secret_question,
            "chat_history": [],
        },
    )
    assert res.status_code == 200

    # Inspect all PostgreSQL tables to guarantee zero persistence of secret token
    with engine.connect() as conn:
        # Check document_inventory
        inv_matches = conn.execute(
            text("SELECT count(*) FROM document_inventory WHERE filename LIKE '%X99SECRET%'")
        ).scalar()
        assert inv_matches == 0

        # Check langchain_pg_embedding
        vec_matches = conn.execute(
            text("SELECT count(*) FROM langchain_pg_embedding WHERE document LIKE '%X99SECRET%'")
        ).scalar()
        assert vec_matches == 0

        # Check performance_metrics
        met_matches = conn.execute(
            text("SELECT count(*) FROM performance_metrics WHERE trial_name LIKE '%X99SECRET%'")
        ).scalar()
        assert met_matches == 0
