# Helpbox — Clinical Trial PDF Workspace & Intelligence Assistant

Helpbox is a trial-scoped clinical document question-answering assistant designed for healthcare and clinical research teams. It is **NOT** a Document Management System (DMS). The company already manages original document lifecycles (upload, replace, delete) within its existing .NET/C# enterprise application.

Helpbox operates with **strictly read-only access** to source PDFs in trial folders (`data/trials/<Trial_Name>/`). When a trial is opened or refreshed, Helpbox automatically synchronizes document inventory, indexes new/changed PDFs, immediately purges deleted PDFs and their pgvector chunks from the database, and answers user questions strictly grounded in the active trial's documents with verified 1-based PDF page citations.

---

## 1. Clinical Trial Document Q&A Workflow

```text
data/
└── trials/
    ├── Trial_101/
    │   ├── Protocol.pdf
    │   └── Safety_Report.pdf
    └── Trial_102/
        ├── Protocol.pdf
        └── Clinical_Report.pdf
```

1. **Folder Convention:** Direct child folders under `data/trials/` define individual trial scopes (`Trial_101`, `Trial_102`).
2. **Company Document Ownership:** Original documents are placed in trial folders by the company's .NET system. Helpbox has strictly read-only access and never modifies, moves, renames, or deletes company source PDFs.
3. **Automatic Synchronization:**
   - **New/Changed PDFs:** Detected on scan/refresh; parsed, chunked, and embedded into pgvector.
   - **Company-Deleted PDFs:** Detected during folder scan; associated vector embeddings and chunks are immediately purged from PostgreSQL pgvector, and inventory status is set to `WITHDRAWN` (ensuring deleted content is never cited or retrieved).
4. **Workspace Navigation:** Selecting a trial loads that trial's dedicated workspace with `Overview`, `Documents` (read-only table), and `AI Assistant` tabs. No upload or delete buttons exist in the UI.
5. **Trial-Isolated Scope:** The assistant retrieves evidence *exclusively* from the selected trial's indexed documents. Switching trials immediately clears in-memory conversation history and redirects the retrieval scope.

---

## 2. Actual System Architecture

```text
User Browser (Clinical Workspace UI)
    │
    │ HTTP / JSON (trial_name parameter; read-only endpoints)
    ▼
FastAPI Application (app/main.py)
    ├── Safe Trial & PDF Discovery (app/trials.py)
    │     ├── Direct-child validation & path traversal prevention
    │     └── SHA-256 incremental content hashing
    │
    ├── Database Engine & ORM (app/db.py, app/models.py)
    │     ├── Relational document inventory (document_inventory table)
    │     ├── Deletion sync & pgvector purge on file removal
    │     └── Technical latency tracking (performance_metrics table)
    │
    ├── [Phase 3 - Complete] Document Ingestion & Observability:
    │     Docling PDF Parser + TableFormer + Selective RapidOCR
    │     Docling HybridChunker (700-900 tokens)
    │     BioClinical ModernBERT Embeddings (768 dimensions)
    │     Console & DB Technical Timing Instrumentation
    │
    └── [Phase 5 - Complete] Multi-Provider Answer Generation:
          Local Ollama (Qwen 3.5 2B) [Dev Default, Verified Offline]
          OpenAI-Compatible Private Server [Company VM Adapter]
          Gemini 3.8 Flash [Approved Cloud Provider]
    │
    ▼
PostgreSQL 16 + pgvector 0.8.7 Container (helpbox-postgres)
    ├── document_inventory (Relational status tracking)
    ├── helpbox_clinical_vectors (768-dim production vector store)
    ├── vector_verification (384-dim test table)
    └── performance_metrics (Technical durations & counts)
    │
    ▼
Persistent Storage
    ├── Docker Named Volume: helpbox_postgres_data
    └── Persistent SQL Dumps: data/backups/latest.sql
```

---

## 3. Current Implementation Status

### Completed Features (Phases 1, 2, 3, 4, 5 & 6)

