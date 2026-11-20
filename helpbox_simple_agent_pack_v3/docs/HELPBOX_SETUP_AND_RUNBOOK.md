# Helpbox — Complete Setup, Run & Migration Guide

> **Authoritative Operational Manual for Helpbox Clinical RAG**  
> **Application Root:** `/workspaces/Helpbox-EDC-rag/helpbox_simple_agent_pack_v3`  
> **Target Audiences:** Project Owners, Solo Developers, QA Engineers, DevOps  
> **Supported Environments:** Windows 11 (PowerShell), Ubuntu/Debian Linux (Bash), GitHub Codespaces

---

## 🚀 One-Command First-Time Setup (After Manual Git Clone)

After cloning the repository manually from GitHub, you do not need to run dozens of individual setup commands. Simply enter the application directory and run the one-command platform installer:

### On Windows 11 (PowerShell):
```powershell
cd Helpbox-EDC-rag\helpbox_simple_agent_pack_v3
.\scripts\setup.ps1
```

### On Ubuntu / Debian / Linux / Codespaces (Bash):
```bash
cd Helpbox-EDC-rag/helpbox_simple_agent_pack_v3
./scripts/setup.sh
```

> [!TIP]
> **What the installer automates:**
> 1. Detects OS, architecture, and compatible Python (>= 3.10).
> 2. Provides interactive customization of instance name, Docker Compose project, ports, database credentials, and container names (or press Enter for standard defaults).
> 3. Creates/updates `.env` safely without displaying or logging passwords (creates timestamped backups of existing `.env`).
> 4. Creates `.venv`, upgrades pip, and installs all dependencies from `requirements.txt`.
> 5. Verifies Docker daemon, starts PostgreSQL 16 + pgvector container with health checks.
> 6. Initializes fresh database schema and pgvector extension, OR restores from an existing SQL backup (`data/backups/latest.sql`).
> 7. Checks Ollama server and Hugging Face embedding model caches (downloads missing model artifacts **only after explicit user confirmation**).
> 8. Verifies all service endpoints and prepares you for immediate daily usage.

---

## ⚡ One-Page Daily Command Cheat Sheet

Keep this section handy for your daily development workflow.

### Daily Routine (Windows 11 PowerShell)

| Task | Command |
|---|---|
| **1. Start Everything Safely** | `.\scripts\start_dev.ps1` |
| **2. Check Service Health** | `.\scripts\status.ps1` |
| **3. Open the Web Application** | Open browser to `http://localhost:8000` |
| **4. Stop Application (Keep DB & Ollama)** | `.\scripts\stop_dev.ps1` |
| **5. Stop All Services (Including Ollama)** | `.\scripts\stop_dev.ps1 -All` |
| **6. View Database Logs** | `docker logs -f helpbox-postgres` |
| **7. Check Ollama Models in RAM** | `ollama ps` |
| **8. Back Up PostgreSQL Database** | `.\scripts\backup_db.ps1` |
| **9. Restore Database from Backup** | `.\scripts\restore_db.ps1` |

### Daily Routine (Linux / Codespaces Bash)

| Task | Command |
|---|---|
| **1. Start Everything Safely** | `./scripts/start_dev.sh` |
| **2. Check Service Health** | `./scripts/status.sh` |
| **3. Open the Web Application** | Open browser to `http://localhost:8000` |
| **4. Stop Application (Keep DB & Ollama)** | `./scripts/stop_dev.sh` |
| **5. Stop All Services (Including Ollama)** | `./scripts/stop_dev.sh --all` |
| **6. View Database Logs** | `docker logs -f helpbox-postgres` |
| **7. Check Ollama Models in RAM** | `ollama ps` |
| **8. Back Up PostgreSQL Database** | `./scripts/backup_db.sh` |
| **9. Restore Database from Backup** | `./scripts/restore_db.sh` |

---

## 1. System Overview & Architecture

Helpbox is a trial-scoped clinical document RAG (Retrieval-Augmented Generation) chatbot. It runs with **three coordinated services**:

