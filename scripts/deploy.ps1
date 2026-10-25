<#
.SYNOPSIS
  Deploys the latest published images (built by GitHub Actions CD) on this laptop and verifies the stack is healthy.
.EXAMPLE
  .\scripts\deploy.ps1                 # latest images
  .\scripts\deploy.ps1 -Tag sha-abc123 # a specific build
#>
param([string]$Tag = 'latest')

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw 'Docker Desktop is not installed or not on PATH.' }
if (-not (Test-Path .env)) { throw 'Missing .env. Run: Copy-Item .env.example .env, then set GHCR_OWNER and your real values.' }

$owner = (Select-String -Path .env -Pattern '^GHCR_OWNER=(.+)$').Matches.Groups[1].Value
if (-not $owner -or $owner -like 'dummy-*') { throw 'Set GHCR_OWNER in .env to your GitHub username (lowercase).' }
New-Item -ItemType Directory -Force storage, secrets | Out-Null

$env:GHCR_OWNER = $owner.ToLower()
$env:IMAGE_TAG = $Tag
$compose = @('compose', '-f', 'docker-compose.release.yml')

Write-Host "Pulling images ghcr.io/$($env:GHCR_OWNER)/job-application-agent-*:$Tag" -ForegroundColor Cyan
docker @compose pull
if ($LASTEXITCODE -ne 0) { throw 'docker compose pull failed' }
docker @compose up -d --remove-orphans
if ($LASTEXITCODE -ne 0) { throw 'docker compose up failed' }

Write-Host 'Waiting for API to become healthy...' -ForegroundColor Cyan
$deadline = (Get-Date).AddSeconds(120)
while ((Get-Date) -lt $deadline) {
    try {
        $health = Invoke-RestMethod -Uri http://localhost:8000/health -TimeoutSec 5
        if ($health.mongodb -eq 'ok') {
            Write-Host "Deployed. Dashboard: http://localhost:5173  API docs: http://localhost:8000/docs  dry_run=$($health.dry_run)" -ForegroundColor Green
            exit 0
        }
    } catch { Start-Sleep -Seconds 3; continue }
    Start-Sleep -Seconds 3
}
docker @compose logs --tail 100 api
throw 'API did not become healthy within 120 seconds.'
