# ==============================================================================
# Helpbox — Database Restore Script (Windows PowerShell)
# ==============================================================================

param(
    [string]$File = ""
)

$ErrorActionPreference = "Stop"

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

$backupDir = Join-Path $projectRoot "data\backups"
$restoreFile = if ($File) { $File } else { Join-Path $backupDir "latest.sql" }

if (-not (Test-Path $restoreFile)) {
    Write-Host "[-] Backup file not found: $restoreFile" -ForegroundColor Red
    exit 1
}

Write-Host "[*] Restoring database in container '$containerName' from $restoreFile..." -ForegroundColor Cyan
Get-Content -Path $restoreFile | docker exec -i $containerName psql -U $pgUser -d $pgDb

Write-Host "[+] Database restore complete." -ForegroundColor Green
