#!/usr/bin/env bash
set -e

# ==============================================================================
# Helpbox — Multi-Service Status & Diagnostic Verification
# ==============================================================================

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Load environment settings if .env exists
if [ -f "$PROJECT_ROOT/.env" ]; then
    set -a
    source "$PROJECT_ROOT/.env" 2>/dev/null || true
    set +a
fi

POSTGRES_CONTAINER="${POSTGRES_CONTAINER_NAME:-helpbox-postgres}"
PG_USER="${POSTGRES_USER:-helpbox}"
PG_DB="${POSTGRES_DB:-helpbox}"
PG_PORT="${POSTGRES_HOST_PORT:-5432}"
FASTAPI_PORT="${APP_PORT:-8000}"
OLLAMA_URL="${OLLAMA_BASE_URL:-http://127.0.0.1:11434}"
MODEL_NAME="${OLLAMA_MODEL:-qwen3.5:2b-q4_K_M}"

echo -e "${BLUE}================================================================${NC}"
echo -e "${BLUE}       HELPBOX CLINICAL RAG — SERVICE STATUS & HEALTH CHECK      ${NC}"
echo -e "${BLUE}================================================================${NC}"

# 1. System Resources
echo -e "\n${YELLOW}[1/5] Host System Resources (Codespaces / Linux)${NC}"
echo -n "  Memory: "
free -h | awk '/^Mem:/ {print "Used: "$3" / Total: "$2" (Free: "$4", Available: "$7")"}'
echo -n "  CPU Load: "
uptime | awk -F'load average:' '{print $2}' | sed 's/^ //'
echo -n "  Disk (/workspaces): "
df -h /workspaces 2>/dev/null | awk 'NR==2 {print "Used: "$3" / Total: "$2" ("$5" used, "$4" free)"}' || df -h . | awk 'NR==2 {print "Used: "$3" / Total: "$2" ("$5" used, "$4" free)"}'

# 2. Terminal 1: PostgreSQL 16 + pgvector Service
echo -e "\n${YELLOW}[2/5] Terminal 1 Service — PostgreSQL 16 + pgvector (Container: ${POSTGRES_CONTAINER})${NC}"
if docker ps --filter "name=^/${POSTGRES_CONTAINER}$" --filter "status=running" --format '{{.Names}}' | grep -q "^${POSTGRES_CONTAINER}$"; then
    PG_STATUS=$(docker inspect -f '{{.State.Status}} (health: {{.State.Health.Status}})' "${POSTGRES_CONTAINER}" 2>/dev/null || echo "running")
    echo -e "  Container State: ${GREEN}${PG_STATUS}${NC} on port ${PG_PORT}"
    
    # Check live SQL connectivity and table counts
    if docker exec "${POSTGRES_CONTAINER}" psql -U "${PG_USER}" -d "${PG_DB}" -c "SELECT 1;" >/dev/null 2>&1; then
        echo -e "  SQL Connectivity: ${GREEN}OK (PostgreSQL 16 + pgvector)${NC}"
        INV_COUNT=$(docker exec "${POSTGRES_CONTAINER}" psql -U "${PG_USER}" -d "${PG_DB}" -t -c "SELECT COUNT(*) FROM document_inventory;" 2>/dev/null | tr -d ' ' || echo "0")
        VEC_COUNT=$(docker exec "${POSTGRES_CONTAINER}" psql -U "${PG_USER}" -d "${PG_DB}" -t -c "SELECT COUNT(*) FROM langchain_pg_embedding;" 2>/dev/null | tr -d ' ' || echo "0")
        METRIC_COUNT=$(docker exec "${POSTGRES_CONTAINER}" psql -U "${PG_USER}" -d "${PG_DB}" -t -c "SELECT COUNT(*) FROM performance_metrics;" 2>/dev/null | tr -d ' ' || echo "0")
        echo -e "  Document Inventory: ${GREEN}${INV_COUNT} records${NC}"
        echo -e "  Clinical Vector Embeddings: ${GREEN}${VEC_COUNT} chunks${NC}"
        echo -e "  Performance Metrics Logged: ${GREEN}${METRIC_COUNT} stage durations${NC}"
    else
        echo -e "  SQL Connectivity: ${RED}FAILED${NC} (PostgreSQL not accepting connections)"
    fi
else
    echo -e "  Container State: ${RED}NOT RUNNING${NC}"
    echo -e "  Action needed: Run 'docker compose up -d' in Terminal 1."
fi

