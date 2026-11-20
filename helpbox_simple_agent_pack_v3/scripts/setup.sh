#!/usr/bin/env bash
# ==============================================================================
# Helpbox — Platform-Specific One-Command Environment Installer (Linux/Codespaces)
# ==============================================================================
# Automates first-time setup after cloning:
#   1. Detects OS and compatible Python (3.10+)
#   2. Configures instance settings interactively or with sensible defaults
#   3. Generates/updates .env safely (preserving existing configurations)
#   4. Creates & configures Python virtual environment (.venv) and dependencies
#   5. Checks Docker, Docker Compose, and starts PostgreSQL + pgvector
#   6. Initializes fresh database schema or restores from backup
#   7. Checks Ollama inference server and embedding model caches
#   8. Downloads missing models ONLY after explicit user confirmation
#   9. Verifies complete multi-service readiness and displays startup commands
# ==============================================================================

set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

# ANSI Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
RED='\033[0;31m'
BOLD='\033[1m'
NC='\033[0m'

# Help message
if [ "${1:-}" = "-h" ] || [ "${1:-}" = "--help" ]; then
    echo "Usage: ./scripts/setup.sh [OPTIONS]"
    echo ""
    echo "Helpbox One-Command Environment Installer for Linux / Codespaces."
    echo ""
    echo "Options:"
    echo "  --default, -y    Run quick setup non-interactively with default settings."
    echo "  --help, -h       Show this help message and exit."
    exit 0
fi

NON_INTERACTIVE=false
if [ "${1:-}" = "--default" ] || [ "${1:-}" = "-y" ]; then
    NON_INTERACTIVE=true
fi

echo -e "${BLUE}================================================================${NC}"
echo -e "${BOLD}${CYAN}          HELPBOX — ONE-COMMAND ENVIRONMENT INSTALLER            ${NC}"
echo -e "${BLUE}================================================================${NC}"
echo -e "Application Root: ${PROJECT_ROOT}"

# ------------------------------------------------------------------------------
# STEP 1: OS & Environment Detection
# ------------------------------------------------------------------------------
echo -e "\n${YELLOW}[Step 1/8] Detecting Operating System & Host Environment...${NC}"

OS_NAME="$(uname -s)"
ARCH_NAME="$(uname -m)"
echo -e "  --> Operating System: ${GREEN}${OS_NAME} (${ARCH_NAME})${NC}"

if [ -f "/.dockerenv" ] || [ -n "${CODESPACES:-}" ]; then
    echo -e "  --> Environment: ${GREEN}GitHub Codespaces / Dev Container${NC}"
elif [ "$OS_NAME" = "Linux" ]; then
    if [ -f "/etc/os-release" ]; then
        DISTRO=$(grep PRETTY_NAME /etc/os-release | cut -d= -f2 | tr -d '"')
        echo -e "  --> Linux Distribution: ${GREEN}${DISTRO}${NC}"
    fi
elif [ "$OS_NAME" = "Darwin" ]; then
    echo -e "  --> Environment: ${GREEN}macOS Host${NC}"
fi

