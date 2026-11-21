# ESG Integrity Intelligence - one-time Windows setup and launcher
# Usage (PowerShell): paste this one line into PowerShell, inside your project folder:
#   irm https://raw.githubusercontent.com/iggysaint/ai-corporate-greenwashing-detector/claude/cool-babbage-cf6d8z/scripts/setup-windows.ps1 | iex
# or, from a local copy:
#   powershell -ExecutionPolicy Bypass -File .\setup-windows.ps1
# Installs Git / Python / Node.js with winget if missing, gets the latest code,
# installs backend + frontend dependencies, and starts both servers in new windows.

$ErrorActionPreference = "Stop"
$RepoUrl = "https://github.com/iggysaint/ai-corporate-greenwashing-detector.git"

function Step($msg) { Write-Host "`n==> $msg" -ForegroundColor Cyan }
function Have($cmd) { [bool](Get-Command $cmd -ErrorAction SilentlyContinue) }
function Refresh-Path {
    $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
                [Environment]::GetEnvironmentVariable("Path", "User")
}
function Ensure-Tool($cmd, $wingetId, $name) {
    if (Have $cmd) { Write-Host "$name found."; return }
    if (-not (Have "winget")) { throw "$name is missing and winget is unavailable. Install $name manually, then re-run." }
    Step "Installing $name"
    winget install --id $wingetId -e --accept-source-agreements --accept-package-agreements
    Refresh-Path
    if (-not (Have $cmd)) { throw "$name installed but not on PATH yet. Close PowerShell, open a new one, and re-run this script." }
}

# 1. Prerequisites
Step "Checking prerequisites"
Ensure-Tool "git" "Git.Git" "Git"
Ensure-Tool "node" "OpenJS.NodeJS.LTS" "Node.js"
if (-not (Have "python")) { Ensure-Tool "python" "Python.Python.3.12" "Python" }
$nodeMajor = [int]((node -v).TrimStart("v").Split(".")[0])
if ($nodeMajor -lt 20) { throw "Node.js 20.9+ required (found $(node -v)). Run: winget upgrade OpenJS.NodeJS.LTS" }

# 2. Code
Step "Getting the latest code"
if (Test-Path ".\app\main.py") {
    $root = (Get-Location).Path
} elseif (Test-Path ".\ai-corporate-greenwashing-detector\app\main.py") {
    $root = (Resolve-Path ".\ai-corporate-greenwashing-detector").Path
} else {
    git clone $RepoUrl
    $root = (Resolve-Path ".\ai-corporate-greenwashing-detector").Path
}
Set-Location $root
$dirty = git status --porcelain
if ($dirty) {
    Write-Host "Local uncommitted changes found - skipping 'git pull' so nothing is overwritten." -ForegroundColor Yellow
} else {
    git checkout master
    git pull origin master
}
if (-not (Test-Path ".\frontend\package.json")) { throw "frontend/ not found - make sure you are on the latest master." }

# 3. Backend
Step "Setting up the backend (Python virtual environment)"
if (-not (Test-Path ".\.venv")) { python -m venv .venv }
& .\.venv\Scripts\python.exe -m pip install --upgrade pip
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt
if (-not (Test-Path ".\.env")) { Copy-Item .env.example .env; Write-Host "Created .env from .env.example" }

# 4. Frontend
Step "Setting up the frontend (npm install)"
Push-Location .\frontend
npm install
if (-not (Test-Path ".\.env.local")) { Copy-Item .env.example .env.local; Write-Host "Created frontend\.env.local" }
Pop-Location

# 5. Launch
Step "Starting backend (port 8000) and frontend (port 3000) in new windows"
Start-Process powershell -ArgumentList "-NoExit", "-Command",
    "Set-Location '$root'; .\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000"
Start-Process powershell -ArgumentList "-NoExit", "-Command",
    "Set-Location '$root\frontend'; npm run dev"

Start-Sleep -Seconds 12
Start-Process "http://localhost:3000"
Write-Host "`nDone. App: http://localhost:3000   API: http://127.0.0.1:8000/docs" -ForegroundColor Green
Write-Host "Next time, just re-run this script (it skips what is already installed)."
