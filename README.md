# AI Job Application Agent — Starter

A local-first, dry-run starter for a personal job application assistant. It provides FastAPI, MongoDB, Redis/Celery, a React + TypeScript + Vite dashboard, connector interfaces, and tests.

## Safety and integration status

- **Dry-run is the default.** The starter never submits an application or sends an email.
- LinkedIn, Naukri, Wellfound, company career sites, and Gmail are represented by connector adapters. They are **not assumed to have API access**. The default adapters report `not_configured` and do not scrape, log in, bypass CAPTCHAs, or submit forms.
- Enable a real connector only after verifying the provider's current terms, API availability, permissions/scopes, and the specific workflow. Gmail integration requires configuring a Google Cloud OAuth client and consent flow; no Gmail API calls are implemented in this starter.
- Never put credentials in source control. Use a local `.env` and revoke tokens if exposed.

## Requirements

- Windows 10/11 with Docker Desktop (Linux containers enabled)
- Git and a recent Node.js LTS if you want to run the frontend outside Docker
- Docker Compose v2

## Start on Windows (PowerShell)

```powershell
Copy-Item .env.example .env
# Edit .env if you want to change local ports or secrets.
docker compose up --build
```

Then open:
- API docs: http://localhost:8000/docs
- API health: http://localhost:8000/health
- React dashboard: http://localhost:5173

Stop services with `Ctrl+C`, or run `docker compose down`. Add `-v` only if you intend to delete local database/Redis data.

## Run backend tests

```powershell
docker compose run --rm api pytest -q
```

## Local development without Docker

Backend (Python 3.11+ recommended):

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:APP_ENV = "test"
pytest -q
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Frontend:

```powershell
cd frontend
npm install
npm run dev -- --host 0.0.0.0
```

For local frontend development, set `VITE_API_BASE_URL=http://localhost:8000` in `frontend/.env.local`.

## What's implemented

- Health endpoint and API route skeleton
- MongoDB document persistence for normalized jobs, match decisions, and applications
- Connector capability/status interface for LinkedIn, Naukri, Wellfound, company career pages, and Gmail
- Manual job import endpoint for testing the pipeline without source API access
- Deterministic match scoring and 50% threshold
- Dry-run application creation (records `dry_run`, does not submit)
- Celery task skeleton with idempotent intent and clear dry-run behavior
- React dashboard pages for overview, jobs, applications, and settings
- Unit tests for matching, connector defaults, and dry-run behavior

## Important implementation gaps (intentionally not faked)

1. OAuth authorization and Gmail API client for reading/sending mail.
2. Provider-approved APIs or permitted workflows for job discovery and submission.
3. Authentication for multi-user/public deployment. This starter is intended for local use only.
4. Resume upload/storage and original-resume checksum management.
5. Reply classification, follow-up scheduling, and real notification delivery.
6. Production observability, backups, rate-limit persistence, and deployment hardening.

## Suggested implementation order

1. Run the scaffold and tests; import a sample job manually.
2. Add profile management and secure resume storage/checksum.
3. Implement Gmail OAuth read-only ingestion for recruiter alerts; verify Google API scopes and policies first.
4. Add matching evaluation fixtures and dashboard explanations.
5. Add a source connector only after confirming permitted access and documenting rate limits.
6. Add email sending behind a feature flag and explicit dry-run/live mode guard.
7. Add one supported application workflow; require confirmation on ambiguous outcomes.
8. Implement follow-up reminders and inbound-reply matching.
9. Add auth, secrets management, audit retention, backups, and end-to-end tests before anything is exposed beyond localhost.

## API examples

Import a test job:

```powershell
Invoke-RestMethod -Method Post -Uri http://localhost:8000/api/jobs/import -ContentType 'application/json' -Body '{"source":"manual","source_job_id":"demo-1","company":"Example Co","title":"Backend Engineer","location":"Bengaluru","description":"Python FastAPI REST API MongoDB backend role","canonical_url":"https://example.com/jobs/demo-1"}'
```

List jobs:

```powershell
Invoke-RestMethod http://localhost:8000/api/jobs
```

Create a dry-run application for a job (replace the ID):

```powershell
Invoke-RestMethod -Method Post -Uri http://localhost:8000/api/applications -ContentType 'application/json' -Body '{"job_id":"REPLACE_WITH_JOB_ID"}'
```

The endpoint refuses to create a live application. Live mode is deliberately not implemented until a provider-specific connector and safety checks are added.
