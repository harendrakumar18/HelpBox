# Helpbox — Production Linux VM Deployment Guide

This guide details the step-by-step procedure to deploy Helpbox on a dedicated company-managed Linux Virtual Machine (VM) without Kubernetes, Celery, Redis, or microservices.

---

## 1. System Requirements & Architecture Overview

```text
               Company Intranet / Clinical Users
                              │
                              ▼
        [NGINX / Reverse Proxy (SSL Termination 443 -> 8000)]
                              │
                              ▼
  ┌─────────────────────────────────────────────────────────────┐
  │ Company Linux VM (Ubuntu 22.04 / 24.04 LTS)                │
  │                                                             │
  │  1. systemd: helpbox.service                                │
  │     └── FastAPI Backend (app.main:app)                      │
  │           ├── Web Workspace (HTML5/CSS3/JS)                 │
  │           ├── Docling PDF Parser & BioClinical ModernBERT   │
  │           └── Background Async Scanner (120s scan loop)     │
  │                                                             │
  │  2. systemd: ollama.service (or Company vLLM Cluster)       │
  │     └── Qwen 3.5 2B Q4_K_M (Local offline inference)        │
  │                                                             │
  │  3. Docker Compose: helpbox-postgres                        │
  │     └── PostgreSQL 16 + pgvector 0.8.7 (Port 5432)          │
  │                                                             │
  │  4. Read-Only Storage Mount: /mnt/company_trials (ro)       │
  │     └── Direct-child folders per trial (read-only)          │
  └─────────────────────────────────────────────────────────────┘
```

### Recommended Virtual Machine Specifications
| Resource | Minimum | Recommended Production |
|---|---|---|
| **Operating System** | Ubuntu 22.04 LTS / 24.04 LTS (x86_64) | Ubuntu 24.04 LTS (x86_64) |
| **vCPU** | 2 vCPU | 4–8 vCPU |
| **RAM** | 8 GB | 16 GB (leaves headroom for OS, Postgres, PyTorch, & LLM) |
| **Disk Storage** | 30 GB SSD | 60–100 GB NVMe (for vector embeddings & model caches) |
| **Network** | Intranet Only (1 Gbps LAN) | Isolated clinical VLAN (No public internet required) |

---

## 2. Step 1: Create Dedicated Linux Service Account

Never run Helpbox as `root`. Create an unprivileged service account:
```bash
sudo useradd -m -s /bin/bash helpbox
sudo usermod -aG docker helpbox
sudo mkdir -p /opt/helpbox /mnt/company_trials /var/log/helpbox
sudo chown -R helpbox:helpbox /opt/helpbox /var/log/helpbox
```

---

## 3. Step 2: Mount Company Document Storage in Read-Only Mode

Mount the company's shared network drive to `/mnt/company_trials` with the `ro` (read-only) flag in `/etc/fstab`:

### Option A: Windows File Share (SMB/CIFS)
Create credentials file `/etc/helpbox-cifs.cred`:
```ini
username=helpbox_svc
password=SecureCompanyPasswordHere
domain=COMPANY_DOMAIN
```
Secure permissions:
```bash
sudo chmod 600 /etc/helpbox-cifs.cred
```
Add to `/etc/fstab`:
```text
//company-fileserver.internal/trials /mnt/company_trials cifs credentials=/etc/helpbox-cifs.cred,ro,file_mode=0440,dir_mode=0550,iocharset=utf8 0 0
```
Mount and test:
```bash
sudo mount -a
ls -la /mnt/company_trials
# Confirm write operations are blocked:
touch /mnt/company_trials/test.txt # Must fail: "Read-only file system"
```

### Option B: Linux / TrueNAS (NFS)
Add to `/etc/fstab`:
```text
company-nas.internal:/exports/trials /mnt/company_trials nfs ro,nosuid,hard,intr 0 0
```
Mount and test:
```bash
sudo mount -a
```

---

## 4. Step 3: Deploy Application & Python Virtual Environment

Switch to the `helpbox` user:
```bash
sudo -u helpbox -i
cd /opt/helpbox
git clone <company_git_repo_url> .
cd helpbox_simple_agent_pack_v3

# Create and activate Python virtual environment
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

---

## 5. Step 4: Configure Production Database (PostgreSQL 16 + pgvector)

Start the containerized PostgreSQL service via Docker Compose:
```bash
cd /opt/helpbox/helpbox_simple_agent_pack_v3
docker compose up -d
docker compose ps
# Verify container is healthy:
docker inspect --format='{{json .State.Health.Status}}' helpbox-postgres
```

---

## 6. Step 7: Configure Environment File (`.env`)

Create `/opt/helpbox/helpbox_simple_agent_pack_v3/.env` (mode `0600`):
```bash
cat << 'EOF' > /opt/helpbox/helpbox_simple_agent_pack_v3/.env
# Document Storage Root (Read-only mounted network path)
TRIALS_DIR=/mnt/company_trials

