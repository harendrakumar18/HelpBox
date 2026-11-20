# Helpbox — Fresh Machine Installation & Setup Guide

This guide provides step-by-step instructions for installing and running Helpbox on a fresh computer (Windows, macOS, or Linux). It assumes no prior Helpbox installation exists on the target machine.

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Clone the Repository](#2-clone-the-repository)
3. [Python Virtual Environment Setup](#3-python-virtual-environment-setup)
4. [Environment Configuration (.env)](#4-environment-configuration-env)
5. [PostgreSQL + pgvector with Docker](#5-postgresql--pgvector-with-docker)
6. [Database Backup & Restore](#6-database-backup--restore)
7. [Visual Database Inspection in VS Code](#7-visual-database-inspection-in-vs-code)
8. [Running Helpbox](#8-running-helpbox)
9. [Adding Clinical Trial PDFs](#9-adding-clinical-trial-pdfs)
10. [Current AI & Model Status (Installed vs. Pending)](#10-current-ai--model-status-installed-vs-pending)
11. [Troubleshooting](#11-troubleshooting)

---

## 1. Prerequisites

Before setting up Helpbox, install and verify these tools:

### A. Git
- **Download:** [https://git-scm.com/downloads](https://git-scm.com/downloads)
- **Verify:**
  ```bash
  git --version
  ```
  *Expected output:* `git version 2.x.x`

### B. Python (3.12 or 3.13)
- **Download:** [https://www.python.org/downloads/](https://www.python.org/downloads/)
- *Windows Note:* Ensure **"Add python.exe to PATH"** is checked during installation.
- **Verify:**
  ```bash
  # Windows PowerShell
  python --version
  
  # Linux / macOS
  python3 --version
  ```
  *Expected output:* `Python 3.12.x` or `Python 3.13.x`

### C. Docker Desktop / Docker Engine
- **Windows / macOS:** Install [Docker Desktop](https://www.docker.com/products/docker-desktop/) (enable WSL 2 backend on Windows).
- **Linux:** Install Docker Engine and Docker Compose plugin ([https://docs.docker.com/engine/install/](https://docs.docker.com/engine/install/)).
- **Verify:**
  ```bash
  docker --version
  docker compose version
  ```
  *Expected output:* `Docker version 2x.x.x` and `Docker Compose version v2.x.x` (or `v5.x.x`)

### D. Visual Studio Code
- **Download:** [https://code.visualstudio.com/](https://code.visualstudio.com/)
- **Verify:**
  ```bash
  code --version
  ```

### E. Microsoft PostgreSQL Extension for VS Code
- Install the official Microsoft extension from VS Code marketplace:
  ```bash
  code --install-extension ms-ossdata.vscode-pgsql
  ```

### F. Ollama (Pending Phase 5 — For Local LLM Inference)
- **Download:** [https://ollama.com/download](https://ollama.com/download)
- *Note:* Needed in Phase 5 for local Qwen 3.5 2B. Not required for Phases 1 & 2.
- **Verify:**
  ```bash
  ollama --version
  ```

---

## 2. Clone the Repository

Clone the authoritative GitHub repository and change into the application root:

```bash
# 1. Clone the repository
git clone https://github.com/Abhishek18-dev/Helpbox-EDC-rag.git

# 2. Enter the repository root
cd Helpbox-EDC-rag

# 3. Enter the application package root (where code and docker-compose.yml live)
cd helpbox_simple_agent_pack_v3

# 4. Verify Git status
git status
```

> **IMPORTANT DIRECTORY NOTE:** All subsequent commands (`docker compose`, `pytest`, `uvicorn`, `python`) must be executed from inside `Helpbox-EDC-rag/helpbox_simple_agent_pack_v3`.

---

## 3. Python Virtual Environment Setup

Create an isolated virtual environment to prevent package conflicts:

### On Windows (PowerShell)

```powershell
# Inside Helpbox-EDC-rag\helpbox_simple_agent_pack_v3

# 1. If script execution is restricted on Windows, allow it for this process:
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process

# 2. Create the virtual environment
python -m venv .venv

# 3. Activate the environment
.\.venv\Scripts\Activate.ps1

# 4. Upgrade pip
python -m pip install --upgrade pip

# 5. Install verified dependencies
pip install -r requirements.txt
```

### On Linux / macOS / GitHub Codespaces (Bash)

```bash
# Inside Helpbox-EDC-rag/helpbox_simple_agent_pack_v3

# 1. Create the virtual environment
python3 -m venv .venv

# 2. Activate the environment
source .venv/bin/activate

# 3. Upgrade pip
pip install --upgrade pip

# 4. Install verified dependencies
pip install -r requirements.txt
```

### To Deactivate the Environment (When finished working)

```bash
deactivate
```

---

## 4. Environment Configuration (.env)

Helpbox loads its runtime configuration from an untracked `.env` file.

### Copy the Template

- **Windows PowerShell:**
  ```powershell
  Copy-Item .env.example .env
  ```
- **Linux / macOS:**
  ```bash
  cp .env.example .env
  ```

### Variable Reference & What Each Means

Open `.env` in VS Code and review the variables:

| Variable | Default Value | Description |
|---|---|---|
| `TRIALS_DIR` | `./data/trials` | Path to folder containing direct clinical trial subfolders. |
| `POSTGRES_DB` | `helpbox` | PostgreSQL database name (matches `docker-compose.yml`). |
| `POSTGRES_USER` | `helpbox` | PostgreSQL database user (matches `docker-compose.yml`). |
| `POSTGRES_PASSWORD` | `change_this_local_dev_password` | Local database password. Choose a secure value for your machine. |
| `DATABASE_URL` | `postgresql+psycopg://helpbox:<PASSWORD>@localhost:5432/helpbox` | Connection URL used by SQLAlchemy and psycopg 3. Must match `POSTGRES_PASSWORD`. |
| `EMBEDDING_MODEL` | `NeuML/bioclinical-modernbert-base-embeddings` | Primary clinical embedding model (Phase 3). |
| `EMBEDDING_DIMENSION` | `768` | Embedding vector dimension (768). |
| `GENERATION_PROVIDER` | `ollama` | Active LLM provider (`ollama` for local CPU; `gemini` for optional cloud). |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Endpoint of the local Ollama daemon. |
| `OLLAMA_MODEL` | `qwen3.5:2b-q4_K_M` | Local Qwen model tag (Phase 5). |
| `OLLAMA_CONTEXT_WINDOW`| `4096` | Conservative 4K context window for low RAM usage. |
| `GEMINI_API_KEY` | *(Blank)* | Optional cloud provider key. Leave empty for 100% offline local dev. |
| `RETRIEVAL_TOP_K` | `4` | Number of evidence chunks retrieved per question. |
| `CHUNK_TOKEN_SIZE` | `800` | Target token size for Docling HybridChunker. |
| `OCR_ENABLED` | `true` | Enables selective RapidOCR on scanned/unreadable pages. |
| `TABLE_EXTRACTION_ENABLED`| `true` | Enables TableFormer structured table extraction. |

> **SECURITY RULE:** Never commit `.env` to Git. The `.gitignore` file automatically excludes `.env`.

---

## 5. PostgreSQL + pgvector with Docker

Helpbox uses one unified PostgreSQL 16 database with the `pgvector` extension.

### Start the Database Container

```bash
# Start container in detached background mode
docker compose up -d
```

### Verify Container Status & Health

```bash
docker compose ps
```
*Expected status:* `helpbox-postgres` is `Up` and `healthy` on `0.0.0.0:5432->5432/tcp`.

### Check Logs (If needed)

```bash
docker compose logs -f db
```

### Restart Database

```bash
docker compose restart db
```

### Stop Database Container Safely

```bash
docker compose stop
```

> **CRITICAL WARNING:** NEVER run `docker compose down -v`. The `-v` flag deletes named Docker volumes, destroying all persistent database records. Always use `docker compose stop` or `docker compose down` (without `-v`).

### Verify pgvector Extension Inside Container

```bash
docker exec helpbox-postgres psql -U helpbox -d helpbox -c "\dx"
```
*Expected output:* You should see `vector` version `0.8.7` listed alongside `plpgsql`.

---

## 6. Database Backup & Restore

All database backups are stored as raw SQL files inside `data/backups/latest.sql`. This folder is excluded from Git to prevent exposing data.

### Create a Fresh Backup

- **Linux / macOS / Codespaces / WSL:**
  ```bash
  ./scripts/backup_db.sh
  ```
- **Windows PowerShell:**
  ```powershell
  docker exec helpbox-postgres pg_dump -U helpbox -d helpbox > data\backups\latest.sql
  ```
*Verifies that a dated backup file and `data/backups/latest.sql` are created.*

### Restore Database from Backup

- **Linux / macOS / Codespaces / WSL:**
  ```bash
  ./scripts/restore_db.sh
  ```
- **Windows PowerShell:**
  ```powershell
  Get-Content data\backups\latest.sql | docker exec -i helpbox-postgres psql -U helpbox -d helpbox
  ```

### Transferring Database to Another Laptop

1. Copy `data/backups/latest.sql` via an encrypted USB drive or secure transfer (never via public Git).
2. On the new laptop, start Docker (`docker compose up -d`).
3. Place `latest.sql` inside `data/backups/`.
4. Run the restore command above.

---

## 7. Visual Database Inspection in VS Code

1. In VS Code, install the official Microsoft extension:
   ```bash
   code --install-extension ms-ossdata.vscode-pgsql
   ```
2. Press `Ctrl + Shift + P` (or `Cmd + Shift + P` on Mac) and select **`PostgreSQL: Add Connection`**.
3. Enter the connection settings:
   - **Hostname:** `localhost`
   - **Database:** `helpbox`
   - **User:** `helpbox`
   - **Password:** *Value from line 5 of your `.env` (`POSTGRES_PASSWORD`)*
   - **Save password:** `Yes`
   - **Port:** `5432`
   - **Connection type / SSL:** `Disable` (or `Prefer`)
   - **Display name:** `Helpbox Local DB`
4. In the left Activity Bar, click the **PostgreSQL (Elephant)** icon.
5. Browse:
   - `Helpbox Local DB` &rarr; `Databases` &rarr; `helpbox` &rarr; `Schemas` &rarr; `public` &rarr; `Tables`
6. You will see the active tables:
   - **`document_inventory`**: Tracks direct trial PDFs, SHA-256 hashes, file sizes, and status.
   - **`vector_verification`**: Verified 384-dimensional pgvector test table.
7. Right-click `document_inventory` &rarr; click **Select Top 1000** to view table rows.

---

## 8. Running Helpbox

### Step 1: Start PostgreSQL

```bash
docker compose up -d
```

### Step 2: Activate Virtual Environment

- **Windows:** `.\.venv\Scripts\Activate.ps1`
- **Linux / macOS:** `source .venv/bin/activate`

### Step 3: Start the FastAPI Server

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Step 4: Access Helpbox

- **Web Browser:** Open [http://localhost:8000](http://localhost:8000)
- **API Health Check:** [http://localhost:8000/health](http://localhost:8000/health)
- **Interactive Swagger Docs:** [http://localhost:8000/docs](http://localhost:8000/docs)

### Step 5: Run Automated Tests

To verify that trial listing, path safety, and database persistence are 100% operational:

```bash
pytest -v tests/test_database.py tests/test_trials.py
```
*Expected result:* **20 passed, 0 failed**.

### Step 6: Shutting Down Safely

1. In the terminal running Uvicorn, press `Ctrl + C` to stop FastAPI.
2. Stop the PostgreSQL container:
   ```bash
   docker compose stop
   ```

---

## 9. Adding Clinical Trial PDFs

Helpbox requires a strictly flat folder convention:

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

### Rules:
1. Create a direct folder inside `data/trials/` named after the trial (e.g., `Trial_103`).
2. Drop native-text PDF files directly inside `data/trials/Trial_103/`.
3. Do not create nested subfolders inside trial directories.
4. Source PDFs are read-only; Helpbox will never rename or modify them.
5. In the UI, click **"Refresh Documents"** or call `POST /api/trials/Trial_103/refresh` to compute SHA-256 hashes and register them in PostgreSQL.

### Generate Synthetic Test Data (Optional)

```bash
python scripts/create_synthetic_trials.py
```
*Creates synthetic oncology (`Trial_101`) and cardiology (`Trial_102`) test PDFs.*

---

## 10. Current AI & Model Status (Installed vs. Pending)

### Status as of Today's Freeze

| Component | Status | Details |
|---|---|---|
| **Phase 1: Foundation & UI** | **INSTALLED & VERIFIED** | FastAPI backend, clinical workspace HTML/CSS/JS, trial switching. |
| **Phase 2: Database & pgvector**| **INSTALLED & VERIFIED** | PostgreSQL 16 + pgvector 0.8.7 container, SQLAlchemy models, backups. |
| **Docling PDF Parser** | **PENDING (Phase 3)** | Not downloaded. Requires user approval before package install. |
| **TableFormer Table Extraction**| **PENDING (Phase 3)** | Not downloaded. Part of Docling pipeline. |
| **RapidOCR Backend** | **PENDING (Phase 3)** | Not downloaded. Selective OCR for scanned pages. |
| **BioClinical ModernBERT (768d)**| **PENDING (Phase 3)** | Not downloaded (~600 MB). Primary embedding model. |
| **PubMedBERT 8M (768d)** | **PENDING (Phase 3)** | Not downloaded (~31 MB). Lightweight fallback. |
| **Ollama & Qwen 3.5 2B** | **PENDING (Phase 5)** | Not downloaded (~1.9 GB). Dev LLM generation. |
| **Gemini 3.8 Flash** | **OPTIONAL** | Cloud fallback. Only active when user configures `GEMINI_API_KEY`. |
| **OpenAI Cloud API** | **EXCLUDED** | Zero OpenAI account, key, or billing required. |

### Future Planned Setup Commands (Phase 3 & Phase 5)

> **DO NOT RUN YET** — These commands will be executed in Phase 3 and Phase 5 after explicit user approval.

```bash
# [PENDING Phase 3] Install CPU PyTorch, Docling & Transformers:
# pip install torch --index-url https://download.pytorch.org/whl/cpu
# pip install docling langchain-docling transformers sentence-transformers

# [PENDING Phase 5] Pull local Qwen 3.5 2B via Ollama:
# ollama pull qwen3.5:2b-q4_K_M
```

---

## 11. Troubleshooting

### 1. Port 5432 Already in Use
- **Error:** `Bind for 0.0.0.0:5432 failed: port is already allocated`
- **Cause:** Another PostgreSQL service is running locally on your laptop.
- **Remedy:** Stop the host PostgreSQL service:
  - Windows: Open `services.msc`, find `postgresql-x64-xx`, and click **Stop**.
  - Linux: `sudo systemctl stop postgresql`
  - macOS: `brew services stop postgresql`

### 2. Docker Daemon Not Running
- **Error:** `Cannot connect to the Docker daemon at unix:///var/run/docker.sock`
- **Cause:** Docker Desktop or Docker service is not running.
- **Remedy:** Start Docker Desktop (Windows/Mac) or run `sudo systemctl start docker` (Linux).

### 3. ExecutionPolicy Error on Windows PowerShell
- **Error:** `Activate.ps1 cannot be loaded because running scripts is disabled on this system`
- **Remedy:** Run this command in PowerShell before activating:
  ```powershell
  Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process
  ```

### 4. Database Password Mismatch
- **Error:** `psycopg.OperationalError: password authentication failed for user "helpbox"`
- **Cause:** `POSTGRES_PASSWORD` in `.env` does not match the password Docker used when creating the volume.
- **Remedy:** Check the password in `.env` and `docker-compose.yml`. If the volume was created with an older password, restore from `data/backups/latest.sql`.

### 5. Database Connection Refused
- **Error:** `connection to server at "localhost", port 5432 failed: Connection refused`
- **Cause:** The Docker container has not finished its health check startup.
- **Remedy:** Wait 5 seconds and check container status:
  ```bash
  docker compose ps
  ```

### 6. pgvector Extension Not Found
- **Error:** `extension "vector" is not available`
- **Cause:** A standard postgres image was pulled instead of the pgvector image.
- **Remedy:** Ensure `docker-compose.yml` uses `image: pgvector/pgvector:0.8.7-pg16-bookworm`. Run `docker compose up -d --force-recreate`.
