# ==============================================================================
# Helpbox — Multi-Service Status & Diagnostic Verification (Windows PowerShell)
# ==============================================================================

$ErrorActionPreference = "Continue"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = Split-Path -Parent $scriptDir

# Load environment settings if .env exists
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

$containerName = if ($env:POSTGRES_CONTAINER_NAME) { $env:POSTGRES_CONTAINER_NAME } else { "helpbox-postgres" }
$pgUser = if ($env:POSTGRES_USER) { $env:POSTGRES_USER } else { "helpbox" }
$pgDb = if ($env:POSTGRES_DB) { $env:POSTGRES_DB } else { "helpbox" }
$pgPort = if ($env:POSTGRES_HOST_PORT) { $env:POSTGRES_HOST_PORT } else { "5432" }
$fastapiPort = if ($env:APP_PORT) { $env:APP_PORT } else { "8000" }
$ollamaUrl = if ($env:OLLAMA_BASE_URL) { $env:OLLAMA_BASE_URL } else { "http://127.0.0.1:11434" }
$modelName = if ($env:OLLAMA_MODEL) { $env:OLLAMA_MODEL } else { "qwen3.5:2b-q4_K_M" }

Write-Host "================================================================" -ForegroundColor Cyan
Write-Host "       HELPBOX CLINICAL RAG — SERVICE STATUS & HEALTH CHECK      " -ForegroundColor Cyan
Write-Host "================================================================" -ForegroundColor Cyan

# 1. System Resources
Write-Host "`n[1/5] Host System Resources (Windows PowerShell)" -ForegroundColor Yellow
try {
    $os = Get-CimInstance Win32_OperatingSystem
    $freeMemGB = [math]::Round($os.FreePhysicalMemory / 1MB, 2)
    $totalMemGB = [math]::Round($os.TotalVisibleMemorySize / 1MB, 2)
    $usedMemGB = [math]::Round($totalMemGB - $freeMemGB, 2)
    Write-Host "  Memory: Used: ${usedMemGB} GB / Total: ${totalMemGB} GB (Free: ${freeMemGB} GB)"
} catch {
    Write-Host "  Memory: Could not query memory statistics."
}

# 2. Terminal 1: PostgreSQL 16 + pgvector Service
Write-Host "`n[2/5] Terminal 1 Service — PostgreSQL 16 + pgvector (Container: $containerName)" -ForegroundColor Yellow
$pgRunning = docker ps --filter "name=^/${containerName}$" --filter "status=running" --format "{{.Names}}" 2>$null
if ($pgRunning -match "^$containerName$") {
    Write-Host "  Container State: RUNNING (healthy) on port $pgPort" -ForegroundColor Green
    $testSql = docker exec $containerName psql -U $pgUser -d $pgDb -c "SELECT 1;" 2>$null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  SQL Connectivity: OK (PostgreSQL 16 + pgvector)" -ForegroundColor Green
        $invCount = (docker exec $containerName psql -U $pgUser -d $pgDb -t -c "SELECT COUNT(*) FROM document_inventory;" 2>$null).Trim()
        $vecCount = (docker exec $containerName psql -U $pgUser -d $pgDb -t -c "SELECT COUNT(*) FROM langchain_pg_embedding;" 2>$null).Trim()
        $metricCount = (docker exec $containerName psql -U $pgUser -d $pgDb -t -c "SELECT COUNT(*) FROM performance_metrics;" 2>$null).Trim()
        Write-Host "  Document Inventory: $invCount records" -ForegroundColor Green
        Write-Host "  Clinical Vector Embeddings: $vecCount chunks" -ForegroundColor Green
        Write-Host "  Performance Metrics Logged: $metricCount stage durations" -ForegroundColor Green
    } else {
        Write-Host "  SQL Connectivity: FAILED (Database not accepting queries)" -ForegroundColor Red
    }
} else {
    Write-Host "  Container State: NOT RUNNING" -ForegroundColor Red
    Write-Host "  Action needed: Run 'docker compose up -d' in Terminal 1."
}

