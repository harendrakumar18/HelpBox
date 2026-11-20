# ==============================================================================
# Helpbox — Database Backup Script (Windows PowerShell)
# ==============================================================================

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

if (-not (Test-Path $backupDir)) {
    New-Item -ItemType Directory -Path $backupDir -Force | Out-Null
}

$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$backupFile = Join-Path $backupDir "helpbox_backup_${timestamp}.sql"
$latestFile = Join-Path $backupDir "latest.sql"

Write-Host "[*] Creating database backup from container '$containerName' to $backupFile..." -ForegroundColor Cyan
docker exec $containerName pg_dump -U $pgUser -d $pgDb > $backupFile

if (Test-Path $backupFile) {
    Copy-Item -Path $backupFile -Destination $latestFile -Force
    $size = [math]::Round((Get-Item $backupFile).Length / 1KB, 1)
    Write-Host "[+] Backup complete: $backupFile (${size} KB)" -ForegroundColor Green
    Write-Host "[+] Updated latest: $latestFile" -ForegroundColor Green
} else {
    Write-Host "[-] Backup failed: file not created." -ForegroundColor Red
}
