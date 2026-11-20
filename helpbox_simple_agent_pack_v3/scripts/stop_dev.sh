#!/usr/bin/env bash
# ==============================================================================
# Helpbox — Safe Development Services Shutdown Script
# Gracefully stops application-owned processes without terminating databases
# or deleting any persistent data/caches.
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

FASTAPI_PORT="${APP_PORT:-8000}"

YELLOW='\033[1;33m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${BLUE}================================================================${NC}"
echo -e "${BLUE}          HELPBOX — SAFE DEVELOPMENT SERVICES SHUTDOWN           ${NC}"
echo -e "${BLUE}================================================================${NC}"

# 1. Stop FastAPI Uvicorn process if tracked or running on port ${FASTAPI_PORT}
echo -e "\n${YELLOW}[1/3] Stopping FastAPI Uvicorn backend (Port ${FASTAPI_PORT})...${NC}"
if [ -f "$PROJECT_ROOT/data/.uvicorn.pid" ]; then
    PID=$(cat "$PROJECT_ROOT/data/.uvicorn.pid")
    if kill -0 "$PID" 2>/dev/null; then
        CMD=$(ps -p "$PID" -o args= 2>/dev/null || echo "")
        if echo "$CMD" | grep -q "uvicorn"; then
            echo -e "  --> Gracefully stopping tracked Uvicorn process (PID: $PID)..."
            kill -TERM "$PID" 2>/dev/null || true
            sleep 1
        fi
    fi
    rm -f "$PROJECT_ROOT/data/.uvicorn.pid"
fi

# Fallback: check if port is still listening
PIDS_PORT=$(lsof -ti ":${FASTAPI_PORT}" 2>/dev/null || true)
if [ -n "$PIDS_PORT" ]; then
    for p in $PIDS_PORT; do
        CMD=$(ps -p "$p" -o args= 2>/dev/null || echo "")
        if echo "$CMD" | grep -q "uvicorn"; then
            echo -e "  --> Stopping Uvicorn process on port ${FASTAPI_PORT} (PID: $p)..."
            kill -TERM "$p" 2>/dev/null || true
        fi
    done
fi
echo -e "  --> FastAPI backend ${GREEN}STOPPED${NC}."

# 2. Ollama model unloading / stopping (optional)
if [ "$1" = "--all" ]; then
    echo -e "\n${YELLOW}[2/3] Stopping Ollama server (--all flag passed)...${NC}"
    if [ -f "$PROJECT_ROOT/data/.ollama.pid" ]; then
        PID=$(cat "$PROJECT_ROOT/data/.ollama.pid")
        if kill -0 "$PID" 2>/dev/null; then
            kill -TERM "$PID" 2>/dev/null || true
        fi
        rm -f "$PROJECT_ROOT/data/.ollama.pid"
    fi
    echo -e "  --> Ollama server ${GREEN}STOPPED${NC}."
else
    echo -e "\n${YELLOW}[2/3] Checking Ollama server...${NC}"
    echo -e "  --> Keeping Ollama server online for fast local inference."
    echo -e "      (Pass '--all' if you wish to shut down Ollama as well)."
fi

# 3. PostgreSQL Docker Service
echo -e "\n${YELLOW}[3/3] Checking PostgreSQL container...${NC}"
echo -e "  --> Preserving PostgreSQL Docker container and persistent data volume."
echo -e "      (To stop container without deleting data: 'docker compose stop')."

echo -e "\n${BLUE}================================================================${NC}"
echo -e "  ${GREEN}FastAPI application processes stopped cleanly.${NC}"
echo -e "  Status Script: ./scripts/status.sh"
echo -e "  Start Script:  ./scripts/start_dev.sh"
echo -e "${BLUE}================================================================${NC}"