# 3. Terminal 2: Ollama Local Inference Server
Write-Host "`n[3/5] Terminal 2 Service — Ollama Server ($ollamaUrl)" -ForegroundColor Yellow
try {
    $ollamaResp = Invoke-RestMethod -Uri "$ollamaUrl/api/tags" -Method Get -TimeoutSec 3 -ErrorAction Stop
    Write-Host "  Server API: OK ($ollamaUrl)" -ForegroundColor Green
    $models = ($ollamaResp.models | ForEach-Object { $_.name }) -join ", "
    Write-Host "  Available Models: $models" -ForegroundColor Green
    if ($models -match "qwen3.5:2b") {
        Write-Host "  Model ($modelName): AVAILABLE & VERIFIED" -ForegroundColor Green
    } else {
        Write-Host "  Model ($modelName): NOT FOUND (Run 'ollama pull $modelName')" -ForegroundColor Red
    }
} catch {
    Write-Host "  Server API: NOT RUNNING on $ollamaUrl" -ForegroundColor Red
    Write-Host "  Action needed: Run 'ollama serve' in Terminal 2."
}

# 4. Terminal 3: FastAPI Backend & Continuous Sync
Write-Host "`n[4/5] Terminal 3 Service — FastAPI Application & Continuous Scanner (Port $fastapiPort)" -ForegroundColor Yellow
try {
    $healthResp = Invoke-RestMethod -Uri "http://127.0.0.1:$fastapiPort/health" -Method Get -TimeoutSec 3 -ErrorAction Stop
    Write-Host "  Backend API: ONLINE (http://127.0.0.1:$fastapiPort)" -ForegroundColor Green
    try {
        $syncResp = Invoke-RestMethod -Uri "http://127.0.0.1:$fastapiPort/api/sync/status" -Method Get -TimeoutSec 3 -ErrorAction Stop
        if ($syncResp.is_running -eq $true) {
            Write-Host "  Continuous Background Sync: ACTIVE (Interval: $($syncResp.interval_seconds)s, Scans: $($syncResp.scan_count))" -ForegroundColor Green
            Write-Host "  Last Completed Scan: $($syncResp.last_scan_time)" -ForegroundColor Green
        } else {
            Write-Host "  Continuous Background Sync: IDLE / DISABLED" -ForegroundColor Yellow
        }
    } catch {
        Write-Host "  Continuous Background Sync: Status check skipped."
    }
} catch {
    Write-Host "  Backend API: NOT RUNNING on 127.0.0.1:$fastapiPort" -ForegroundColor Red
    Write-Host "  Action needed: Run '.\scripts\start_dev.ps1'."
}

# 5. Local Model Caches on Disk
Write-Host "`n[5/5] Cached Model Footprint on Disk" -ForegroundColor Yellow
$userHome = [Environment]::GetFolderPath("UserProfile")
$hfPath = Join-Path $userHome ".cache\huggingface\hub"
$ollamaPath = Join-Path $userHome ".ollama\models"

if (Test-Path $hfPath) {
    $hfSizeMB = [math]::Round((Get-ChildItem -Path $hfPath -Recurse -File -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum).Sum / 1MB, 1)
    Write-Host "  Hugging Face Models (ModernBERT): ${hfSizeMB} MB ($hfPath)" -ForegroundColor Green
}
if (Test-Path $ollamaPath) {
    $ollamaSizeMB = [math]::Round((Get-ChildItem -Path $ollamaPath -Recurse -File -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum).Sum / 1MB, 1)
    Write-Host "  Ollama Models (Qwen 3.5 2B): ${ollamaSizeMB} MB ($ollamaPath)" -ForegroundColor Green
}

Write-Host "`n================================================================" -ForegroundColor Cyan
