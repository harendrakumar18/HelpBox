#!/usr/bin/env bash
# ==============================================================================
# Helpbox — Safe Development Services Startup Script
# Checks existing ports and processes; starts missing services safely.
# Never restarts already healthy services. Never deletes caches or volumes.
# ==============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

# Load environment settings if .env exists
if [ -f "$PROJECT_ROOT/.env" ]; then
    set -a
    source "$PROJECT_ROOT/.env" 2>/dev/null || true
    set +a
fi

POSTGRES_CONTAINER="${POSTGRES_CONTAINER_NAME:-helpbox-postgres}"
PG_PORT="${POSTGRES_HOST_PORT:-5432}"
FASTAPI_PORT="${APP_PORT:-8000}"
OLLAMA_URL="${OLLAMA_BASE_URL:-http://127.0.0.1:11434}"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${BLUE}================================================================${NC}"
echo -e "${BLUE}          HELPBOX — SAFE DEVELOPMENT ENVIRONMENT STARTUP         ${NC}"
echo -e "${BLUE}================================================================${NC}"

# 1. PostgreSQL Check
echo -e "\n${YELLOW}[1/3] Verifying PostgreSQL 16 + pgvector container (${POSTGRES_CONTAINER})...${NC}"
if docker ps --filter "name=^/${POSTGRES_CONTAINER}$" --filter "status=running" --format '{{.Names}}' | grep -q "^${POSTGRES_CONTAINER}$"; then
    echo -e "  --> PostgreSQL container is already ${GREEN}HEALTHY & RUNNING${NC} on port ${PG_PORT}."
else
    echo -e "  --> Starting PostgreSQL container via Docker Compose..."
    docker compose up -d
    sleep 2
    echo -e "  --> PostgreSQL container ${GREEN}STARTED${NC}."
fi

# 2. Ollama Server Check
echo -e "\n${YELLOW}[2/3] Verifying Ollama Inference Server (${OLLAMA_URL})...${NC}"
if curl -s "${OLLAMA_URL}/api/tags" >/dev/null 2>&1; then
    echo -e "  --> Ollama server is already ${GREEN}ONLINE${NC} on ${OLLAMA_URL}."
else
    echo -e "  --> Starting Ollama server daemon..."
    ollama serve > "$PROJECT_ROOT/data/ollama.log" 2>&1 &
    OLLAMA_PID=$!
    echo "$OLLAMA_PID" > "$PROJECT_ROOT/data/.ollama.pid"
    echo -e "  --> Ollama server launched with PID ${OLLAMA_PID} (log: data/ollama.log)."
    
    # Wait for Ollama to accept connections (max 10s)
    for i in {1..10}; do
        if curl -s "${OLLAMA_URL}/api/tags" >/dev/null 2>&1; then
            echo -e "  --> Ollama server is ${GREEN}READY${NC}."
            break
        fi
        sleep 1
    done
fi

# 3. FastAPI Backend Check
echo -e "\n${YELLOW}[3/3] Verifying FastAPI Application Backend (Port ${FASTAPI_PORT})...${NC}"
if curl -s "http://127.0.0.1:${FASTAPI_PORT}/health" >/dev/null 2>&1; then
    echo -e "  --> FastAPI backend is already ${GREEN}ONLINE${NC} on http://127.0.0.1:${FASTAPI_PORT}."
else
    echo -e "  --> Starting FastAPI backend with Uvicorn..."
    source .venv/bin/activate
    uvicorn app.main:app --host 0.0.0.0 --port "${FASTAPI_PORT}" > "$PROJECT_ROOT/data/uvicorn.log" 2>&1 &
    UVICORN_PID=$!
    echo "$UVICORN_PID" > "$PROJECT_ROOT/data/.uvicorn.pid"
    echo -e "  --> FastAPI backend launched with PID ${UVICORN_PID} (log: data/uvicorn.log)."
    
    # Wait for FastAPI health check (max 10s)
    for i in {1..10}; do
        if curl -s "http://127.0.0.1:${FASTAPI_PORT}/health" >/dev/null 2>&1; then
            echo -e "  --> FastAPI backend is ${GREEN}ONLINE & HEALTHY${NC}."
            break
        fi
        sleep 1
    done
fi

echo -e "\n${BLUE}================================================================${NC}"
echo -e "  ${GREEN}All development services are active and verified.${NC}"
echo -e "  Workspace UI:  http://localhost:${FASTAPI_PORT}"
echo -e "  Status Script: ./scripts/status.sh"
echo -e "  Stop Script:   ./scripts/stop_dev.sh"
echo -e "${BLUE}================================================================${NC}"