```
[Service 1: PostgreSQL 16 + pgvector]  <--- Port 5432 (Docker Container)
       ▲
       │ SQL / Vector Queries
       ▼
[Service 2: FastAPI Backend + Scanner] <--- Port 8000 (Python Process)
       ▲
       │ HTTP REST /api/chat
       ▼
[Service 3: Ollama Model Server]       <--- Port 11434 (Host Model Daemon)
```

### Critical Architecture Realities
1. **Helpbox is NOT a Document Management System (DMS):** The company's main software (.NET/C#) handles document uploads, replacements, and deletions. Helpbox only accesses PDFs **read-only**.
2. **PostgreSQL runs inside Docker:** It uses the official `pgvector/pgvector:0.8.7-pg16-bookworm` image.
3. **FastAPI & Ollama run directly on your host machine:** They execute in your local OS (Windows, Linux, or Codespaces), not inside Docker.
4. **No External Task Queues:** The background sync scanner runs directly inside the FastAPI process lifespan using Python threads (`asyncio.to_thread`). No Celery, Redis, or Kafka required.
5. **Zero Paid Cloud API Dependencies:** Helpbox runs 100% offline using a local CPU embedding model (`BioClinical ModernBERT`) and a local quantized LLM (`Qwen 3.5 2B Q4_K_M` via Ollama).

---

## 2. Setup on a Brand-New Machine (Step-by-Step)

Follow these steps in exact order when setting up Helpbox on a fresh computer.

### Step 1: Hardware & Software Prerequisites

#### Hardware Requirements
- **RAM:** Minimum 8 GB RAM (16 GB recommended for faster CPU inference).
- **CPU:** 2 vCPU / 2 cores minimum (4+ cores recommended for faster Docling parsing).
- **Disk Space:** Minimum 15 GB free disk space (to store Docker images, Python virtualenv, and AI model weights).
- **OS:** Windows 11 (64-bit with WSL2), Ubuntu 22.04/24.04 LTS, macOS (Apple Silicon or Intel), or GitHub Codespaces.

