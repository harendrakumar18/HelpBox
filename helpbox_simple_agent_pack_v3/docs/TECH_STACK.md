# Helpbox — Technology and Dependency Plan

## Updated Tech Stack (Phase 3 & Production Architecture)

| Area | Component | Implementation Detail |
|---|---|---|
| **Runtime** | Python 3.13 | Linux x86_64, active in `.venv` |
| **Web / API** | FastAPI + Uvicorn | Monolith with modular routers and static workspace UI |
| **Database** | PostgreSQL 16 + pgvector 0.8.7 | Pinned Docker container `helpbox-postgres` on port 5432 |
| **ORM / Persistence** | SQLAlchemy 2.0 + psycopg 3 | Relational metadata, `DocumentInventory`, persistent SQL backups |
| **Vector Store** | `langchain-postgres` (`PGVectorStore`) | Production table `helpbox_clinical_vectors` (768 dimensions) |
| **PDF Extraction** | Docling (`docling` & `langchain-docling`) | Layout detection, reading order, headings, paragraphs, and figures |
| **Table Extraction** | Docling TableFormer | Preserves row/col structure, headers, units, captions, and footnotes |
| **OCR Backend** | Selective RapidOCR | Targeted for scanned or non-native text pages; configurable |
| **Fallback PDF Parser** | PyPDFLoader (`pypdf`) | Lightweight validation and fallback tool |
| **Chunking** | Docling `HybridChunker` | Structure-aware chunking (700–900 tokens) preserving section continuity |
| **Primary Embeddings** | `NeuML/bioclinical-modernbert-base-embeddings` | 768 dimensions, clinical/biomedical retrieval focus (~600 MB) |
| **Fallback Embeddings** | `NeuML/pubmedbert-base-embeddings-8M` | Static CPU-friendly baseline (~31 MB) if resource-constrained |
| **Dev LLM (Default)** | Local Qwen 3.5 2B via Ollama | `qwen3.5:2b-q4_K_M` (~1.9 GB) with conservative 4K context; zero API costs |
| **Cloud LLM (Optional)** | Gemini 3.8 Flash API | User-configured optional provider for approved data flows only |
| **No Paid OpenAI** | Zero OpenAI Cloud Billing | No OpenAI account or paid OpenAI cloud API is used |

---

## Model Dimensions and Compatibility

- `VectorVerificationRecord`: 384 dimensions (retained for database regression tests).
- `helpbox_clinical_vectors`: **768 dimensions** (matches `bioclinical-modernbert-base-embeddings`).
- Programmatic dimension validation: vector table dimension is determined dynamically from the active embedding model configuration.
