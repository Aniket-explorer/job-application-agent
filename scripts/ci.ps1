<#
.SYNOPSIS
  Runs the same stages as GitHub Actions CI on this laptop.
.EXAMPLE
  .\scripts\ci.ps1              # secrets scan, backend lint + tests, frontend checks, docker smoke (if Docker is available)
  .\scripts\ci.ps1 -SkipDocker  # everything except the docker compose smoke stage
#>
param([switch]$SkipDocker)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

function Invoke-Stage([string]$Name, [scriptblock]$Body) {
    Write-Host "`n=== $Name ===" -ForegroundColor Cyan
    & $Body
    if ($LASTEXITCODE -ne 0) { throw "Stage failed: $Name (exit $LASTEXITCODE)" }
}

$hasDocker = [bool](Get-Command docker -ErrorAction SilentlyContinue)

Invoke-Stage 'Secrets scan (gitleaks)' {
    if (-not (Get-Command gitleaks -ErrorAction SilentlyContinue)) { throw 'gitleaks not installed: winget install Gitleaks.Gitleaks' }
    gitleaks git . --config .gitleaks.toml --redact --no-banner
    if ($LASTEXITCODE -eq 0) { gitleaks dir . --config .gitleaks.toml --redact --no-banner }
}

Invoke-Stage 'Backend lint + tests' {
    Push-Location backend
    try {
        if (-not (Test-Path .venv)) { py -3.12 -m venv .venv }
        .\.venv\Scripts\pip install -q -r requirements-dev.txt
        .\.venv\Scripts\ruff check .
        if ($LASTEXITCODE -eq 0) {
            $env:MONGODB_URL = 'mongodb://localhost:27017'
            .\.venv\Scripts\pytest tests/unit tests/integration -q --cov=app --cov-report=term
        }
    } finally { Pop-Location }
}

Invoke-Stage 'Frontend typecheck + tests + build' {
    Push-Location frontend
    try {
        npm ci --no-fund --no-audit
        if ($LASTEXITCODE -eq 0) { npm run typecheck }
        if ($LASTEXITCODE -eq 0) { npm test }
        if ($LASTEXITCODE -eq 0) { npm run build }
    } finally { Pop-Location }
}

if ($SkipDocker -or -not $hasDocker) {
    Write-Host "`nSkipping docker smoke stage (Docker not available or -SkipDocker)." -ForegroundColor Yellow
    exit 0
}

Invoke-Stage 'Stack smoke test (docker compose)' {
    if (-not (Test-Path .env)) { Copy-Item .env.example .env }
    docker compose up -d --build api worker mongo redis
    try {
        $env:SMOKE_BASE_URL = 'http://localhost:8000'
        Push-Location backend
        try { .\.venv\Scripts\pytest tests/smoke -q } finally { Pop-Location }
    } finally {
        $code = $LASTEXITCODE
        docker compose stop api worker | Out-Null
        $global:LASTEXITCODE = $code
    }
}

Write-Host "`nAll CI stages passed." -ForegroundColor Green