# Detect Compatible Python (>= 3.10)
PYTHON_CMD=""
for cmd in python3 python py; do
    if command -v "$cmd" >/dev/null 2>&1; then
        if "$cmd" -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" 2>/dev/null; then
            PYTHON_CMD="$cmd"
            PY_VER=$("$cmd" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')")
            break
        fi
    fi
done

if [ -z "$PYTHON_CMD" ]; then
    echo -e "  ${RED}[!] Compatible Python (>= 3.10) was not found on your system.${NC}"
    echo -e "      Please install Python 3.11, 3.12, or 3.13:"
    echo -e "      - Ubuntu/Debian: sudo apt update && sudo apt install -y python3 python3-venv python3-pip"
    echo -e "      - Fedora/RHEL:   sudo dnf install -y python3 python3-pip"
    echo -e "      - Arch Linux:    sudo pacman -S python python-pip"
    echo -e "      - macOS:         brew install python@3.12"
    exit 1
fi
echo -e "  --> Python Runtime: ${GREEN}${PYTHON_CMD} (version ${PY_VER})${NC}"

# ------------------------------------------------------------------------------
# STEP 2: Interactive Configuration & Instance Customization
# ------------------------------------------------------------------------------
echo -e "\n${YELLOW}[Step 2/8] Configuring Instance Settings...${NC}"

# Read existing .env defaults if present
EXISTING_ENV=false
if [ -f "$PROJECT_ROOT/.env" ]; then
    EXISTING_ENV=true
    set -a
    source "$PROJECT_ROOT/.env" 2>/dev/null || true
    set +a
fi

DEF_INSTANCE="${HELPBOX_INSTANCE_NAME:-helpbox}"
DEF_COMPOSE_PROJECT="${COMPOSE_PROJECT_NAME:-helpbox_simple_agent_pack_v3}"
DEF_CONTAINER="${POSTGRES_CONTAINER_NAME:-helpbox-postgres}"
DEF_DB_NAME="${POSTGRES_DB:-helpbox}"
DEF_DB_USER="${POSTGRES_USER:-helpbox}"
DEF_DB_PASS="${POSTGRES_PASSWORD:-change_this_local_dev_password}"
DEF_VOLUME="${POSTGRES_VOLUME_NAME:-helpbox_simple_agent_pack_v3_helpbox_postgres_data}"
DEF_PG_PORT="${POSTGRES_HOST_PORT:-5432}"
DEF_APP_PORT="${APP_PORT:-8000}"
DEF_OLLAMA_URL="${OLLAMA_BASE_URL:-http://localhost:11434}"
DEF_GEN_MODEL="${OLLAMA_MODEL:-qwen3.5:2b-q4_K_M}"
DEF_EMB_MODEL="${EMBEDDING_MODEL:-NeuML/bioclinical-modernbert-base-embeddings}"
DEF_TRIALS_DIR="${TRIALS_DIR:-./data/trials}"

SETUP_MODE="1"
if [ "$NON_INTERACTIVE" = false ]; then
    echo -e "Choose setup configuration mode:"
    echo -e "  ${BOLD}[1] Quick Setup${NC}   (Recommended — Uses standard default settings)"
    echo -e "  ${BOLD}[2] Custom Setup${NC}  (Customize instance name, ports, container names, database)"
    read -r -p "Enter choice [1]: " user_mode_choice
    if [ "$user_mode_choice" = "2" ]; then
        SETUP_MODE="2"
    fi
fi

if [ "$SETUP_MODE" = "2" ]; then
    echo -e "\n${CYAN}--- Custom Instance Parameters ---${NC}"
    read -r -p "Helpbox Instance Name [${DEF_INSTANCE}]: " input_val
    CFG_INSTANCE="${input_val:-$DEF_INSTANCE}"

    read -r -p "Docker Compose Project Name [${DEF_COMPOSE_PROJECT}]: " input_val
    CFG_COMPOSE_PROJECT="${input_val:-$DEF_COMPOSE_PROJECT}"

    read -r -p "PostgreSQL Container Name [${DEF_CONTAINER}]: " input_val
    CFG_CONTAINER="${input_val:-$DEF_CONTAINER}"

    read -r -p "PostgreSQL Database Name [${DEF_DB_NAME}]: " input_val
    CFG_DB_NAME="${input_val:-$DEF_DB_NAME}"

    read -r -p "PostgreSQL Username [${DEF_DB_USER}]: " input_val
    CFG_DB_USER="${input_val:-$DEF_DB_USER}"

    # Mask password input
    read -r -s -p "PostgreSQL Password (leave blank to keep default): " input_val
    echo ""
    CFG_DB_PASS="${input_val:-$DEF_DB_PASS}"

    read -r -p "PostgreSQL Docker Volume Name [${DEF_VOLUME}]: " input_val
    CFG_VOLUME="${input_val:-$DEF_VOLUME}"

    # Port validation
    while true; do
        read -r -p "PostgreSQL Host Port [${DEF_PG_PORT}]: " input_val
        val="${input_val:-$DEF_PG_PORT}"
        if [[ "$val" =~ ^[0-9]+$ ]] && [ "$val" -ge 1024 ] && [ "$val" -le 65535 ]; then
            CFG_PG_PORT="$val"
            break
        elif [ "$val" -eq 5432 ]; then
            CFG_PG_PORT="5432"
            break
        else
            echo -e "  ${RED}[!] Invalid port number. Please enter a number between 1024 and 65535 (or 5432).${NC}"
        fi
    done

    while true; do
        read -r -p "FastAPI Application Port [${DEF_APP_PORT}]: " input_val
        val="${input_val:-$DEF_APP_PORT}"
        if [[ "$val" =~ ^[0-9]+$ ]] && [ "$val" -ge 1024 ] && [ "$val" -le 65535 ]; then
            CFG_APP_PORT="$val"
            break
        else
            echo -e "  ${RED}[!] Invalid port number. Please enter a number between 1024 and 65535.${NC}"
        fi
    done

    read -r -p "Ollama Server Endpoint [${DEF_OLLAMA_URL}]: " input_val
    CFG_OLLAMA_URL="${input_val:-$DEF_OLLAMA_URL}"

    read -r -p "LLM Generation Model [${DEF_GEN_MODEL}]: " input_val
    CFG_GEN_MODEL="${input_val:-$DEF_GEN_MODEL}"

    read -r -p "Clinical Embedding Model [${DEF_EMB_MODEL}]: " input_val
    CFG_EMB_MODEL="${input_val:-$DEF_EMB_MODEL}"

    read -r -p "Trial PDF Root Directory [${DEF_TRIALS_DIR}]: " input_val
    CFG_TRIALS_DIR="${input_val:-$DEF_TRIALS_DIR}"
else
    CFG_INSTANCE="$DEF_INSTANCE"
    CFG_COMPOSE_PROJECT="$DEF_COMPOSE_PROJECT"
    CFG_CONTAINER="$DEF_CONTAINER"
    CFG_DB_NAME="$DEF_DB_NAME"
    CFG_DB_USER="$DEF_DB_USER"
    CFG_DB_PASS="$DEF_DB_PASS"
    CFG_VOLUME="$DEF_VOLUME"
    CFG_PG_PORT="$DEF_PG_PORT"
    CFG_APP_PORT="$DEF_APP_PORT"
    CFG_OLLAMA_URL="$DEF_OLLAMA_URL"
    CFG_GEN_MODEL="$DEF_GEN_MODEL"
    CFG_EMB_MODEL="$DEF_EMB_MODEL"
    CFG_TRIALS_DIR="$DEF_TRIALS_DIR"
    echo -e "  --> Using default configuration (Instance: ${CFG_INSTANCE}, Web Port: ${CFG_APP_PORT}, DB Port: ${CFG_PG_PORT})"
fi

# ------------------------------------------------------------------------------
# STEP 3: Safe .env Configuration
# ------------------------------------------------------------------------------
echo -e "\n${YELLOW}[Step 3/8] Writing Safe Configuration (.env)...${NC}"

if [ -f "$PROJECT_ROOT/.env" ]; then
    TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
    cp "$PROJECT_ROOT/.env" "$PROJECT_ROOT/.env.backup_${TIMESTAMP}"
    echo -e "  --> Existing .env backed up to: ${GREEN}.env.backup_${TIMESTAMP}${NC}"
fi

cat <<EOF > "$PROJECT_ROOT/.env"
# Instance & Deployment Identification
HELPBOX_INSTANCE_NAME=${CFG_INSTANCE}
COMPOSE_PROJECT_NAME=${CFG_COMPOSE_PROJECT}
POSTGRES_CONTAINER_NAME=${CFG_CONTAINER}
POSTGRES_HOST_PORT=${CFG_PG_PORT}
POSTGRES_VOLUME_NAME=${CFG_VOLUME}
APP_PORT=${CFG_APP_PORT}

# Folder containing one direct subfolder per trial
TRIALS_DIR=${CFG_TRIALS_DIR}

# PostgreSQL + pgvector
POSTGRES_DB=${CFG_DB_NAME}
POSTGRES_USER=${CFG_DB_USER}
POSTGRES_PASSWORD=${CFG_DB_PASS}
DATABASE_URL=postgresql+psycopg://${CFG_DB_USER}:${CFG_DB_PASS}@localhost:${CFG_PG_PORT}/${CFG_DB_NAME}

# Primary Embedding Model (768 dimensions)
EMBEDDING_MODEL=${CFG_EMB_MODEL}
EMBEDDING_DIMENSION=768

# LLM Generation Provider
GENERATION_PROVIDER=ollama
OLLAMA_BASE_URL=${CFG_OLLAMA_URL}
OLLAMA_MODEL=${CFG_GEN_MODEL}
OLLAMA_CONTEXT_WINDOW=4096
OLLAMA_NUM_PREDICT=196
OLLAMA_KEEP_ALIVE=60m

# Optional Cloud Provider
GEMINI_API_KEY=
GEMINI_MODEL=gemini-3.8-flash

# Optional Private Company Endpoint
OPENAI_COMPATIBLE_BASE_URL=
OPENAI_COMPATIBLE_MODEL=${CFG_GEN_MODEL}
OPENAI_COMPATIBLE_API_KEY=not-needed

# Continuous Synchronization & RAG Settings
SYNC_ENABLED=true
SYNC_INTERVAL_SECONDS=120
RETRIEVAL_TOP_K=4
CHUNK_TOKEN_SIZE=800
CHUNK_TOKEN_OVERLAP=100
OCR_ENABLED=true
TABLE_EXTRACTION_ENABLED=true
EOF

echo -e "  --> Successfully written ${GREEN}.env${NC} (Password masked and securely saved)."

# ------------------------------------------------------------------------------
# STEP 4: Python Virtual Environment (.venv) & Dependencies
# ------------------------------------------------------------------------------
echo -e "\n${YELLOW}[Step 4/8] Setting Up Python Virtual Environment & Packages...${NC}"

if [ ! -d "$PROJECT_ROOT/.venv" ]; then
    echo -e "  --> Creating new virtual environment at .venv..."
    "$PYTHON_CMD" -m venv "$PROJECT_ROOT/.venv"
    echo -e "  --> Virtual environment ${GREEN}CREATED${NC}."
else
    echo -e "  --> Virtual environment already exists at ${GREEN}.venv${NC}."
fi

VENV_PYTHON="$PROJECT_ROOT/.venv/bin/python"
VENV_PIP="$PROJECT_ROOT/.venv/bin/pip"

echo -e "  --> Upgrading pip in .venv..."
"$VENV_PIP" install --quiet --upgrade pip

echo -e "  --> Installing verified application dependencies from requirements.txt..."
"$VENV_PIP" install --quiet -r "$PROJECT_ROOT/requirements.txt"
echo -e "  --> All Python packages ${GREEN}INSTALLED & VERIFIED${NC}."

# ------------------------------------------------------------------------------
# STEP 5: Docker & PostgreSQL/pgvector Service
# ------------------------------------------------------------------------------
echo -e "\n${YELLOW}[Step 5/8] Verifying Docker & PostgreSQL/pgvector Service...${NC}"

DOCKER_READY=false
if command -v docker >/dev/null 2>&1; then
    if docker info >/dev/null 2>&1; then
        DOCKER_READY=true
        echo -e "  --> Docker daemon: ${GREEN}ONLINE & READY${NC}"
    else
        echo -e "  ${RED}[!] Docker is installed, but the Docker daemon is not running.${NC}"
        echo -e "      Start the Docker service with: sudo systemctl start docker"
    fi
else
    echo -e "  ${RED}[!] Docker CLI was not found on your system.${NC}"
    echo -e "      Please install Docker and Docker Compose plugin:"
    echo -e "      https://docs.docker.com/engine/install/"
fi

if [ "$DOCKER_READY" = true ]; then
    # Check if container is already running
    if docker ps --filter "name=^/${CFG_CONTAINER}$" --filter "status=running" --format '{{.Names}}' | grep -q "^${CFG_CONTAINER}$"; then
        echo -e "  --> Container '${CFG_CONTAINER}' is already ${GREEN}RUNNING${NC} on port ${CFG_PG_PORT}."
    else
        echo -e "  --> Starting PostgreSQL service via Docker Compose..."
        docker compose up -d
        echo -e "  --> Waiting for PostgreSQL health check..."
        for i in {1..15}; do
            if docker inspect --format '{{.State.Health.Status}}' "${CFG_CONTAINER}" 2>/dev/null | grep -q "healthy"; then
                echo -e "  --> PostgreSQL container is ${GREEN}HEALTHY${NC}."
                break
            fi
            sleep 1
        done
    fi
else
    echo -e "  ${YELLOW}[*] Proceeding without Docker container startup. (Ensure PostgreSQL is running manually)${NC}"
fi

# ------------------------------------------------------------------------------
# STEP 6: Database Initialization / Restore
# ------------------------------------------------------------------------------
echo -e "\n${YELLOW}[Step 6/8] Database Schema Initialization & Backup Options...${NC}"

DB_ACTION="1"
if [ "$NON_INTERACTIVE" = false ] && [ -f "$PROJECT_ROOT/data/backups/latest.sql" ]; then
    echo -e "A previous database backup was detected at ${CYAN}data/backups/latest.sql${NC}."
    echo -e "  ${BOLD}[1] Fresh Database${NC}      (Initialize new tables and pgvector schema)"
    echo -e "  ${BOLD}[2] Restore from Backup${NC} (Restore existing document inventory and vector embeddings)"
    read -r -p "Enter choice [1]: " user_db_choice
    if [ "$user_db_choice" = "2" ]; then
        DB_ACTION="2"
    fi
fi

if [ "$DB_ACTION" = "2" ]; then
    echo -e "  --> Restoring database from backup..."
    if [ -f "$PROJECT_ROOT/scripts/restore_db.sh" ]; then
        bash "$PROJECT_ROOT/scripts/restore_db.sh" "$PROJECT_ROOT/data/backups/latest.sql"
    fi
else
    echo -e "  --> Initializing fresh database schema and pgvector extension..."
    if [ "$DOCKER_READY" = true ]; then
        "$VENV_PYTHON" -c "from app.db import init_db; init_db()" 2>/dev/null || true
        echo -e "  --> PostgreSQL schema and pgvector extension ${GREEN}INITIALIZED${NC}."
    fi
fi

# Check Trial Documents Directory
mkdir -p "${PROJECT_ROOT}/${CFG_TRIALS_DIR}"
TRIAL_COUNT=$(find "${PROJECT_ROOT}/${CFG_TRIALS_DIR}" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | wc -l || echo "0")
if [ "$TRIAL_COUNT" -eq 0 ]; then
    echo -e "  --> No trial folders found in ${CFG_TRIALS_DIR}."
    if [ "$NON_INTERACTIVE" = false ]; then
        read -r -p "Generate synthetic demo trial documents (Trial_101 & Trial_102)? [Y/n]: " gen_choice
        gen_choice="${gen_choice:-Y}"
    else
        gen_choice="Y"
    fi
    if [[ "$gen_choice" =~ ^[Yy]$ ]]; then
        "$VENV_PYTHON" "$PROJECT_ROOT/scripts/create_synthetic_trials.py"
        echo -e "  --> Synthetic trial folders ${GREEN}CREATED${NC}."
    fi
else
    echo -e "  --> Found ${GREEN}${TRIAL_COUNT} trial folders${NC} in ${CFG_TRIALS_DIR}."
fi

# ------------------------------------------------------------------------------
# STEP 7: Ollama Server & Local Model Cache Checks
# ------------------------------------------------------------------------------
echo -e "\n${YELLOW}[Step 7/8] Verifying Ollama Inference Server & Model Caches...${NC}"

OLLAMA_ONLINE=false
if curl -s "${CFG_OLLAMA_URL}/api/tags" >/dev/null 2>&1; then
    OLLAMA_ONLINE=true
    echo -e "  --> Ollama server: ${GREEN}ONLINE${NC} at ${CFG_OLLAMA_URL}"
else
    echo -e "  --> Ollama server is currently ${YELLOW}OFFLINE${NC} at ${CFG_OLLAMA_URL}."
    if command -v ollama >/dev/null 2>&1; then
        echo -e "      (Ollama CLI is installed. The dev launcher will automatically start it)."
    else
        echo -e "  ${YELLOW}[*] Ollama CLI is not yet installed on this machine.${NC}"
        echo -e "      To install Ollama, run: curl -fsSL https://ollama.com/install.sh | sh"
    fi
fi

# Check Ollama generation model cache
OLLAMA_MODEL_FOUND=false
if command -v ollama >/dev/null 2>&1; then
    if ollama list 2>/dev/null | grep -q "${CFG_GEN_MODEL}"; then
        OLLAMA_MODEL_FOUND=true
    fi
fi

if [ "$OLLAMA_MODEL_FOUND" = true ]; then
    echo -e "  --> Generation Model (${CFG_GEN_MODEL}): ${GREEN}CACHED ON DISK${NC}"
else
    echo -e "  --> Generation Model (${CFG_GEN_MODEL}, ~1.9 GB): ${YELLOW}NOT IN LOCAL CACHE${NC}"
    if command -v ollama >/dev/null 2>&1; then
        if [ "$NON_INTERACTIVE" = false ]; then
            read -r -p "  --> Would you like to download '${CFG_GEN_MODEL}' now? [y/N]: " pull_choice
            pull_choice="${pull_choice:-N}"
        else
            pull_choice="N"
        fi
        if [[ "$pull_choice" =~ ^[Yy]$ ]]; then
            echo -e "  --> Pulling model weights from Ollama registry..."
            ollama pull "${CFG_GEN_MODEL}"
            echo -e "  --> Model ${GREEN}DOWNLOADED & CACHED${NC}."
        else
            echo -e "  --> Model download deferred. You can download later with: ${CYAN}ollama pull ${CFG_GEN_MODEL}${NC}"
        fi
    fi
fi

# Check Hugging Face Embedding Model Cache
HF_CACHE_DIR="$HOME/.cache/huggingface/hub"
EMB_CLEAN_NAME="${CFG_EMB_MODEL//\//--}"
HF_MODEL_DIR="${HF_CACHE_DIR}/models--${EMB_CLEAN_NAME}"

if [ -d "$HF_MODEL_DIR" ]; then
    echo -e "  --> Clinical Embedding Model (${CFG_EMB_MODEL}): ${GREEN}CACHED ON DISK${NC}"
else
    echo -e "  --> Clinical Embedding Model (${CFG_EMB_MODEL}, ~570 MB): ${YELLOW}NOT YET CACHED${NC}"
    if [ "$NON_INTERACTIVE" = false ]; then
        read -r -p "  --> Pre-download embedding model now? [y/N]: " emb_choice
        emb_choice="${emb_choice:-N}"
    else
        emb_choice="N"
    fi
    if [[ "$emb_choice" =~ ^[Yy]$ ]]; then
        echo -e "  --> Downloading embedding model via sentence-transformers..."
        "$VENV_PYTHON" -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('${CFG_EMB_MODEL}')"
        echo -e "  --> Embedding model ${GREEN}CACHED${NC}."
    else
        echo -e "  --> Embedding model will be cached automatically upon first document indexing."
    fi
fi

# ------------------------------------------------------------------------------
# STEP 8: Summary & First Indexing Instructions
# ------------------------------------------------------------------------------
echo -e "\n${BLUE}================================================================${NC}"
echo -e "${GREEN}${BOLD}        HELPBOX SETUP COMPLETED SUCCESSFULLY!                    ${NC}"
echo -e "${BLUE}================================================================${NC}"

echo -e "\n${BOLD}Daily Operations Commands:${NC}"
echo -e "  ${CYAN}1. Start Everything Daily:${NC}  ./scripts/start_dev.sh"
echo -e "  ${CYAN}2. Check Service Health:${NC}    ./scripts/status.sh"
echo -e "  ${CYAN}3. Stop Safely:${NC}             ./scripts/stop_dev.sh"
echo -e "  ${CYAN}4. Backup Database:${NC}         ./scripts/backup_db.sh"
echo -e "  ${CYAN}5. Restore Database:${NC}        ./scripts/restore_db.sh"

echo -e "\n${BOLD}How to Perform Your First Indexing:${NC}"
echo -e "  1. Run: ${CYAN}./scripts/start_dev.sh${NC}"
echo -e "  2. Open browser to: ${CYAN}http://localhost:${CFG_APP_PORT}${NC}"
echo -e "  3. Click on a trial in the left sidebar (e.g., Trial_101)."
echo -e "  4. Click the ${BOLD}'AI Assistant'${NC} tab or ${BOLD}'Refresh'${NC} button."
echo -e "     Helpbox will automatically parse, chunk, and embed your trial PDFs into pgvector."
echo -e "  5. Ask clinical questions and receive evidence-grounded answers with citations!"
echo -e "${BLUE}================================================================${NC}\n"
