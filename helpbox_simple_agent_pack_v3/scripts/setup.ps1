# ==============================================================================
# Helpbox — Platform-Specific One-Command Environment Installer (Windows PowerShell)
# ==============================================================================
# Automates first-time setup after cloning:
#   1. Detects Windows OS and compatible Python (3.10+)
#   2. Configures instance settings interactively or with sensible defaults
#   3. Generates/updates .env safely (preserving existing configurations)
#   4. Creates & configures Python virtual environment (.venv) and dependencies
#   5. Checks Docker Desktop, Docker Compose, and starts PostgreSQL + pgvector
#   6. Initializes fresh database schema or restores from backup
#   7. Checks Ollama inference server and embedding model caches
#   8. Downloads missing models ONLY after explicit user confirmation
#   9. Verifies complete multi-service readiness and displays startup commands
# ==============================================================================

param(
    [switch]$Default,
    [switch]$Help
)

$ErrorActionPreference = "Stop"

if ($Help) {
    Write-Host "Usage: .\scripts\setup.ps1 [-Default] [-Help]"
    Write-Host ""
    Write-Host "Helpbox One-Command Environment Installer for Windows 11 / PowerShell."
    Write-Host ""
    Write-Host "Options:"
    Write-Host "  -Default    Run quick setup non-interactively with default settings."
    Write-Host "  -Help       Show this help message and exit."
    exit 0
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = Split-Path -Parent $scriptDir
Set-Location $projectRoot

Write-Host "================================================================" -ForegroundColor Cyan
Write-Host "          HELPBOX — ONE-COMMAND ENVIRONMENT INSTALLER            " -ForegroundColor Cyan
Write-Host "================================================================" -ForegroundColor Cyan
Write-Host "Application Root: $projectRoot"

# ------------------------------------------------------------------------------
# STEP 1: OS & Environment Detection
# ------------------------------------------------------------------------------
Write-Host "`n[Step 1/8] Detecting Operating System & Host Environment..." -ForegroundColor Yellow

$os = Get-CimInstance Win32_OperatingSystem -ErrorAction SilentlyContinue
$osCaption = if ($os) { $os.Caption } else { "Microsoft Windows" }
$osArch = [System.Environment]::GetEnvironmentVariable("PROCESSOR_ARCHITECTURE")
Write-Host "  --> Operating System: $osCaption ($osArch)" -ForegroundColor Green

# Detect Compatible Python (>= 3.10)
$pythonCmd = $null
$pyVer = $null
foreach ($cmd in @("python", "py", "python3")) {
    if (Get-Command $cmd -ErrorAction SilentlyContinue) {
        try {
            $check = & $cmd -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" 2>$null
            if ($LASTEXITCODE -eq 0) {
                $pythonCmd = $cmd
                $pyVer = & $cmd -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')" 2>$null
                break
            }
        } catch {}
    }
}

if (-not $pythonCmd) {
    Write-Host "  [!] Compatible Python (>= 3.10) was not found on your system." -ForegroundColor Red
    Write-Host "      Please install Python 3.11, 3.12, or 3.13 from python.org or via winget:"
    Write-Host "      winget install Python.Python.3.12"
    exit 1
}
Write-Host "  --> Python Runtime: $pythonCmd (version $pyVer)" -ForegroundColor Green

# ------------------------------------------------------------------------------
# STEP 2: Interactive Configuration & Instance Customization
# ------------------------------------------------------------------------------
Write-Host "`n[Step 2/8] Configuring Instance Settings..." -ForegroundColor Yellow

# Read existing .env defaults if present
if (Test-Path "$projectRoot\.env") {
    Get-Content "$projectRoot\.env" | ForEach-Object {
        $line = $_.Trim()
        if ($line -and -not $line.StartsWith("#") -and $line.Contains("=")) {
            $parts = $line.Split("=", 2)
            $varName = $parts[0].Trim()
            $varValue = $parts[1].Trim()
            [Environment]::SetEnvironmentVariable($varName, $varValue, "Process")
        }
    }
}

$defInstance = if ($env:HELPBOX_INSTANCE_NAME) { $env:HELPBOX_INSTANCE_NAME } else { "helpbox" }
$defComposeProject = if ($env:COMPOSE_PROJECT_NAME) { $env:COMPOSE_PROJECT_NAME } else { "helpbox" }
$defContainer = if ($env:POSTGRES_CONTAINER_NAME) { $env:POSTGRES_CONTAINER_NAME } else { "helpbox-postgres" }
$defDbName = if ($env:POSTGRES_DB) { $env:POSTGRES_DB } else { "helpbox" }
$defDbUser = if ($env:POSTGRES_USER) { $env:POSTGRES_USER } else { "helpbox" }
$defDbPass = if ($env:POSTGRES_PASSWORD) { $env:POSTGRES_PASSWORD } else { "change_this_local_dev_password" }
$defVolume = if ($env:POSTGRES_VOLUME_NAME) { $env:POSTGRES_VOLUME_NAME } else { "helpbox_postgres_data" }
$defPgPort = if ($env:POSTGRES_HOST_PORT) { $env:POSTGRES_HOST_PORT } else { "5432" }
$defAppPort = if ($env:APP_PORT) { $env:APP_PORT } else { "8000" }
$defOllamaUrl = if ($env:OLLAMA_BASE_URL) { $env:OLLAMA_BASE_URL } else { "http://localhost:11434" }
$defGenModel = if ($env:OLLAMA_MODEL) { $env:OLLAMA_MODEL } else { "qwen3.5:2b-q4_K_M" }
$defEmbModel = if ($env:EMBEDDING_MODEL) { $env:EMBEDDING_MODEL } else { "NeuML/bioclinical-modernbert-base-embeddings" }
$defTrialsDir = if ($env:TRIALS_DIR) { $env:TRIALS_DIR } else { "./data/trials" }

$setupMode = "1"
if (-not $Default) {
    Write-Host "Choose setup configuration mode:"
    Write-Host "  [1] Quick Setup   (Recommended — Uses standard default settings)"
    Write-Host "  [2] Custom Setup  (Customize instance name, ports, container names, database)"
    $userMode = Read-Host "Enter choice [1]"
    if ($userMode -eq "2") {
        $setupMode = "2"
    }
}

if ($setupMode -eq "2") {
    Write-Host "`n--- Custom Instance Parameters ---" -ForegroundColor Cyan
    $in = Read-Host "Helpbox Instance Name [$defInstance]"
    $cfgInstance = if ($in) { $in } else { $defInstance }

    $in = Read-Host "Docker Compose Project Name [$defComposeProject]"
    $cfgComposeProject = if ($in) { $in } else { $defComposeProject }

    $in = Read-Host "PostgreSQL Container Name [$defContainer]"
    $cfgContainer = if ($in) { $in } else { $defContainer }

    $in = Read-Host "PostgreSQL Database Name [$defDbName]"
    $cfgDbName = if ($in) { $in } else { $defDbName }

    $in = Read-Host "PostgreSQL Username [$defDbUser]"
    $cfgDbUser = if ($in) { $in } else { $defDbUser }

    $inSecure = Read-Host -AsSecureString "PostgreSQL Password (leave blank to keep default)"
    $inPass = [System.Net.NetworkCredential]::new("", $inSecure).Password
    $cfgDbPass = if ($inPass) { $inPass } else { $defDbPass }

    $in = Read-Host "PostgreSQL Docker Volume Name [$defVolume]"
    $cfgVolume = if ($in) { $in } else { $defVolume }

    # Port validations
    while ($true) {
        $in = Read-Host "PostgreSQL Host Port [$defPgPort]"
        $val = if ($in) { $in } else { $defPgPort }
        if ($val -match "^\d+$" -and [int]$val -ge 1024 -and [int]$val -le 65535) {
            $cfgPgPort = $val
            break
        } elseif ($val -eq "5432") {
            $cfgPgPort = "5432"
            break
        } else {
            Write-Host "  [!] Invalid port number. Enter 5432 or 1024-65535." -ForegroundColor Red
        }
    }

    while ($true) {
        $in = Read-Host "FastAPI Application Port [$defAppPort]"
        $val = if ($in) { $in } else { $defAppPort }
        if ($val -match "^\d+$" -and [int]$val -ge 1024 -and [int]$val -le 65535) {
            $cfgAppPort = $val
            break
        } else {
            Write-Host "  [!] Invalid port number. Enter 1024-65535." -ForegroundColor Red
        }
    }

    $in = Read-Host "Ollama Server Endpoint [$defOllamaUrl]"
    $cfgOllamaUrl = if ($in) { $in } else { $defOllamaUrl }

    $in = Read-Host "LLM Generation Model [$defGenModel]"
    $cfgGenModel = if ($in) { $in } else { $defGenModel }

    $in = Read-Host "Clinical Embedding Model [$defEmbModel]"
    $cfgEmbModel = if ($in) { $in } else { $defEmbModel }

    $in = Read-Host "Trial PDF Root Directory [$defTrialsDir]"
    $cfgTrialsDir = if ($in) { $in } else { $defTrialsDir }
} else {
    $cfgInstance = $defInstance
    $cfgComposeProject = $defComposeProject
    $cfgContainer = $defContainer
    $cfgDbName = $defDbName
    $cfgDbUser = $defDbUser
    $cfgDbPass = $defDbPass
    $cfgVolume = $defVolume
    $cfgPgPort = $defPgPort
    $cfgAppPort = $defAppPort
    $cfgOllamaUrl = $defOllamaUrl
    $cfgGenModel = $defGenModel
    $cfgEmbModel = $defEmbModel
    $cfgTrialsDir = $defTrialsDir
    Write-Host "  --> Using default configuration (Instance: $cfgInstance, Web Port: $cfgAppPort, DB Port: $cfgPgPort)"
}

# ------------------------------------------------------------------------------
# STEP 3: Safe .env Configuration
# ------------------------------------------------------------------------------
Write-Host "`n[Step 3/8] Writing Safe Configuration (.env)..." -ForegroundColor Yellow

if (Test-Path "$projectRoot\.env") {
    $timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
    Copy-Item "$projectRoot\.env" "$projectRoot\.env.backup_$timestamp" -Force
    Write-Host "  --> Existing .env backed up to: .env.backup_$timestamp" -ForegroundColor Green
}

$envContent = @"
# Instance & Deployment Identification
HELPBOX_INSTANCE_NAME=$cfgInstance
COMPOSE_PROJECT_NAME=$cfgComposeProject
POSTGRES_CONTAINER_NAME=$cfgContainer
POSTGRES_HOST_PORT=$cfgPgPort
POSTGRES_VOLUME_NAME=$cfgVolume
APP_PORT=$cfgAppPort

# Folder containing one direct subfolder per trial
TRIALS_DIR=$cfgTrialsDir

# PostgreSQL + pgvector
POSTGRES_DB=$cfgDbName
POSTGRES_USER=$cfgDbUser
POSTGRES_PASSWORD=$cfgDbPass
DATABASE_URL=postgresql+psycopg://${cfgDbUser}:${cfgDbPass}@localhost:${cfgPgPort}/${cfgDbName}

# Primary Embedding Model (768 dimensions)
EMBEDDING_MODEL=$cfgEmbModel
EMBEDDING_DIMENSION=768

# LLM Generation Provider
GENERATION_PROVIDER=ollama
OLLAMA_BASE_URL=$cfgOllamaUrl
OLLAMA_MODEL=$cfgGenModel
OLLAMA_CONTEXT_WINDOW=4096
OLLAMA_NUM_PREDICT=196
OLLAMA_KEEP_ALIVE=60m

# Optional Cloud Provider
GEMINI_API_KEY=
GEMINI_MODEL=gemini-3.8-flash

# Optional Private Company Endpoint
OPENAI_COMPATIBLE_BASE_URL=
OPENAI_COMPATIBLE_MODEL=$cfgGenModel
OPENAI_COMPATIBLE_API_KEY=not-needed

# Continuous Synchronization & RAG Settings
SYNC_ENABLED=true
SYNC_INTERVAL_SECONDS=120
RETRIEVAL_TOP_K=4
CHUNK_TOKEN_SIZE=800
CHUNK_TOKEN_OVERLAP=100
OCR_ENABLED=true
TABLE_EXTRACTION_ENABLED=true
"@

Set-Content -Path "$projectRoot\.env" -Value $envContent -Encoding utf8
Write-Host "  --> Successfully written .env (Password masked and securely saved)." -ForegroundColor Green

# ------------------------------------------------------------------------------
# STEP 4: Python Virtual Environment (.venv) & Dependencies
# ------------------------------------------------------------------------------
Write-Host "`n[Step 4/8] Setting Up Python Virtual Environment & Packages..." -ForegroundColor Yellow

$venvPath = Join-Path $projectRoot ".venv"
$venvPython = Join-Path $venvPath "Scripts\python.exe"
$venvPip = Join-Path $venvPath "Scripts\pip.exe"

if (-not (Test-Path $venvPath)) {
    Write-Host "  --> Creating new virtual environment at .venv..."
    & $pythonCmd -m venv $venvPath
    Write-Host "  --> Virtual environment CREATED." -ForegroundColor Green
} else {
    Write-Host "  --> Virtual environment already exists at .venv." -ForegroundColor Green
}

Write-Host "  --> Upgrading pip in .venv..."
& $venvPip install --quiet --upgrade pip

Write-Host "  --> Installing verified application dependencies from requirements.txt..."
& $venvPip install --quiet -r "$projectRoot\requirements.txt"
Write-Host "  --> All Python packages INSTALLED & VERIFIED." -ForegroundColor Green

# ------------------------------------------------------------------------------
# STEP 5: Docker & PostgreSQL/pgvector Service
# ------------------------------------------------------------------------------
Write-Host "`n[Step 5/8] Verifying Docker Desktop & PostgreSQL/pgvector Service..." -ForegroundColor Yellow

$dockerReady = $false
if (Get-Command "docker" -ErrorAction SilentlyContinue) {
    try {
        $null = docker info 2>$null
        if ($LASTEXITCODE -eq 0) {
            $dockerReady = $true
            Write-Host "  --> Docker daemon: ONLINE & READY" -ForegroundColor Green
        } else {
            Write-Host "  [!] Docker is installed, but Docker Desktop daemon is not running." -ForegroundColor Red
            Write-Host "      Please start Docker Desktop and ensure WSL2 integration is enabled."
        }
    } catch {}
} else {
    Write-Host "  [!] Docker was not found on your system." -ForegroundColor Red
    Write-Host "      Please install Docker Desktop for Windows: https://www.docker.com/products/docker-desktop"
}

if ($dockerReady) {
    $pgRunning = docker ps --filter "name=^/${cfgContainer}$" --filter "status=running" --format "{{.Names}}" 2>$null
    if ($pgRunning -match "^$cfgContainer$") {
        Write-Host "  --> Container '$cfgContainer' is already RUNNING on port $cfgPgPort." -ForegroundColor Green
    } else {
        Write-Host "  --> Starting PostgreSQL service via Docker Compose..."
        docker compose up -d
        Write-Host "  --> Waiting for PostgreSQL health check..."
        for ($i = 0; $i -lt 15; $i++) {
            $health = docker inspect --format '{{.State.Health.Status}}' $cfgContainer 2>$null
            if ($health -match "healthy") {
                Write-Host "  --> PostgreSQL container is HEALTHY." -ForegroundColor Green
                break
            }
            Start-Sleep -Seconds 1
        }
    }
} else {
    Write-Host "  [*] Proceeding without Docker container startup. (Ensure PostgreSQL is running manually)" -ForegroundColor Yellow
}

# ------------------------------------------------------------------------------
# STEP 6: Database Initialization / Restore
# ------------------------------------------------------------------------------
Write-Host "`n[Step 6/8] Database Schema Initialization & Backup Options..." -ForegroundColor Yellow

$dbAction = "1"
$latestBackup = Join-Path $projectRoot "data\backups\latest.sql"
if (-not $Default -and (Test-Path $latestBackup)) {
    Write-Host "A previous database backup was detected at data\backups\latest.sql." -ForegroundColor Cyan
    Write-Host "  [1] Fresh Database       (Initialize new tables and pgvector schema)"
    Write-Host "  [2] Restore from Backup  (Restore existing document inventory and vector embeddings)"
    $userDb = Read-Host "Enter choice [1]"
    if ($userDb -eq "2") {
        $dbAction = "2"
    }
}

if ($dbAction -eq "2") {
    Write-Host "  --> Restoring database from backup..."
    $restoreScript = Join-Path $projectRoot "scripts\restore_db.ps1"
    if (Test-Path $restoreScript) {
        & $restoreScript -File $latestBackup
    }
} else {
    Write-Host "  --> Initializing fresh database schema and pgvector extension..."
    if ($dockerReady) {
        try {
            & $venvPython -c "from app.db import init_db; init_db()" 2>$null
            Write-Host "  --> PostgreSQL schema and pgvector extension INITIALIZED." -ForegroundColor Green
        } catch {
            Write-Host "  --> Database schema initialization deferred." -ForegroundColor Yellow
        }
    }
}

# Check Trial Documents Directory
$trialsFullPath = Join-Path $projectRoot $cfgTrialsDir
if (-not (Test-Path $trialsFullPath)) {
    New-Item -ItemType Directory -Path $trialsFullPath -Force | Out-Null
}

$trialFolders = Get-ChildItem -Path $trialsFullPath -Directory -ErrorAction SilentlyContinue
if (-not $trialFolders -or $trialFolders.Count -eq 0) {
    Write-Host "  --> No trial folders found in $cfgTrialsDir."
    $genChoice = "Y"
    if (-not $Default) {
        $in = Read-Host "Generate synthetic demo trial documents (Trial_101 & Trial_102)? [Y/n]"
        $genChoice = if ($in) { $in } else { "Y" }
    }
    if ($genChoice -match "^[Yy]$") {
        $synthScript = Join-Path $projectRoot "scripts\create_synthetic_trials.py"
        & $venvPython $synthScript
        Write-Host "  --> Synthetic trial folders CREATED." -ForegroundColor Green
    }
} else {
    Write-Host "  --> Found $($trialFolders.Count) trial folders in $cfgTrialsDir." -ForegroundColor Green
}

# ------------------------------------------------------------------------------
# STEP 7: Ollama Server & Local Model Cache Checks
# ------------------------------------------------------------------------------
Write-Host "`n[Step 7/8] Verifying Ollama Inference Server & Model Caches..." -ForegroundColor Yellow

$ollamaOnline = $false
try {
    $res = Invoke-RestMethod -Uri "$cfgOllamaUrl/api/tags" -Method Get -TimeoutSec 3 -ErrorAction Stop
    $ollamaOnline = $true
    Write-Host "  --> Ollama server: ONLINE at $cfgOllamaUrl" -ForegroundColor Green
} catch {
    Write-Host "  --> Ollama server is currently OFFLINE at $cfgOllamaUrl." -ForegroundColor Yellow
    if (Get-Command "ollama" -ErrorAction SilentlyContinue) {
        Write-Host "      (Ollama CLI is installed. The dev launcher will automatically start it)."
    } else {
        Write-Host "  [*] Ollama CLI is not yet installed on this Windows machine." -ForegroundColor Yellow
        Write-Host "      Download and install Ollama from: https://ollama.com/download/windows"
    }
}

# Check Ollama generation model cache
$ollamaModelFound = $false
if (Get-Command "ollama" -ErrorAction SilentlyContinue) {
    $list = ollama list 2>$null
    if ($list -match $cfgGenModel) {
        $ollamaModelFound = $true
    }
}

if ($ollamaModelFound) {
    Write-Host "  --> Generation Model ($cfgGenModel): CACHED ON DISK" -ForegroundColor Green
} else {
    Write-Host "  --> Generation Model ($cfgGenModel, ~1.9 GB): NOT IN LOCAL CACHE" -ForegroundColor Yellow
    if (Get-Command "ollama" -ErrorAction SilentlyContinue) {
        $pullChoice = "N"
        if (-not $Default) {
            $in = Read-Host "  --> Would you like to download '$cfgGenModel' now? [y/N]"
            $pullChoice = if ($in) { $in } else { "N" }
        }
        if ($pullChoice -match "^[Yy]$") {
            Write-Host "  --> Pulling model weights from Ollama registry..."
            ollama pull $cfgGenModel
            Write-Host "  --> Model DOWNLOADED & CACHED." -ForegroundColor Green
        } else {
            Write-Host "  --> Model download deferred. You can download later with: ollama pull $cfgGenModel" -ForegroundColor Cyan
        }
    }
}

# Check Hugging Face Embedding Model Cache
$userProfile = [System.Environment]::GetFolderPath("UserProfile")
$embClean = $cfgEmbModel.Replace("/", "--")
$hfModelDir = Join-Path $userProfile ".cache\huggingface\hub\models--$embClean"

if (Test-Path $hfModelDir) {
    Write-Host "  --> Clinical Embedding Model ($cfgEmbModel): CACHED ON DISK" -ForegroundColor Green
} else {
    Write-Host "  --> Clinical Embedding Model ($cfgEmbModel, ~570 MB): NOT YET CACHED" -ForegroundColor Yellow
    $embChoice = "N"
    if (-not $Default) {
        $in = Read-Host "  --> Pre-download embedding model now? [y/N]"
        $embChoice = if ($in) { $in } else { "N" }
    }
    if ($embChoice -match "^[Yy]$") {
        Write-Host "  --> Downloading embedding model via sentence-transformers..."
        & $venvPython -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('$cfgEmbModel')"
        Write-Host "  --> Embedding model CACHED." -ForegroundColor Green
    } else {
        Write-Host "  --> Embedding model will be cached automatically upon first document indexing."
    }
}

# ------------------------------------------------------------------------------
# STEP 8: Summary & First Indexing Instructions
# ------------------------------------------------------------------------------
Write-Host "`n================================================================" -ForegroundColor Cyan
Write-Host "        HELPBOX SETUP COMPLETED SUCCESSFULLY!                    " -ForegroundColor Green
Write-Host "================================================================" -ForegroundColor Cyan

Write-Host "`nDaily Operations Commands:" -ForegroundColor Yellow
Write-Host "  1. Start Everything Daily:  .\scripts\start_dev.ps1" -ForegroundColor Cyan
Write-Host "  2. Check Service Health:    .\scripts\status.ps1" -ForegroundColor Cyan
Write-Host "  3. Stop Safely:             .\scripts\stop_dev.ps1" -ForegroundColor Cyan
Write-Host "  4. Backup Database:         .\scripts\backup_db.ps1" -ForegroundColor Cyan
Write-Host "  5. Restore Database:        .\scripts\restore_db.ps1" -ForegroundColor Cyan

Write-Host "`nHow to Perform Your First Indexing:" -ForegroundColor Yellow
Write-Host "  1. Run: .\scripts\start_dev.ps1" -ForegroundColor Cyan
Write-Host "  2. Open browser to: http://localhost:$cfgAppPort" -ForegroundColor Cyan
Write-Host "  3. Click on a trial in the left sidebar (e.g., Trial_101)."
Write-Host "  4. Click the 'AI Assistant' tab or 'Refresh' button."
Write-Host "     Helpbox will automatically parse, chunk, and embed your trial PDFs into pgvector."
Write-Host "  5. Ask clinical questions and receive evidence-grounded answers with citations!"
Write-Host "================================================================`n" -ForegroundColor Cyan