# 3. Terminal 2: Ollama Local Inference Server
echo -e "\n${YELLOW}[3/5] Terminal 2 Service — Ollama Server (${OLLAMA_URL})${NC}"
if curl -s "${OLLAMA_URL}/api/tags" >/dev/null 2>&1; then
    echo -e "  Server API: ${GREEN}OK (${OLLAMA_URL})${NC}"
    MODELS=$(curl -s "${OLLAMA_URL}/api/tags" | grep -o '"name":"[^"]*"' | tr '\n' ' ' | sed 's/"name"://g')
    echo -e "  Available Models: ${GREEN}${MODELS}${NC}"
    if echo "$MODELS" | grep -q "${MODEL_NAME}"; then
        echo -e "  Model (${MODEL_NAME}): ${GREEN}AVAILABLE & VERIFIED${NC}"
    else
        echo -e "  Model (${MODEL_NAME}): ${RED}NOT FOUND${NC} (run 'ollama pull ${MODEL_NAME}')"
    fi
    ACTIVE_MODEL=$(ollama ps 2>/dev/null | awk 'NR==2 {print $1" (Size: "$3", Context: "$5")"}' || echo "")
    if [ -n "$ACTIVE_MODEL" ]; then
        echo -e "  Active in RAM: ${GREEN}${ACTIVE_MODEL}${NC}"
    else
        echo -e "  Active in RAM: ${YELLOW}None (model idle/unloaded)${NC}"
    fi
else
    echo -e "  Server API: ${RED}NOT RUNNING${NC} on ${OLLAMA_URL}"
    echo -e "  Action needed: Run 'ollama serve' in Terminal 2."
fi

# 4. Terminal 3: FastAPI Backend & Continuous Sync
echo -e "\n${YELLOW}[4/5] Terminal 3 Service — FastAPI Application & Continuous Scanner (Port ${FASTAPI_PORT})${NC}"
if curl -s "http://127.0.0.1:${FASTAPI_PORT}/health" >/dev/null 2>&1; then
    HEALTH_JSON=$(curl -s "http://127.0.0.1:${FASTAPI_PORT}/health")
    echo -e "  Backend API: ${GREEN}ONLINE (http://127.0.0.1:${FASTAPI_PORT})${NC}"
    SYNC_STATUS=$(curl -s "http://127.0.0.1:${FASTAPI_PORT}/api/sync/status" 2>/dev/null || echo "{}")
    SYNC_RUNNING=$(echo "$SYNC_STATUS" | grep -o '"is_running":[^,]*' | cut -d: -f2 | tr -d ' ')
    SCAN_COUNT=$(echo "$SYNC_STATUS" | grep -o '"scan_count":[^,]*' | cut -d: -f2 | tr -d ' ')
    INTERVAL=$(echo "$SYNC_STATUS" | grep -o '"interval_seconds":[^,]*' | cut -d: -f2 | tr -d ' ')
    LAST_SCAN=$(echo "$SYNC_STATUS" | grep -o '"last_scan_time":[^,]*' | cut -d: -f2- | tr -d ' "')
    
    if [ "$SYNC_RUNNING" = "true" ]; then
        echo -e "  Continuous Background Sync: ${GREEN}ACTIVE${NC} (interval: ${INTERVAL}s, cycles: ${SCAN_COUNT})"
        echo -e "  Last Completed Scan: ${GREEN}${LAST_SCAN:-just started}${NC}"
    else
        echo -e "  Continuous Background Sync: ${YELLOW}IDLE / DISABLED${NC}"
    fi
else
    echo -e "  Backend API: ${RED}NOT RUNNING${NC} on 127.0.0.1:${FASTAPI_PORT}"
    echo -e "  Action needed: Run 'uvicorn app.main:app --host 0.0.0.0 --port ${FASTAPI_PORT}' or './scripts/start_dev.sh'."
fi

# 5. Model Weights On-Disk Cache
echo -e "\n${YELLOW}[5/5] Cached Model Footprint on Disk${NC}"
if [ -d "$HOME/.cache/huggingface/hub" ]; then
    HF_SIZE=$(du -sh "$HOME/.cache/huggingface/hub" 2>/dev/null | cut -f1)
    echo -e "  Hugging Face Models (ModernBERT + Docling Layout): ${GREEN}${HF_SIZE}${NC} (~/.cache/huggingface/hub)"
fi
if [ -d "$HOME/.ollama/models" ]; then
    OLLAMA_SIZE=$(du -sh "$HOME/.ollama/models" 2>/dev/null | cut -f1)
    echo -e "  Ollama Models (Qwen 3.5 2B GGUF): ${GREEN}${OLLAMA_SIZE}${NC} (~/.ollama/models)"
fi

echo -e "\n${BLUE}================================================================${NC}"