- [x] **FastAPI Backend Foundation:** Core application running on Python 3.13 with modular structure.
- [x] **Safe Trial Discovery & Path Security:** Strict direct-child folder enumeration; rejects path traversal (`..`), directory separators (`/`, `\`), null bytes, and out-of-root symlink escapes.
- [x] **Read-Only PDF Scanning:** Direct PDF listing, metadata extraction (size, timestamps), and SHA-256 content hashing without modifying source files.
- [x] **Clinical Workspace Frontend:** Clean UI following `docs/UI_WORKSPACE_SPEC.md` featuring top bar, left trial sidebar with search, selected-trial workspace, Overview/Documents tabs, and in-trial AI Assistant panel.
- [x] **Conversation Isolation:** Switching trials clears visible chat and resets conversation scope.
- [x] **PostgreSQL 16 + pgvector 0.8.7:** Running via Docker container `helpbox-postgres` on port `5432:5432`.
- [x] **SQLAlchemy 2.0 + psycopg 3 ORM:** Session pooling (`pool_pre_ping=True`) and database connection checks.
- [x] **Relational Document Inventory:** `document_inventory` table created with unique constraint `(trial_name, relative_path)` and versioning.
- [x] **pgvector Vector Operations Verified:** 384-dimensional and 768-dimensional cosine distance similarity queries (`<=>`) verified against live PostgreSQL.
- [x] **Automated Database Backups:** `scripts/backup_db.sh` and `scripts/restore_db.sh` generating SQL dumps to `data/backups/latest.sql`.
- [x] **Automated Test Suite:** 41/41 automated tests passing across 6 test suites (`test_database.py`, `test_trials.py`, `test_ingestion.py`, `test_incremental.py`, `test_rag.py`, `test_sync_scanner.py`).
- [x] **Live Server HTTP Verification:** Verified live running Uvicorn server on `http://127.0.0.1:8000` with streaming SSE and JSON endpoints returning HTTP 200 OK.
- [x] **Phase 3 — Document Understanding, Ingestion & Observability:** Docling layout parser, TableFormer table extraction, Docling HybridChunker (800 tokens), BioClinical ModernBERT (768-dim) normalized embeddings, PGVector production vector store in PostgreSQL (`helpbox_clinical_vectors`), and stage-level latency tracking with opaque `document_id` in `performance_metrics` table.
- [x] **Phase 4 — Incremental Indexing & Automatic Deletion Pruning:** Re-embedding only changed files via fast SHA-256 diffing (<35 ms); timestamp updating for touched files; version bumping and old vector purging for modified PDFs; automatically detecting company-deleted PDFs during scan, purging their chunks/vectors from pgvector, and marking status `WITHDRAWN`.
- [x] **Phase 5 — RAG Answer Generation & Provider Abstraction:** Local Ollama integration (`qwen3.5:2b-q4_K_M` running offline on CPU with `reasoning=False` for fast streaming), provider abstraction (`OllamaProvider`, `OpenAICompatibleProvider`, `GeminiProvider`), strict trial-isolated retrieval, evidence grounding prompt, server-constructed citations (source filename, 1-based page number, excerpt), abstention on unmentioned facts, SSE token streaming (`POST /api/chat/stream`), and zero database persistence for chat history.
- [x] **Phase 6 — Continuous Document Sync, Complete UI & Observability:** Background async scanner (`BackgroundScanner` in `app/scanner.py`, `app/sync.py`) running within FastAPI lifespan via `asyncio.to_thread` without external queue infrastructure (zero Celery/Redis/Kafka); live sync status indicator badge with animated pulsing light; quiet 15s UI polling for instant document updates; collapsible performance strip showing query embedding, vector search, retrieval latency, and tokens/sec; diagnostic scripts `scripts/status.sh` and `scripts/dev.sh`; live demonstration of file addition and deletion with abstention verification.

### Pending Development Phases

- [ ] **Phase 7 — End-to-End Verification & Company Deployment:** Full cross-trial isolation tests, container restart persistence verification, and VM deployment automation.

---

## 4. Full Technology Stack

| Layer | Component | Version / Identifier | Notes |
|---|---|---|---|
| **Runtime** | Python | 3.12 / 3.13 | Linux x86_64 / Windows / macOS |
| **Web Framework** | FastAPI | >=0.110.0 | Async ASGI backend |
| **ASGI Server** | Uvicorn | >=0.28.0 | Standard distribution |
| **Database** | PostgreSQL | 16.15 (Debian) | Pinned Docker container |
| **Vector Extension**| pgvector | 0.8.7 | Native PostgreSQL extension |
| **ORM** | SQLAlchemy | >=2.0.0 | Engine with `pool_pre_ping=True` |
| **DB Driver** | psycopg (v3) | >=3.1.0 | Binary driver |
| **Vector Adapter** | langchain-postgres | >=0.0.19 | `PGVectorStore` API |
| **PDF Parser** | Docling | 2.148.0 | Layout, tables, reading order |
| **Table Extraction**| Docling TableFormer| Fast Mode | Preserves rows, columns, headers |
| **OCR Backend** | RapidOCR | 3.10.0 | Selective for scanned pages |
| **Chunking** | Docling HybridChunker | Built-in | 800 tokens max |
| **Primary Embedding**| BioClinical ModernBERT | 768 dimensions | Normalized, cached locally (~571 MB) |
| **Fallback Embedding**| PubMedBERT 8M | 768 dimensions | Optional lightweight fallback |
| **Dev LLM** | Ollama (Qwen 3.5 2B)| 0.17+ / Q4_K_M | `qwen3.5:2b-q4_K_M` (Local CPU, 4K context, reasoning=False) |
| **Cloud LLM (Opt)** | Gemini 3.8 Flash | langchain-google-genai | Optional, user-configured |
| **Observability** | Technical Metrics | Implemented | Console timings + `performance_metrics` table + UI details |
| **Frontend** | Vanilla HTML5/CSS3/JS| Built-in | Served directly by FastAPI (Read-only UI) |
| **Excluded** | DMS / File Management | Strictly Excluded | Company .NET application manages file lifecycle |

> **Cost & Privacy Guarantee:** Zero paid OpenAI cloud dependencies. No OpenAI account, key, or billing is required. Local development runs 100% offline using local embeddings and Ollama. Absolutely no clinical text or chat history is stored in performance metrics.

---

## 5. Repository Structure

```text
Helpbox-EDC-rag/
├── README.md                                  # This authoritative root guide
└── helpbox_simple_agent_pack_v3/              # Application root
    ├── app/
    │   ├── __init__.py
    │   ├── config.py                          # Environment & settings loader
    │   ├── db.py                              # SQLAlchemy engine, session & init_db
    │   ├── models.py                          # DocumentInventory & verification models
    │   ├── trials.py                          # Safe folder discovery & path security
    │   ├── main.py                            # FastAPI routes & static file mounting
    │   └── static/                            # Clinical workspace frontend
    │       ├── index.html                     # Workspace layout & tabs
    │       ├── app.css                        # Clinical styling
    │       └── app.js                         # Trial navigation & API calls
    ├── data/
    │   ├── trials/                            # Trial document root
    │   │   ├── Trial_101/                     # Synthetic Trial 101 PDFs
    │   │   └── Trial_102/                     # Synthetic Trial 102 PDFs
    │   └── backups/                           # Local SQL dumps (gitignored)
    │       ├── latest.sql                     # Latest verified database dump
    │       └── helpbox_backup_*.sql           # Dated historical backups
    ├── docs/                                  # Specifications & persistent logs
    │   ├── ARCHITECTURE.md                    # Architecture diagrams & components
    │   ├── DATABASE_AND_RAG.md                # Unified database & RAG schema
    │   ├── DECISIONS.md                       # Architectural decision records
    │   ├── HELPBOX_SETUP_AND_RUNBOOK.md       # Complete Operations, Setup & Migration Manual
    │   ├── IMPLEMENTATION_PLAN.md             # Ordered development phases
    │   ├── NEXT_TASK.md                       # Immediate next task handoff
    │   ├── PHASE_GATES.md                     # Phase exit criteria & gates
    │   ├── PROGRESS.md                        # Verified development progress log
    │   ├── SETUP_NEW_MACHINE.md               # Step-by-step fresh laptop setup guide
    │   ├── SYSTEM_MAP.md                      # Comprehensive Architecture Audit & Data Flow
    │   ├── TECH_STACK.md                      # Detailed technology plan
    │   ├── UI_WORKSPACE_SPEC.md               # UI specification
    │   └── USER_ACTIONS.md                    # Pending & completed user inputs
    ├── scripts/
    │   ├── setup.sh                           # One-command installer (Linux / Codespaces)
    │   ├── setup.ps1                          # One-command installer (Windows PowerShell)
    │   ├── start_dev.sh                       # Safe multi-service launcher (Linux)
    │   ├── start_dev.ps1                      # Safe multi-service launcher (Windows)
    │   ├── status.sh                          # Multi-service health & resource diagnostic (Linux)
    │   ├── status.ps1                         # Multi-service health & resource diagnostic (Windows)
    │   ├── stop_dev.sh                        # Safe service shutdown (Linux)
    │   ├── stop_dev.ps1                       # Safe service shutdown (Windows)
    │   ├── backup_db.sh                       # Automated PostgreSQL pg_dump script (Linux)
    │   ├── backup_db.ps1                      # Automated PostgreSQL pg_dump script (Windows)
    │   ├── restore_db.sh                      # Automated psql restore script (Linux)
    │   ├── restore_db.ps1                     # Automated psql restore script (Windows)
    │   └── create_synthetic_trials.py         # Synthetic clinical PDF generator
    ├── tests/
    │   ├── __init__.py
    │   ├── test_trials.py                     # Trial discovery, safety & API tests (15 checks)
    │   ├── test_database.py                   # Live PostgreSQL & pgvector tests (5 checks)
    │   ├── test_ingestion.py                  # Docling parsing & vector embedding tests (3 checks)
    │   ├── test_incremental.py                # Incremental & deletion sync lifecycle (9 checks)
    │   ├── test_rag.py                        # RAG answer generation & streaming tests (6 checks)
    │   └── test_sync_scanner.py               # Background async scanner lifecycle (3 checks)
    ├── docker-compose.yml                     # PostgreSQL 16 + pgvector container
    ├── requirements.txt                       # Verified Python dependencies
    ├── .env.example                           # Configuration template
    ├── .env                                   # Local untracked environment config
    └── .gitignore                             # Git ignore rules
```

---

## 6. Installation & Setup Instructions

### 🚀 Recommended: One-Command Platform Installer (After Manual Git Clone)

Once you manually clone the repository from GitHub, enter the application pack directory and run the installer for your operating system:

#### On Windows 11 (PowerShell):
```powershell
cd Helpbox-EDC-rag\helpbox_simple_agent_pack_v3
.\scripts\setup.ps1
```

#### On Ubuntu / Debian / Linux / Codespaces (Bash):
```bash
cd Helpbox-EDC-rag/helpbox_simple_agent_pack_v3
./scripts/setup.sh
```

The installer automatically:
1. Detects OS and compatible Python (>= 3.10).
2. Interactively asks for custom instance names, ports, and container names (or press Enter for standard defaults).
3. Safely creates or updates `.env` (creates a timestamped backup of any existing config).
4. Creates `.venv` and installs all dependencies from `requirements.txt`.
5. Checks Docker, launches PostgreSQL 16 + pgvector container, and verifies health checks.
6. Initializes the database schema or lets you restore from a previous SQL backup (`data/backups/latest.sql`).
7. Checks Ollama and model caches (downloads models **only after explicit user confirmation**).
8. Prepares trial document folders and displays your daily run commands.

> 📖 **Authoritative Operations & Migration Manual:** [`helpbox_simple_agent_pack_v3/docs/HELPBOX_SETUP_AND_RUNBOOK.md`](helpbox_simple_agent_pack_v3/docs/HELPBOX_SETUP_AND_RUNBOOK.md)  
> 🗺️ **Comprehensive System Architecture Audit:** [`helpbox_simple_agent_pack_v3/docs/SYSTEM_MAP.md`](helpbox_simple_agent_pack_v3/docs/SYSTEM_MAP.md)

---

## 7. Daily Routine & Running the Services

### ⚡ One-Command Daily Routine

| Action | Windows 11 PowerShell | Linux / Codespaces Bash |
|---|---|---|
| **Start Everything** | `.\scripts\start_dev.ps1` | `./scripts/start_dev.sh` |
| **Check System Status** | `.\scripts\status.ps1` | `./scripts/status.sh` |
| **Open Application** | `http://localhost:8000` | `http://localhost:8000` |
| **Stop Application** | `.\scripts\stop_dev.ps1` | `./scripts/stop_dev.sh` |
| **Backup Database** | `.\scripts\backup_db.ps1` | `./scripts/backup_db.sh` |
| **Restore Database** | `.\scripts\restore_db.ps1` | `./scripts/restore_db.sh` |

### Manual Multi-Terminal Workflow (Optional for Debugging)

If you prefer to run services in separate visible terminals:

### Terminal 1 — PostgreSQL 16 + pgvector (Database Container)
```bash
cd /workspaces/Helpbox-EDC-rag/helpbox_simple_agent_pack_v3
docker compose up -d
docker logs -f helpbox-postgres
```

### Terminal 2 — Ollama Server (Local Offline LLM)
```bash
ollama serve
# Verify model availability in another command:
# ollama list
```

### Terminal 3 — FastAPI Application Backend & Background Sync
```bash
cd /workspaces/Helpbox-EDC-rag/helpbox_simple_agent_pack_v3
source .venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

- **Web Workspace:** Open `http://localhost:8000` (or `http://127.0.0.1:8000`) in your browser.
- **Continuous Sync Badge:** Shows `Sync: Active (120s)` in the top bar. Background scanner checks trial folders every 120 seconds.
- **Health Endpoint:** `http://localhost:8000/health`
- **Sync Status API:** `http://localhost:8000/api/sync/status`
- **Interactive Swagger Docs:** `http://localhost:8000/docs`

### System Status & Health Check Script
Run the automated diagnostic check at any time:
```bash
./scripts/status.sh
```
*Reports host RAM/disk usage, PostgreSQL container health, table record counts, Ollama server status, FastAPI backend sync state, and disk cache footprint.*

### Run Automated Tests

```bash
cd /workspaces/Helpbox-EDC-rag/helpbox_simple_agent_pack_v3
source .venv/bin/activate

# Execute all 41 verified regression checks across all 6 test suites
pytest -v tests/
```

---

## 8. Database Inspection in VS Code

You can visually inspect the PostgreSQL database directly within VS Code:

1. Install the official Microsoft extension: **PostgreSQL** (`ms-ossdata.vscode-pgsql`).
2. Press `Ctrl+Shift+P` (or `Cmd+Shift+P`) and choose **`PostgreSQL: Add Connection`**.
3. Enter the connection settings:
   - **Hostname:** `localhost`
   - **Database:** `helpbox`
   - **User:** `helpbox`
   - **Password:** *From line 5 of your `.env` file (`POSTGRES_PASSWORD`)*
   - **Port:** `5432`
   - **SSL:** `Disable` (or `Prefer`)
   - **Display Name:** `Helpbox Local DB`
4. Expand `Helpbox Local DB` &rarr; `Databases` &rarr; `helpbox` &rarr; `Schemas` &rarr; `public` &rarr; `Tables` to view:
   - `document_inventory`
   - `vector_verification`

---

## 9. Backup & Restore Instructions

The database dump is stored directly inside the persistent workspace (`data/backups/`) to protect against container recreation or Codespaces rebuilds.

### Create a Database Backup

```bash
cd /workspaces/Helpbox-EDC-rag/helpbox_simple_agent_pack_v3
./scripts/backup_db.sh
```
*Creates a dated SQL dump and updates `data/backups/latest.sql`.*

### Restore Database from Backup

```bash
cd /workspaces/Helpbox-EDC-rag/helpbox_simple_agent_pack_v3
./scripts/restore_db.sh
```

> **CRITICAL WARNING:** NEVER run `docker compose down -v` during routine maintenance. The `-v` flag deletes Docker named volumes, destroying persistent database data. Use `docker compose down` or `docker compose stop`.

---

## 10. Troubleshooting Common Issues

| Issue | Cause | Remedy |
|---|---|---|
| **Port 5432 in use** | Local PostgreSQL already running on host | Stop existing host postgres service (`sudo service postgresql stop`) or adjust port in `docker-compose.yml` and `.env`. |
| **Docker connection error** | Docker daemon not running | Ensure Docker Desktop is running (Windows/Mac) or start docker service (`sudo service docker start` on Linux). |
| **`pgvector` extension missing** | Standard Postgres image used instead of pgvector image | Ensure `docker-compose.yml` uses `pgvector/pgvector:0.8.7-pg16-bookworm`. |
| **Database connection refused** | Container still initializing | Wait 5–10 seconds for container health check: `docker inspect --format='{{json .State.Health.Status}}' helpbox-postgres`. |
| **`latest.sql` missing** | Fresh clone from GitHub | Run `./scripts/create_synthetic_trials.py` and start the FastAPI app to auto-initialize tables, or import an existing backup. |

---

## 11. Future Company Deployment Setup

When moving from GitHub Codespaces development to the company's controlled Linux VM:

1. **Database:** Deploy the same `docker-compose.yml` on the company VM, or point `DATABASE_URL` to the company's managed PostgreSQL 16 instance with `pgvector` enabled.
2. **Document Root:** Mount the company trial network storage directly to `data/trials/` via `TRIALS_DIR=/mnt/company_trials`.
3. **Private LLM:** Point `GENERATION_PROVIDER=openai_compatible` and `OPENAI_COMPATIBLE_BASE_URL` to the company's internal vLLM / Ollama inference server. Zero clinical text leaves the company perimeter.
4. **Offline Operation:** The entire pipeline (Docling, RapidOCR, BioClinical ModernBERT, and private LLM) operates 100% locally on the company infrastructure without external cloud APIs.
5. **Future Company Webhook/Event Trigger:** While Helpbox includes a periodic background folder scanner, the company can trigger instant synchronization when files are updated in their .NET application by invoking the modular synchronization logic (`synchronize_trial_documents()`).

---

## 12. Model Cache Persistence & Memory Management

- **Disk Footprint:**
  - Hugging Face cache (`~/.cache/huggingface`): ~1.1 GB (BioClinical ModernBERT + Docling layout models).
  - Ollama cache (`~/.ollama/models`): ~1.9 GB (Qwen 3.5 2B Q4_K_M GGUF).
- **Persistence Across Sessions:** Caches stored in the home directory survive normal machine restarts and Codespace stop/start cycles.
- **Codespaces Devcontainer Rebuild Risk:** If a user performs a full devcontainer rebuild in Codespaces, user home directory caches are wiped and models must be re-cached on first use. In contrast, the `/workspaces/Helpbox-EDC-rag/helpbox_simple_agent_pack_v3/data/backups/latest.sql` database dump is stored directly in the workspace directory and survives devcontainer rebuilds.
- **Dynamic Memory Loading:** Models load weights into RAM sequentially and unload dynamically, ensuring that peak system memory usage remains safely within the 8 GB RAM boundary during ingestion and inference.
