#!/usr/bin/env bash
set -euo pipefail

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
BACKUP_DIR="${PROJECT_ROOT}/data/backups"
RESTORE_FILE="${1:-${BACKUP_DIR}/latest.sql}"

if [ ! -f "${RESTORE_FILE}" ]; then
    echo "[-] Backup file not found: ${RESTORE_FILE}"
    exit 1
fi

echo "[*] Restoring database in container '${POSTGRES_CONTAINER}' from ${RESTORE_FILE}..."
docker exec -i "${POSTGRES_CONTAINER}" psql -U "${PG_USER}" -d "${PG_DB}" < "${RESTORE_FILE}"
echo "[+] Database restore complete."
