#!/usr/bin/env bash
set -e

# ==============================================================================
# Helpbox — Developer Environment Startup Helper
# ==============================================================================

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_ROOT"

echo -e "${BLUE}================================================================${NC}"
echo -e "${BLUE}       STARTING HELPBOX DEVELOPMENT ENVIRONMENT                 ${NC}"
echo -e "${BLUE}================================================================${NC}"

# Check Virtual Environment
if [ -f "$PROJECT_ROOT/.venv/bin/activate" ]; then
    source "$PROJECT_ROOT/.venv/bin/activate"
    echo -e "${GREEN}[+] Activated virtual environment: .venv${NC}"
else
    echo -e "${RED}[!] Virtual environment .venv not found. Run python3 -m venv .venv && pip install -r requirements.txt${NC}"
    exit 1
fi

# Step 1: PostgreSQL Check / Startup (Terminal 1)
echo -e "\n${YELLOW}[Step 1/3] Checking PostgreSQL Container (helpbox-postgres)...${NC}"
if ! docker ps --filter "name=helpbox-postgres" --filter "status=running" | grep -q helpbox-postgres; then
    echo "Starting PostgreSQL container via docker compose..."
    docker compose up -d
    sleep 2
fi
echo -e "${GREEN}[+] PostgreSQL container is running on port 5432.${NC}"

# Step 2: Ollama Check (Terminal 2)
echo -e "\n${YELLOW}[Step 2/3] Checking Ollama Local LLM Server...${NC}"
if ! curl -s http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
    echo -e "${YELLOW}[*] Ollama server is not running on 127.0.0.1:11434.${NC}"
    echo -e "${YELLOW}[*] Starting Ollama server in background...${NC}"
    ollama serve > /tmp/ollama_serve.log 2>&1 &
    sleep 3
fi
echo -e "${GREEN}[+] Ollama server is active on http://127.0.0.1:11434.${NC}"

# Step 3: Run FastAPI Application (Terminal 3)
echo -e "\n${YELLOW}[Step 3/3] Launching FastAPI Backend & Continuous Sync...${NC}"
echo -e "${GREEN}[+] Serving clinical workspace UI on http://127.0.0.1:8000${NC}"
echo -e "${GREEN}[+] Press Ctrl+C to stop FastAPI server.${NC}\n"

exec uvicorn app.main:app --host 0.0.0.0 --port 8000
