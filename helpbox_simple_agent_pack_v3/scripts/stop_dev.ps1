# ==============================================================================
# Helpbox — Safe Development Services Shutdown (Windows PowerShell)
# ==============================================================================

param(
    [switch]$All
)

$ErrorActionPreference = "Continue"

Write-Host "================================================================" -ForegroundColor Cyan
Write-Host "          HELPBOX — SAFE DEVELOPMENT SERVICES SHUTDOWN           " -ForegroundColor Cyan
Write-Host "================================================================" -ForegroundColor Cyan

# 1. Stop FastAPI / Uvicorn processes
Write-Host "`n[1/3] Stopping FastAPI Uvicorn backend..." -ForegroundColor Yellow
$uvicornProcs = Get-Process -Name "python" -ErrorAction SilentlyContinue | Where-Object {
    $_.CommandLine -match "uvicorn" -or $_.Path -match "\.venv\\Scripts\\python\.exe"
}
if ($uvicornProcs) {
    foreach ($p in $uvicornProcs) {
        Write-Host "  --> Stopping Uvicorn process (PID: $($p.Id))..."
        Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue
    }
}
Write-Host "  --> FastAPI backend STOPPED." -ForegroundColor Green

# 2. Stop Ollama if requested
if ($All) {
    Write-Host "`n[2/3] Stopping Ollama server (-All switch passed)..." -ForegroundColor Yellow
    Get-Process -Name "ollama" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
    Write-Host "  --> Ollama server STOPPED." -ForegroundColor Green
} else {
    Write-Host "`n[2/3] Checking Ollama server..." -ForegroundColor Yellow
    Write-Host "  --> Keeping Ollama server online for fast local inference."
    Write-Host "      (Pass '-All' if you wish to shut down Ollama as well)."
}

# 3. PostgreSQL Docker container status
Write-Host "`n[3/3] Checking PostgreSQL container..." -ForegroundColor Yellow
Write-Host "  --> Preserving PostgreSQL Docker container and persistent data volume."
Write-Host "      (To stop container without deleting data: 'docker compose stop')."

Write-Host "`n================================================================" -ForegroundColor Cyan
Write-Host "  Application stopped cleanly. Persistent data preserved." -ForegroundColor Green
Write-Host "  Status Script: .\scripts\status.ps1"
Write-Host "  Start Script:  .\scripts\start_dev.ps1"
Write-Host "================================================================" -ForegroundColor Cyan
