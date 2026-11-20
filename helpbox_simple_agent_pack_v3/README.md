# Helpbox — Simple Trial-wise PDF RAG

This is the **project and persistent instruction pack** for building Helpbox. It intentionally keeps the product small and practical.

---

## ⚡ Quickstart: One-Command Setup & Daily Operations

After manually cloning the repository, enter this directory and run the setup script for your platform:

### 1. First-Time Setup (Automated One-Command Installer)

```powershell
# On Windows 11 (PowerShell):
.\scripts\setup.ps1
```

```bash
# On Ubuntu / Linux / Codespaces (Bash):
./scripts/setup.sh
```

*The installer verifies Python, creates `.venv`, installs requirements, starts PostgreSQL 16 + pgvector with health checks, initializes or restores the database, and verifies local AI model caches.*

### 2. Daily Routine Commands

| Action | Windows 11 PowerShell | Linux / Codespaces Bash |
|---|---|---|
| **Start Everything** | `.\scripts\start_dev.ps1` | `./scripts/start_dev.sh` |
| **Check System Status** | `.\scripts\status.ps1` | `./scripts/status.sh` |
| **Open Application** | `http://localhost:8000` | `http://localhost:8000` |
| **Stop Safely** | `.\scripts\stop_dev.ps1` | `./scripts/stop_dev.sh` |
| **Backup Database** | `.\scripts\backup_db.ps1` | `./scripts/backup_db.sh` |
| **Restore Database** | `.\scripts\restore_db.ps1` | `./scripts/restore_db.sh` |

> 📖 **Full Operations Manual:** [`docs/HELPBOX_SETUP_AND_RUNBOOK.md`](docs/HELPBOX_SETUP_AND_RUNBOOK.md)  
> 🗺️ **Complete Architecture Audit:** [`docs/SYSTEM_MAP.md`](docs/SYSTEM_MAP.md)

---

## Product in one sentence

Put PDFs in a folder for each trial, select that trial in Helpbox, ask questions, and receive answers grounded only in that trial's PDFs with correct filename and page citations.

## Simple document layout

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

PDFs go directly inside each trial folder. No nested document folders are part of the initial product.

## Required UI behavior

The app must look like a restrained clinical/business software workspace: top header, left trial sidebar, selected-trial workspace with Overview / Documents / AI Assistant tabs, and the chatbot inside the selected trial workspace below its document-status strip. Follow `docs/UI_WORKSPACE_SPEC.md`. Opening the assistant checks the selected folder and reuses existing pgvector records for unchanged PDFs; only new/changed files are indexed. Every question is restricted to the selected trial on the backend.

## Fixed stack

- Python 3.11
- FastAPI
- Small HTML/CSS/vanilla JavaScript UI
- LangChain for PDF loading, text splitting, embeddings, vector retrieval, and Gemini chat integration
- PostgreSQL + pgvector as the **only database/vector store**
- `langchain-postgres` using the maintained `PGVectorStore` API
- Local Hugging Face embeddings: `sentence-transformers/all-MiniLM-L6-v2`
- Gemini Flash model through `langchain-google-genai` for the first demo, model name configured in `.env`
- Docker Compose for PostgreSQL/pgvector where available

## What is deliberately excluded

No Qdrant, Chroma, Redis, Celery, Kafka, Kubernetes, microservices, multi-agent system, user login, upload portal, persistent chat history, analytics dashboard, or complex folder taxonomy. OCR and advanced visual/table understanding are not in the first working slice.

## Persistent project context (important for new CLI sessions)

Read [`PROJECT_CONTEXT.md`](PROJECT_CONTEXT.md) first after the workspace instruction files. It records the project goal, the exact current status of this starter pack versus the actual application, the complete file-reading order, and the daily resume procedure. It exists because a fresh Antigravity CLI session may not have the previous chat history. At every session end, update `docs/PROGRESS.md` and `docs/NEXT_TASK.md`.

## Give this folder to Antigravity

1. Extract this ZIP into the Helpbox workspace/repository root in GitHub Codespaces. Keep `AGENTS.md`, `GEMINI.md`, `docker-compose.yml`, and `docs/` at the workspace root.
2. Open/start Antigravity CLI with this folder as its workspace. Antigravity automatically discovers root `AGENTS.md`/`GEMINI.md` workspace rules.
3. Start the agent once with: **“Read AGENTS.md, GEMINI.md, and PROJECT_CONTEXT.md. Then follow the session-start reading order in PROJECT_CONTEXT.md, inspect the real workspace, and continue from docs/NEXT_TASK.md. Do not depend on previous chat history.”**
4. For later sessions, workspace instructions plus `PROJECT_CONTEXT.md`, `docs/PROGRESS.md`, and `docs/NEXT_TASK.md` are the persistent project memory; you should not need to paste the long prompt again.

If this is being added to an existing Helpbox repository, extract/merge the files without replacing existing source code. The agent must inspect Git status and preserve current work.

## First project instruction

The initial next task is recorded in `docs/NEXT_TASK.md`: inspect the real workspace, then build the simplest working slice for safe trial-folder discovery and PDF scanning. Do not spend time rewriting this plan.

## Important privacy note

The initial Gemini API path sends retrieved PDF text to Google's external API when answering. Use synthetic documents or company-approved data until the company explicitly approves this data flow. Never put a real API key in source control or chat; configure it through Codespaces Secrets or an untracked `.env` file.

## Configuration starter

- `.env.example` — environment variable template.
- `docker-compose.yml` — one PostgreSQL/pgvector service with a persistent named volume.
- `data/trials/` — place trial folders here.

The app source code is intentionally left for the Antigravity implementation agent to build in small, verified slices. This ZIP is the persistent project specification, setup starter, and agent handoff—not a claim that the runnable chatbot has already been implemented.
