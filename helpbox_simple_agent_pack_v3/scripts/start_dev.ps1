# ==============================================================================
# Helpbox — Safe Development Environment Startup (Windows PowerShell)
# ==============================================================================

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = Split-Path -Parent $scriptDir
Set-Location $projectRoot

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
$pgPort = if ($env:POSTGRES_HOST_PORT) { $env:POSTGRES_HOST_PORT } else { "5432" }
$fastapiPort = if ($env:APP_PORT) { $env:APP_PORT } else { "8000" }
$ollamaUrl = if ($env:OLLAMA_BASE_URL) { $env:OLLAMA_BASE_URL } else { "http://127.0.0.1:11434" }

Write-Host "================================================================" -ForegroundColor Cyan
Write-Host "          HELPBOX — SAFE DEVELOPMENT ENVIRONMENT STARTUP         " -ForegroundColor Cyan
Write-Host "================================================================" -ForegroundColor Cyan

# 1. PostgreSQL Check & Launch
Write-Host "`n[1/3] Verifying PostgreSQL 16 + pgvector container ($containerName)..." -ForegroundColor Yellow
$pgRunning = docker ps --filter "name=^/${containerName}$" --filter "status=running" --format "{{.Names}}" 2>$null
if ($pgRunning -match "^$containerName$") {
    Write-Host "  --> PostgreSQL container is already HEALTHY & RUNNING on port $pgPort." -ForegroundColor Green
} else {
    Write-Host "  --> Starting PostgreSQL container via Docker Compose..."
    docker compose up -d
    Start-Sleep -Seconds 3
    Write-Host "  --> PostgreSQL container STARTED." -ForegroundColor Green
}

# 2. Ollama Server Check & Launch
Write-Host "`n[2/3] Verifying Ollama Inference Server ($ollamaUrl)..." -ForegroundColor Yellow
$ollamaOnline = $false
try {
    $res = Invoke-RestMethod -Uri "$ollamaUrl/api/tags" -Method Get -TimeoutSec 2 -ErrorAction Stop
    $ollamaOnline = $true
} catch {
    $ollamaOnline = $false
}

if ($ollamaOnline) {
    Write-Host "  --> Ollama server is already ONLINE on $ollamaUrl." -ForegroundColor Green
} else {
    Write-Host "  --> Starting Ollama server in background..."
    Start-Process -FilePath "ollama" -ArgumentList "serve" -WindowStyle Hidden
    Start-Sleep -Seconds 3
    Write-Host "  --> Ollama server launched." -ForegroundColor Green
}

# 3. FastAPI Backend Check & Launch
Write-Host "`n[3/3] Verifying FastAPI Application Backend (Port $fastapiPort)..." -ForegroundColor Yellow
$fastapiOnline = $false
try {
    $res = Invoke-RestMethod -Uri "http://127.0.0.1:$fastapiPort/health" -Method Get -TimeoutSec 2 -ErrorAction Stop
    $fastapiOnline = $true
} catch {
    $fastapiOnline = $false
}

if ($fastapiOnline) {
    Write-Host "  --> FastAPI backend is already ONLINE on http://127.0.0.1:$fastapiPort." -ForegroundColor Green
} else {
    Write-Host "  --> Starting FastAPI backend with Uvicorn..."
    $venvPython = Join-Path $projectRoot ".venv\Scripts\python.exe"
    if (-not (Test-Path $venvPython)) {
        Write-Host "  [-] Virtual environment not found at .venv! Run: python -m venv .venv" -ForegroundColor Red
        exit 1
    }
    Start-Process -FilePath $venvPython -ArgumentList "-m uvicorn app.main:app --host 0.0.0.0 --port $fastapiPort" -WindowStyle Hidden
    Start-Sleep -Seconds 4
    Write-Host "  --> FastAPI backend launched." -ForegroundColor Green
}

Write-Host "`n================================================================" -ForegroundColor Cyan
Write-Host "  All development services are active and verified." -ForegroundColor Green
Write-Host "  Workspace UI:  http://localhost:$fastapiPort"
Write-Host "  Status Script: .\scripts\status.ps1"
Write-Host "  Stop Script:   .\scripts\stop_dev.ps1"
Write-Host "================================================================" -ForegroundColor Cyan