#### Software to Install
1. **Git:** [https://git-scm.com/downloads](https://git-scm.com/downloads)
2. **Python:** Version 3.11, 3.12, or 3.13 (Python 3.11 or 3.12 recommended for broadest package wheel compatibility). Ensure you check *"Add Python to PATH"* during Windows installation.
3. **Docker:** 
   - **Windows/macOS:** Install [Docker Desktop](https://www.docker.com/products/docker-desktop/) (enable WSL2 engine on Windows).
   - **Linux:** Install Docker Engine and Docker Compose plugin (`sudo apt-get install docker-ce docker-compose-plugin`).
4. **Ollama:** Install from [https://ollama.com/download](https://ollama.com/download).

---

### Step 2: Clone the Repository

Open your terminal (PowerShell on Windows, Bash on Linux) and clone the repository:

```bash
# Clone the repository
git clone https://github.com/YourOrg/Helpbox-EDC-rag.git

# Enter the repository
cd Helpbox-EDC-rag

# Enter the actual Helpbox application pack directory
cd helpbox_simple_agent_pack_v3
```

> [!IMPORTANT]
> Always execute commands from within the `helpbox_simple_agent_pack_v3` folder, where `requirements.txt`, `docker-compose.yml`, and the `app/` folder reside.

> [!TIP]
> **Recommended One-Command Setup:** Once inside `helpbox_simple_agent_pack_v3`, you can run the automated platform setup script to complete Steps 3 through 8 in one go:
> - **Windows PowerShell:** `.\scripts\setup.ps1`
> - **Linux / Codespaces:** `./scripts/setup.sh`
> 
> The installer guides you interactively through instance customization, virtual environment creation, Docker startup, database initialization, and model caching. If you prefer to perform each step manually, follow Steps 3 through 8 below.

---

### Step 3: Set Up Python Virtual Environment & Dependencies

#### On Windows (PowerShell):
```powershell
# Create virtual environment named .venv
python -m venv .venv

# Activate the virtual environment
.\.venv\Scripts\Activate.ps1

# Upgrade pip and packaging tools
python -m pip install --upgrade pip setuptools wheel

# Install PyTorch CPU wheel first
pip install torch --index-url https://download.pytorch.org/whl/cpu

# Install all Helpbox dependencies
pip install -r requirements.txt
```

#### On Linux / macOS / Codespaces (Bash):
```bash
# Create virtual environment named .venv
python3 -m venv .venv

# Activate the virtual environment
source .venv/bin/activate

# Upgrade pip and packaging tools
pip install --upgrade pip setuptools wheel

# Install all Helpbox dependencies
pip install -r requirements.txt
```

#### Verification Step (Without running full tests):
Verify that core packages load cleanly:
```bash
python -c "import fastapi, sqlalchemy, docling, sentence_transformers; print('Python environment OK!')"
```

---

### Step 4: Configure Environment Variables (`.env`)

Copy the provided example file to create your local `.env`:

#### On Windows PowerShell:
```powershell
Copy-Item .env.example .env
```

#### On Linux / Bash:
```bash
cp .env.example .env
```

#### Environment Variable Specification Table:

| Variable | Purpose | Status | Default / Example Value |
|---|---|---|---|
| `TRIALS_DIR` | Relative or absolute path to trial PDF root folder | Mandatory | `./data/trials` |
| `POSTGRES_DB` | Name of PostgreSQL database inside Docker container | Mandatory | `helpbox` |
| `POSTGRES_USER` | PostgreSQL username | Mandatory | `helpbox` |
| `POSTGRES_PASSWORD` | PostgreSQL password (local dev only) | Mandatory | `change_this_local_dev_password` |
| `DATABASE_URL` | SQLAlchemy connection string | Mandatory | `postgresql+psycopg://helpbox:change_this_local_dev_password@localhost:5432/helpbox` |
| `EMBEDDING_MODEL` | Hugging Face model identifier for vector embeddings | Mandatory | `NeuML/bioclinical-modernbert-base-embeddings` |
| `EMBEDDING_DIMENSION` | Dimension count of dense vectors | Mandatory | `768` |
| `GENERATION_PROVIDER` | Active LLM backend (`ollama`, `gemini`, `openai_compatible`) | Mandatory | `ollama` |
| `OLLAMA_BASE_URL` | HTTP endpoint where Ollama daemon listens | Mandatory | `http://localhost:11434` |
| `OLLAMA_MODEL` | Ollama model tag to invoke | Mandatory | `qwen3.5:2b-q4_K_M` |
| `OLLAMA_CONTEXT_WINDOW` | Max context tokens passed to Ollama | Optional | `4096` |
| `OLLAMA_NUM_PREDICT` | Bounded maximum output generation tokens | Optional | `196` |
| `OLLAMA_KEEP_ALIVE` | Duration Ollama holds model in RAM | Optional | `60m` |
| `SYNC_ENABLED` | Enables continuous background folder sync scanner | Optional | `true` |
| `SYNC_INTERVAL_SECONDS`| Frequency in seconds between background sync scans | Optional | `120` |
| `RETRIEVAL_TOP_K` | Number of document chunks retrieved for RAG context | Optional | `4` |
| `CHUNK_TOKEN_SIZE` | Target chunk size for Docling HybridChunker | Optional | `800` |
| `GEMINI_API_KEY` | Google GenAI API key for optional cloud provider | Optional | `""` (Leave empty for local Ollama) |

---

### Step 5: Start PostgreSQL 16 + pgvector (Service 1)

Make sure Docker Desktop or Docker Engine is running on your machine.

```bash
# Start PostgreSQL container in background
docker compose up -d
```

#### How to Check:
```bash
# Verify container is running and healthy
docker ps --filter "name=helpbox-postgres"

# Check database logs
docker logs -f helpbox-postgres
```

The container exposes port `5432:5432` and stores its data inside the persistent Docker named volume `helpbox_postgres_data`.

> [!NOTE]
> Database tables and extensions (`vector 0.8.7`) are initialized automatically by FastAPI on startup via `app.db:init_db()`. You do not need to run manual SQL migrations on a fresh machine.

---

### Step 6: Install and Start Ollama (Service 2)

Ollama is our local offline LLM inference server.

#### 1. Start Ollama Server
- **On Windows:** Ollama runs automatically in the system tray after installation. If stopped, search for "Ollama" in the Start Menu, or run `ollama serve` in a terminal.
- **On Linux:** Start the service via `ollama serve` or systemd (`sudo systemctl start ollama`).

#### 2. Verify Ollama is Listening
```bash
curl http://127.0.0.1:11434/api/tags
```

#### 3. Pull the Required Qwen Generation Model
Run this command once to download the 4-bit quantized model (~1.9 GB):
```bash
ollama pull qwen3.5:2b-q4_K_M
```

#### 4. Verify Model Availability:
```bash
ollama list
```
You should see `qwen3.5:2b-q4_K_M` listed.

---

### Step 7: Embedding Model & PDF Parser Dependencies

Helpbox uses two models from Hugging Face:
1. **IBM Docling Layout & TableFormer Models:** Analyzes PDF layout and tabular grids.
2. **NeuML BioClinical ModernBERT:** Computes 768-dimensional clinical vector embeddings.

#### Automatic First-Use Download:
When you start the application for the first time, Helpbox automatically downloads these weights directly into your user cache directory:
- **Windows:** `C:\Users\<YourUser>\.cache\huggingface\hub\`
- **Linux:** `~/.cache/huggingface/hub/`

Total download size is approximately **1.1 GB**. Once downloaded, the application works 100% offline.

---

### Step 8: Prepare Trial Folders and PDFs

Helpbox requires a simple, flat folder structure directly under `data/trials/`:

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

- Each folder under `data/trials/` represents a single clinical trial.
- PDFs must be placed directly inside their trial folder (no nested subfolders).
- Helpbox opens PDFs **strictly read-only**. It will never rename, move, delete, or alter your source PDFs.

> [!TIP]
> If you have no PDFs and want to test immediately, generate synthetic demo PDFs:
> ```bash
> python scripts/create_synthetic_trials.py
> ```

---

### Step 9: Start FastAPI Backend & Web UI (Service 3)

Activate your virtual environment and start the application server:

#### Windows PowerShell:
```powershell
.\.venv\Scripts\Activate.ps1
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

#### Linux / macOS / Codespaces Bash:
```bash
source .venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

#### Open the Application:
Open your browser and navigate to:
```
http://localhost:8000
```
You will see the clinical workspace UI:
- **Left Sidebar:** Displays discovered trials (`Trial_101`, `Trial_102`).
- **Overview Tab:** Shows document counts and trial status.
- **Documents Tab:** Shows document inventory, versions, and SHA-256 hashes.
- **AI Assistant Tab:** Allows you to ask questions and see streamed answers with exact citations.

---

## 3. Environment-Specific Walkthroughs

### Environment A: Windows 11 (PowerShell + Docker Desktop + Ollama)

1. Open **Docker Desktop** and ensure the engine is running (green whale icon in system tray).
2. Open **PowerShell** as standard user.
3. Navigate to the project:
   ```powershell
   cd C:\path\to\Helpbox-EDC-rag\helpbox_simple_agent_pack_v3
   ```
4. Run the one-click launcher:
   ```powershell
   .\scripts\start_dev.ps1
   ```
5. Check status:
   ```powershell
   .\scripts\status.ps1
   ```
6. Open browser to `http://localhost:8000`.
7. When finished, stop services safely:
   ```powershell
   .\scripts\stop_dev.ps1
   ```

---

### Environment B: Ubuntu / Debian Linux

1. Ensure Docker Engine is active:
   ```bash
   sudo systemctl start docker
   ```
2. Open terminal in the project directory:
   ```bash
   cd /path/to/Helpbox-EDC-rag/helpbox_simple_agent_pack_v3
   ```
3. Run the automated starter script:
   ```bash
   ./scripts/start_dev.sh
   ```
4. Verify all tiers:
   ```bash
   ./scripts/status.sh
   ```
5. When finished, stop cleanly:
   ```bash
   ./scripts/stop_dev.sh
   ```

---

### Environment C: GitHub Codespaces

In GitHub Codespaces, Docker and Python are pre-installed.

1. Open terminal inside `/workspaces/Helpbox-EDC-rag/helpbox_simple_agent_pack_v3`.
2. Start all services:
   ```bash
   ./scripts/start_dev.sh
   ```
3. Codespaces will notify you: *"Your application running on port 8000 is available"*. Click **Open in Browser**.
4. Check health anytime:
   ```bash
   ./scripts/status.sh
   ```
5. If Codespaces is stopped and restarted:
   Run `./scripts/start_dev.sh` to resume services. Your database volume and model caches are preserved.

---

### Environment D: Running Multiple Independent Instances on One Computer

You can run two or more independent Helpbox instances (e.g., `helpbox_dev` and `helpbox_staging`) on the same physical computer without port, container, or database volume conflicts.

#### How It Works:
The one-command installer (`.\scripts\setup.ps1` or `./scripts/setup.sh`) prompts you for custom instance identifiers when you choose **[2] Custom Setup**.

| Parameter | Instance 1 (Default) | Instance 2 (Custom Example) |
|---|---|---|
| **Instance Name** | `helpbox` | `helpbox-dev2` |
| **Docker Compose Project** | `helpbox` | `helpbox2` |
| **PostgreSQL Container** | `helpbox-postgres` | `helpbox-postgres-2` |
| **PostgreSQL Volume** | `helpbox_postgres_data` | `helpbox_postgres_data_2` |
| **PostgreSQL Host Port** | `5432` | `5433` |
| **FastAPI App Port** | `8000` | `8001` |
| **Trials Root Directory** | `./data/trials` | `./data/trials_2` |

#### Setup Procedure for a Second Instance:
1. Clone the repository into a separate folder (e.g., `Helpbox-Instance-2`).
2. Run the platform installer:
   - Windows: `.\scripts\setup.ps1`
   - Linux: `./scripts/setup.sh`
3. When prompted, select **[2] Custom Setup**.
4. Enter unique ports (e.g., Postgres port `5433`, Web port `8001`) and unique container/volume names (`helpbox-postgres-2`, `helpbox2`).
5. The installer will generate a custom `.env` with the mapped ports and isolated Docker resources.
6. Start Instance 2 using `.\scripts\start_dev.ps1` or `./scripts/start_dev.sh`. Both instances run simultaneously with 100% isolation!

---

## 4. Moving Helpbox to Another Laptop

### Scenario A: Fresh Machine Setup (Code Only)

When you only have the Git repository and want to set everything up from scratch:

1. Clone the repository onto the new laptop.
2. Install Python 3.11/3.12, Docker Desktop, and Ollama.
3. Create `.venv` and run `pip install -r requirements.txt`.
4. Copy `.env.example` to `.env`.
5. Run `docker compose up -d` to create a fresh PostgreSQL container.
6. Run `ollama pull qwen3.5:2b-q4_K_M`.
7. Copy your source PDFs into `data/trials/<Trial_Name>/`.
8. Start the app: `./scripts/start_dev.sh` (or `.\scripts\start_dev.ps1`).
9. Click **Refresh** in the UI or let the background scanner index all PDFs automatically.

---

### Scenario B: Migration with Existing Database & Indexed Vectors

When you want to transfer your **already-indexed database** (so you don't have to re-parse or re-embed your PDFs):

#### On the OLD Laptop:
1. Ensure the PostgreSQL container is running.
2. Run the backup script:
   - **Linux:** `./scripts/backup_db.sh`
   - **Windows:** `.\scripts\backup_db.ps1`
3. Locate the backup file: `data/backups/latest.sql`.
4. Copy the following items onto a USB drive or secure transfer:
   - `data/backups/latest.sql` (Database dump with all vector embeddings).
   - `data/trials/` (Your original PDF files).
   - `.env` (Your configuration settings).

#### On the NEW Laptop:
1. Clone the repository and set up `.venv` as described in Step 3.
2. Place your `latest.sql` inside `data/backups/latest.sql`.
3. Place your PDFs inside `data/trials/`.
4. Start the fresh PostgreSQL container:
   ```bash
   docker compose up -d
   ```
5. Restore the database dump:
   - **Linux:** `./scripts/restore_db.sh`
   - **Windows:** `.\scripts\restore_db.ps1`
6. Pull the Ollama model: `ollama pull qwen3.5:2b-q4_K_M`.
7. Start the app: `./scripts/start_dev.sh` (or `.\scripts\start_dev.ps1`).
8. Open `http://localhost:8000`. All your trials, document statuses (`READY`), and 768-dim vector embeddings are immediately present without re-indexing!

---

## 5. Troubleshooting Guide

### 1. "Docker is not running" or `Cannot connect to the Docker daemon`
- **Meaning:** Docker Desktop or the background Docker service has not been started.
- **Inspection Command:** `docker info`
- **Safe Fix:** Start Docker Desktop from the Start Menu on Windows, or run `sudo systemctl start docker` on Linux. Wait 15 seconds until Docker is ready.
- **Verification:** Run `docker ps`. It should output table headers without errors.

---

### 2. "PostgreSQL connection refused" (Port 5432)
- **Meaning:** The `helpbox-postgres` container is stopped or exited.
- **Inspection Command:** `docker ps -a --filter "name=helpbox-postgres"`
- **Safe Fix:** Run `docker compose up -d`. Check container logs with `docker logs helpbox-postgres`.
- **Verification:** Run `./scripts/status.sh` (or `.\scripts\status.ps1`).

---

### 3. Port 5432 is already occupied by another service
- **Meaning:** A native PostgreSQL server is already running on your laptop outside Docker.
- **Inspection Command:**
  - *Windows:* `Get-NetTCPConnection -LocalPort 5432`
  - *Linux:* `sudo lsof -i :5432`
- **Safe Fix:** Either stop the local PostgreSQL service (`net stop postgresql` on Windows, `sudo systemctl stop postgresql` on Linux), or change the external port mapping in `docker-compose.yml` (e.g., `"5433:5432"`) and update `DATABASE_URL` in `.env` to port `5433`.

---

### 4. "Ollama is not running" or `curl: (7) Failed to connect to 127.0.0.1:11434`
- **Meaning:** The Ollama background daemon is not running.
- **Inspection Command:** `curl http://127.0.0.1:11434/api/tags`
- **Safe Fix:** Run `ollama serve` in a dedicated terminal, or launch Ollama from the Windows Start Menu.
- **Verification:** The curl command returns `{"models": [...]}`.

---

### 5. "Model qwen3.5:2b-q4_K_M not found"
- **Meaning:** Ollama is running, but the specific model weights have not been downloaded.
- **Inspection Command:** `ollama list`
- **Safe Fix:** Run `ollama pull qwen3.5:2b-q4_K_M`.
- **Verification:** `ollama list` displays `qwen3.5:2b-q4_K_M`.

---

### 6. Port 8000 is already in use
- **Meaning:** An earlier Uvicorn instance is still running in the background.
- **Inspection Command:**
  - *Windows:* `Get-Process python | Where-Object { $_.CommandLine -match "uvicorn" }`
  - *Linux:* `lsof -i :8000`
- **Safe Fix:**
  - *Windows:* `.\scripts\stop_dev.ps1`
  - *Linux:* `./scripts/stop_dev.sh`
- **Verification:** `curl http://127.0.0.1:8000/health` should fail after stopping, then succeed after starting cleanly.

---

### 7. "ModuleNotFoundError: No module named 'fastapi'" (or other package)
- **Meaning:** The Python virtual environment is not activated.
- **Inspection Command:** `which python` (Linux) or `Get-Command python` (Windows).
- **Safe Fix:** Activate the virtual environment:
  - *Windows:* `.\.venv\Scripts\Activate.ps1`
  - *Linux:* `source .venv/bin/activate`
  If packages are missing, re-run `pip install -r requirements.txt`.

---

### 8. Python package installation fails with compilation errors
- **Meaning:** C++ build tools are missing or PyTorch wheel could not be resolved.
- **Safe Fix:**
  Install the pre-built CPU wheels explicitly:
  ```bash
  pip install torch --index-url https://download.pytorch.org/whl/cpu
  pip install docling rapidocr transformers sentence-transformers
  ```

---

### 9. PDF indexing does not start or trial list is empty
- **Meaning:** The `data/trials` directory is empty or path configuration is mismatched.
- **Inspection Command:** Check directory contents: `ls data/trials`
- **Safe Fix:** Ensure folders are direct children (e.g., `data/trials/Trial_101/`). Verify that `TRIALS_DIR=./data/trials` in your `.env`.

---

### 10. Background sync scanner is idle or not updating
- **Meaning:** `SYNC_ENABLED` is set to false, or scanner is waiting for the 120s interval.
- **Inspection Command:** `curl http://127.0.0.1:8000/api/sync/status`
- **Safe Fix:** Set `SYNC_ENABLED=true` in `.env`. To trigger a scan immediately without waiting, click **Refresh** in the UI or call `POST /api/sync/run`.

---

### 11. "I do not have sufficient information" answered to every question
- **Meaning:** Normal RAG behavior when documents are not indexed or facts are missing.
- **Inspection Command:** Check document status in UI or query database:
  `SELECT filename, status FROM document_inventory;`
- **Safe Fix:** Ensure the document status is `READY`. If status is `FAILED` or `PENDING`, click **Refresh** to trigger re-indexing.

---

### 12. Model runs very slowly (high latency on CPU)
- **Meaning:** Ollama unloaded model from RAM, or thread contention occurred.
- **Safe Fix:**
  1. Ensure `OLLAMA_KEEP_ALIVE=60m` is set in `.env` so weights remain resident in RAM.
  2. Verify that `TORCH_NUM_THREADS=2` is set in your environment to eliminate thread thrashing.
  3. Close CPU-heavy applications while running inference.

---

### 13. Frontend UI shows "Unable to complete request"
- **Meaning:** The FastAPI server crashed or lost connection to Ollama/PostgreSQL.
- **Inspection Command:** Check `data/uvicorn.log` or run `./scripts/status.sh`.
- **Safe Fix:** Run `./scripts/start_dev.sh` (or `.\scripts\start_dev.ps1`) to recover services.

---

### 14. Codespace restarted and models are re-downloading
- **Meaning:** A complete devcontainer rebuild wipes root cache directories (`~/.cache`).
- **Safe Fix:** Model downloads are automatic and cache on NVMe. To prevent lost vector indices, always keep `data/backups/latest.sql` updated by running `./scripts/backup_db.sh` periodically.

---

## 6. Verification and Acceptance Checklist

Your Helpbox environment is demonstrably working when:

- [ ] `docker ps` shows container `helpbox-postgres` running on port `5432`.
- [ ] `ollama list` displays `qwen3.5:2b-q4_K_M`.
- [ ] `./scripts/status.sh` (or `.\scripts\status.ps1`) reports all services **ONLINE**.
- [ ] Browsing to `http://localhost:8000` loads the clinical trial workspace.
- [ ] Selecting `Trial_101` lists `Protocol.pdf` and `Safety_Report.pdf` with status `READY`.
- [ ] Asking a question in the AI Assistant tab streams an evidence-grounded answer with filename and page citations.
- [ ] Switching to `Trial_102` clears the chat history and enforces trial boundary isolation.