# Database Connection (PostgreSQL 16 + pgvector)
DATABASE_URL=postgresql+psycopg://helpbox:ChangeToStrongRandomPasswordHere@127.0.0.1:5432/helpbox
POSTGRES_PASSWORD=ChangeToStrongRandomPasswordHere

# Embedding Configuration (BioClinical ModernBERT - 768 dimensions)
EMBEDDING_MODEL=NeuML/bioclinical-modernbert-base-embeddings
EMBEDDING_DIMENSION=768

# Generation Provider (Default: local ollama, or company private vLLM endpoint)
GENERATION_PROVIDER=ollama
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=qwen3.5:2b-q4_K_M
OLLAMA_CONTEXT_WINDOW=4096
OLLAMA_KEEP_ALIVE=60m

# Continuous Background Synchronization
SYNC_ENABLED=true
SYNC_INTERVAL_SECONDS=120

# Model Cache Directories on VM Local Disk
HF_HOME=/opt/helpbox/cache/huggingface
OLLAMA_MODELS=/opt/helpbox/cache/ollama
EOF

chmod 600 /opt/helpbox/helpbox_simple_agent_pack_v3/.env
```

---

## 7. Step 6: Systemd Process Management

Configure `systemd` to manage the services with automatic restarts.

### 1. Ollama Inference Service (`/etc/systemd/system/ollama.service`)
```ini
[Unit]
Description=Ollama Local LLM Inference Engine
After=network.target

[Service]
Type=simple
User=helpbox
Group=helpbox
Environment="OLLAMA_MODELS=/opt/helpbox/cache/ollama"
Environment="OLLAMA_HOST=127.0.0.1:11434"
Environment="OLLAMA_KEEP_ALIVE=60m"
ExecStart=/usr/local/bin/ollama serve
Restart=always
RestartSec=5s
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
```

### 2. Helpbox Backend Application Service (`/etc/systemd/system/helpbox.service`)
```ini
[Unit]
Description=Helpbox Clinical RAG Assistant Backend
After=network.target ollama.service

[Service]
Type=simple
User=helpbox
Group=helpbox
WorkingDirectory=/opt/helpbox/helpbox_simple_agent_pack_v3
EnvironmentFile=/opt/helpbox/helpbox_simple_agent_pack_v3/.env
Environment="PATH=/opt/helpbox/helpbox_simple_agent_pack_v3/.venv/bin:/usr/local/bin:/usr/bin"
ExecStart=/opt/helpbox/helpbox_simple_agent_pack_v3/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
Restart=always
RestartSec=5s
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
```

### Enable and Start Services
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now ollama.service
sudo systemctl enable --now helpbox.service

# Check service status:
sudo systemctl status helpbox.service
sudo systemctl status ollama.service
```

---

## 8. Step 7: NGINX Reverse Proxy & HTTPS Configuration

Install and configure NGINX to terminate HTTPS (SSL) on port 443:
```nginx
server {
    listen 80;
    server_name helpbox.company.internal;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name helpbox.company.internal;

    ssl_certificate /etc/ssl/certs/company_wildcard.crt;
    ssl_certificate_key /etc/ssl/private/company_wildcard.key;

    # Allow iframe embedding inside company intranet portal
    add_header X-Frame-Options "ALLOW-FROM https://clinical.company.internal" always;
    add_header Content-Security-Policy "frame-ancestors 'self' https://clinical.company.internal" always;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # SSE Real-time Streaming Buffering Disabled
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 300s;
    }
}
```

---

## 9. Step 8: Automated Database Backup Cron Job

Configure daily automated SQL backups using `scripts/backup_db.sh`:
```bash
# Add to helpbox user crontab
crontab -e -u helpbox
```
Add the cron line (runs daily at 02:00 AM):
```cron
0 2 * * * /opt/helpbox/helpbox_simple_agent_pack_v3/scripts/backup_db.sh >> /var/log/helpbox/backup.log 2>&1
```

---

## 10. Operational Runbook & Disaster Recovery

### Quick Health Diagnostic
Run the built-in diagnostic script at any time:
```bash
cd /opt/helpbox/helpbox_simple_agent_pack_v3
./scripts/status.sh
```

### Restarting Services
```bash
# Restart Backend & In-process Scanner
sudo systemctl restart helpbox.service

# Restart Local LLM
sudo systemctl restart ollama.service

# Restart Database Container
docker compose restart
```

### Restoring Database from Backup
In case of VM corruption or migration to a new host:
```bash
cd /opt/helpbox/helpbox_simple_agent_pack_v3
./scripts/restore_db.sh data/backups/latest.sql
```
After restoring, the background scanner will automatically run on the next cycle, verify all hashes against the storage mount, and confirm that all trial vectors match the documents on disk.
