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
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
BACKUP_FILE="${BACKUP_DIR}/helpbox_backup_${TIMESTAMP}.sql"
LATEST_FILE="${BACKUP_DIR}/latest.sql"

mkdir -p "${BACKUP_DIR}"

echo "[*] Creating database backup from container '${POSTGRES_CONTAINER}' to ${BACKUP_FILE}..."
docker exec "${POSTGRES_CONTAINER}" pg_dump -U "${PG_USER}" -d "${PG_DB}" > "${BACKUP_FILE}"
cp "${BACKUP_FILE}" "${LATEST_FILE}"

echo "[+] Backup complete: ${BACKUP_FILE} ($(du -h "${BACKUP_FILE}" | cut -f1))"
echo "[+] Updated latest: ${LATEST_FILE}"
