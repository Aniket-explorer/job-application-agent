# AI Job Application Agent

[![CI](https://github.com/Aniket-explorer/job-application-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/Aniket-explorer/job-application-agent/actions/workflows/ci.yml)

A personal, local-first assistant that discovers jobs, scores them against your verified profile, prepares applications with your **original resume**, and tracks replies and follow-ups. It runs on your own laptop with Docker Desktop.

**Status:** Phase 0 complete (design, repository, CI/CD). The running app is still the starter scaffold: manual job import, baseline scoring, and dry-run application records. See [docs/IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md) for what comes next.

## Safety

- **Dry-run is the default.** Nothing is submitted and no email is sent. Live submission stays off until a channel is implemented, tested, and explicitly enabled.
- LinkedIn, Naukri, Wellfound, company career pages, and Gmail are connectors that report `not_configured` until their access is verified. They do not scrape, log in, bypass CAPTCHAs, or submit forms.
- This is a **public** repository. Only dummy placeholder credentials are committed. Your real keys go in `.env` / `secrets/`, your resume and profile in `storage/`; all are gitignored.

## Design docs

| Doc | Contents |
|---|---|
| [PRD](docs/PRD.md) | Goals, scope, requirements |
| [HLD](docs/HLD.md) | Architecture, runtime topology, key decisions, delivery pipeline |
| [LLD](docs/LLD.md) | Package layout, connector interfaces, services, state machines, tasks |
| [API spec](docs/API_SPEC.md) | `/api/v1` contracts, errors, pagination |
| [Data model](docs/DATA_MODEL.md) | MongoDB collections and indexes |
| [Security](docs/SECURITY.md) | Threats, OAuth scopes, secret handling |
| [Implementation plan](docs/IMPLEMENTATION_PLAN.md) | Phase checklist, integrations to verify |

`CURSOR.md` is the short project memory used by the Cursor agent (current phase, feature inventory, change log).

## Requirements (Windows)

- Windows 10/11 with [Docker Desktop](https://www.docker.com/products/docker-desktop/) (WSL 2 backend, Linux containers)
- Git, Node.js 20.15+ (22 recommended), Python 3.12 (`winget install Python.Python.3.12`)
- Optional: `winget install Gitleaks.Gitleaks` and `pip install pre-commit` for local secret scanning

## Quick start (PowerShell)

```powershell
Copy-Item .env.example .env      # then replace dummy-* values locally if needed
docker compose up --build
```

- Dashboard: http://localhost:5173
- API docs: http://localhost:8000/docs
- Health: http://localhost:8000/health

Stop with `Ctrl+C` or `docker compose down` (add `-v` only to delete local data).

## Testing (fully automated)

Run every CI stage locally:

```powershell
.\scripts\ci.ps1              # secrets scan, backend lint + tests, frontend checks, docker smoke test
.\scripts\ci.ps1 -SkipDocker  # without Docker
```

| Suite | Location | Needs |
|---|---|---|
| Backend unit | `backend/tests/unit` | nothing |
| Backend integration | `backend/tests/integration` | MongoDB (skipped locally if absent, required in CI) |
| Stack smoke | `backend/tests/smoke` | running compose stack, `SMOKE_BASE_URL` |
| Frontend | `frontend/src/**/*.test.ts(x)` | nothing |
| End-to-end UI | `e2e/` | added in Phase 6 |

## CI/CD

```
PR -> secrets scan -> unit + lint -> frontend -> integration (+coverage gate) -> docker build -> compose smoke -> e2e -> merge
main -> publish images to ghcr.io -> .\scripts\deploy.ps1 on your laptop
```

- [`ci.yml`](.github/workflows/ci.yml) runs on every pull request and push to `main`. A failed stage blocks merging.
- [`cd.yml`](.github/workflows/cd.yml) publishes `job-application-agent-api` and `job-application-agent-frontend` images to GitHub Container Registry after CI passes on `main`.

### Deploy the latest build locally

```powershell
# one-time: set GHCR_OWNER=<your-github-username> in .env
.\scripts\deploy.ps1            # pulls latest images, starts the stack, waits for health
.\scripts\deploy.ps1 -Tag sha-<commit>
```

## How we work

1. Create a branch `phase-N-<name>`.
2. Implement with tests; update `CURSOR.md` and this README.
3. Run `.\scripts\ci.ps1`, push, open a PR.
4. CI must be green, then merge. CD publishes the images.

## Secrets rules

- Never commit `.env`, OAuth client JSON, tokens, keys, or your resume.
- Committed config values must start with `dummy-`.
- gitleaks runs in a pre-commit hook (`pre-commit install`), in CI on every PR, and GitHub push protection is enabled.
- If a secret ever leaks: rotate it at the provider first, then clean history. See [docs/SECURITY.md](docs/SECURITY.md).

## Current API (starter, legacy routes)

These move to `/api/v1` in Phases 1-6 (mapping in [docs/API_SPEC.md](docs/API_SPEC.md#10-legacy-starter-routes-deprecated)).

```powershell
# Import a test job
Invoke-RestMethod -Method Post -Uri http://localhost:8000/api/jobs/import -ContentType 'application/json' -Body '{"source":"manual","source_job_id":"demo-1","company":"Example Co","title":"Backend Engineer","location":"Bengaluru","description":"Python FastAPI REST API MongoDB backend role","canonical_url":"https://example.com/jobs/demo-1"}'

# List jobs
Invoke-RestMethod http://localhost:8000/api/jobs

# Create a dry-run application (replace the ID)
Invoke-RestMethod -Method Post -Uri http://localhost:8000/api/applications -ContentType 'application/json' -Body '{"job_id":"REPLACE_WITH_JOB_ID"}'
```
