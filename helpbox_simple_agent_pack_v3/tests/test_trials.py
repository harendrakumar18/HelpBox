import os
import tempfile
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.trials import (
    TrialNotFoundError,
    TrialSecurityError,
    compute_file_sha256,
    list_trial_folders,
    list_trial_pdfs,
    sanitize_and_validate_trial_name,
)


@pytest.fixture
def temp_trials_dir():
    """Create a temporary trials directory structure with synthetic data."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        
        # Valid trials
        t1 = root / "Trial_A"
        t1.mkdir()
        (t1 / "Protocol.pdf").write_bytes(b"%PDF-1.4 Trial A Protocol")
        (t1 / "notes.txt").write_text("Should be ignored because not PDF")
        
        # Nested folder inside trial - should be ignored
        sub = t1 / "Subfolder"
        sub.mkdir()
        (sub / "nested.pdf").write_bytes(b"%PDF-1.4 Nested")
        
        t2 = root / "Trial_B"
        t2.mkdir()
        (t2 / "Clinical_Report.PDF").write_bytes(b"%PDF-1.4 Trial B Report uppercase ext")
        
        # Hidden folder & file at root
        (root / ".gitkeep").write_text("")
        hidden_dir = root / ".hidden_trial"
        hidden_dir.mkdir()
        (hidden_dir / "secret.pdf").write_bytes(b"%PDF-1.4 Hidden")
        
        # File at root (not a trial folder)
        (root / "RootFile.pdf").write_bytes(b"%PDF-1.4 Root")
        
        yield root


def test_list_trial_folders(temp_trials_dir):
    """Test that only direct child directories (excluding hidden ones) are returned."""
    folders = list_trial_folders(temp_trials_dir)
    assert folders == ["Trial_A", "Trial_B"]


def test_sanitize_and_validate_trial_name_success(temp_trials_dir):
    """Test valid trial name resolution."""
    path = sanitize_and_validate_trial_name("Trial_A", temp_trials_dir)
    assert path.is_dir()
    assert path.name == "Trial_A"


def test_sanitize_and_validate_trial_name_traversal_rejection(temp_trials_dir):
    """Test that path traversal attempts are rejected with TrialSecurityError."""
    traversal_payloads = [
        "../",
        "..",
        ".",
        "../../etc",
        "Trial_A/../Trial_B",
        "Trial_A/nested",
        "Trial_A\\nested",
        "/etc/passwd",
        "C:\\Windows",
        "Trial_A\0evil",
    ]
    for payload in traversal_payloads:
        with pytest.raises(TrialSecurityError):
            sanitize_and_validate_trial_name(payload, temp_trials_dir)


def test_sanitize_and_validate_trial_name_not_found(temp_trials_dir):
    """Test non-existent trial raises TrialNotFoundError."""
    with pytest.raises(TrialNotFoundError):
        sanitize_and_validate_trial_name("NonExistentTrial", temp_trials_dir)


def test_symlink_escape_rejection(temp_trials_dir):
    """Test that a symlink pointing outside the trials root is rejected."""
    with tempfile.TemporaryDirectory() as outside_dir:
        outside_path = Path(outside_dir) / "OutsideTrial"
        outside_path.mkdir()
        (outside_path / "leak.pdf").write_bytes(b"%PDF-1.4 leaked")
        
        # Create symlink inside temp_trials_dir pointing outside
        symlink_trial = temp_trials_dir / "SymlinkTrial"
        try:
            symlink_trial.symlink_to(outside_path, target_is_directory=True)
        except OSError:
            pytest.skip("Symlinks not supported in this environment")
            
        with pytest.raises(TrialSecurityError):
            sanitize_and_validate_trial_name("SymlinkTrial", temp_trials_dir)
            
        # list_trial_folders should also safely exclude the symlinked directory
        assert "SymlinkTrial" not in list_trial_folders(temp_trials_dir)


def test_list_trial_pdfs(temp_trials_dir):
    """Test that only direct PDF files are listed and case-insensitivity works."""
    docs_a = list_trial_pdfs("Trial_A", temp_trials_dir, compute_hashes=True)
    assert len(docs_a) == 1
    assert docs_a[0]["filename"] == "Protocol.pdf"
    assert docs_a[0]["relative_path"] == "Protocol.pdf"
    assert docs_a[0]["size_bytes"] == len(b"%PDF-1.4 Trial A Protocol")
    assert docs_a[0]["status"] == "DISCOVERED"
    assert "sha256" in docs_a[0]
    assert len(docs_a[0]["sha256"]) == 64

    # Upper case extension check
    docs_b = list_trial_pdfs("Trial_B", temp_trials_dir, compute_hashes=False)
    assert len(docs_b) == 1
    assert docs_b[0]["filename"] == "Clinical_Report.PDF"


def test_source_pdfs_are_never_modified(temp_trials_dir):
    """Confirm source PDFs retain identical content and mtime after listing/hashing."""
    trial_file = temp_trials_dir / "Trial_A" / "Protocol.pdf"
    original_bytes = trial_file.read_bytes()
    original_mtime = trial_file.stat().st_mtime

    # Run listing and hash calculation
    list_trial_pdfs("Trial_A", temp_trials_dir, compute_hashes=True)

    assert trial_file.read_bytes() == original_bytes
    assert trial_file.stat().st_mtime == original_mtime


# Integration checks with FastAPI TestClient
client = TestClient(app)


def test_api_health():
    res = client.get("/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert data["app"] == "helpbox"


def test_api_index_page():
    res = client.get("/")
    assert res.status_code == 200
    assert "HELPBOX" in res.text
    assert "AI Assistant" in res.text


def test_api_list_trials():
    res = client.get("/api/trials")
    assert res.status_code == 200
    data = res.json()
    assert "trials" in data
    assert "Trial_101" in data["trials"]
    assert "Trial_102" in data["trials"]


def test_api_trial_documents():
    res = client.get("/api/trials/Trial_101/documents")
    assert res.status_code == 200
    data = res.json()
    assert data["trial_name"] == "Trial_101"
    filenames = [d["filename"] for d in data["documents"]]
    assert "Protocol.pdf" in filenames
    assert "Safety_Report.pdf" in filenames


def test_api_trial_status():
    res = client.get("/api/trials/Trial_101/status")
    assert res.status_code == 200
    data = res.json()
    assert data["trial_name"] == "Trial_101"
    assert data["total_documents"] == 2


def test_api_trial_refresh():
    res = client.get("/api/trials/Trial_102/documents")
    assert res.status_code == 200
    data = res.json()
    assert len(data["documents"]) == 2

    # Refresh endpoint computes SHA-256
    refresh_res = client.post("/api/trials/Trial_102/refresh")
    assert refresh_res.status_code == 200
    refreshed_data = refresh_res.json()
    for doc in refreshed_data["documents"]:
        assert doc["sha256"] is not None
        assert len(doc["sha256"]) == 64


def test_api_path_traversal_rejected():
    """Verify that path traversal attempts via API are rejected with 400 or 404."""
    for bad_name in ["..", "../", "..%2F..", "Trial_101/nested"]:
        res = client.get(f"/api/trials/{bad_name}/documents")
        assert res.status_code in [400, 404]


def test_api_chat_in_trial():
    from unittest.mock import patch
    with patch("app.main.generate_rag_answer") as mock_rag:
        mock_rag.return_value = {
            "answer": "Objective response rate at 24 weeks with oral HB-101 at 50mg daily.",
            "citations": [{"id": 1, "filename": "Protocol.pdf", "page": 1, "excerpt": "Primary Endpoint..."}],
            "insufficient_evidence": False,
            "metrics": {
                "retrieval_ms": 45.0,
                "first_token_ms": 280.0,
                "generation_ms": 1100.0,
                "tokens_per_second": 10.5,
                "token_count": 25,
                "total_response_ms": 1425.0,
                "provider": "ollama",
                "model": "qwen3.5:2b-q4_K_M",
            },
        }
        res = client.post(
            "/api/chat",
            json={"trial_name": "Trial_101", "question": "What is the primary endpoint?", "chat_history": []},
        )
        assert res.status_code == 200
        data = res.json()
        assert "objective response rate" in data["answer"].lower() or "hb-101" in data["answer"].lower()
        assert len(data["citations"]) > 0
        assert data["citations"][0]["filename"] == "Protocol.pdf"
        assert data["citations"][0]["page"] == 1
