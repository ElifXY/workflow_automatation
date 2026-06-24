# Vollständige Prüfung: statisch immer; mit Docker falls verfügbar
$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)
Write-Host "=== Statische Prüfungen (full_stack_check.py) ===" -ForegroundColor Cyan
python scripts/full_stack_check.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$docker = Get-Command docker -ErrorAction SilentlyContinue
if (-not $docker) {
    Write-Host "`nDocker nicht gefunden — Container-Tests übersprungen." -ForegroundColor Yellow
    Write-Host "Installiere Docker Desktop oder führe in GitHub Actions: Docker stack verify Workflow aus." -ForegroundColor Yellow
    exit 0
}

Write-Host "`n=== Docker Stack (optional) ===" -ForegroundColor Cyan
python scripts/full_stack_check.py --docker
exit $LASTEXITCODE
