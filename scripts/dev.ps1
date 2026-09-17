$ErrorActionPreference = "Stop"
$rootPath = Split-Path -Parent $PSScriptRoot

Write-Host "Starting Net2Net development services..." -ForegroundColor Cyan

$api = Start-Process powershell -ArgumentList @(
    "-NoExit", "-Command",
    "Set-Location '$rootPath\apps\api'; if (-not (Test-Path .venv)) { python -m venv .venv }; .\.venv\Scripts\python -m pip install -e '.[dev]'; .\.venv\Scripts\python -m uvicorn app.main:app --reload --port 8000"
) -PassThru

$web = Start-Process powershell -ArgumentList @(
    "-NoExit", "-Command",
    "Set-Location '$rootPath\apps\web'; if (-not (Test-Path node_modules)) { npm install }; npm run dev"
) -PassThru

$radius = Start-Process powershell -ArgumentList @(
    "-NoExit", "-Command",
    "Set-Location '$rootPath\apps\api'; .\.venv\Scripts\python -m app.radius_server"
) -PassThru

Write-Host "API process: $($api.Id) | Web process: $($web.Id) | RADIUS process: $($radius.Id)" -ForegroundColor Green
Write-Host "Open http://localhost:5173"
