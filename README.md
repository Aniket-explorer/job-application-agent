# AI Job Application Agent

[![CI](https://github.com/Aniket-explorer/job-application-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/Aniket-explorer/job-application-agent/actions/workflows/ci.yml)

A personal, local-first assistant that discovers jobs, scores them against your verified profile, prepares applications with your **original resume**, and tracks replies and follow-ups. It runs on your own laptop with Docker Desktop.

**Status:** Phase 1 is complete. Phase 2 milestone 1 adds a disabled-by-default Greenhouse job-list connector. Milestone 2 scores stored jobs against a local profile. Milestone 3 adds `POST /api/v1/sources/career_page/sync`. Milestone 4 adds a confirmed Sync jobs button on the Connectors page. The connector stays off unless you enable it, and the hourly scheduler does not call it. Applications are dry-run only. See [PHASE_2_PLAN.md](PHASE_2_PLAN.md).

## Safety

- **Dry-run is the default.** Nothing is submitted and no email is sent. Live submission stays off until a channel is implemented, tested, and explicitly enabled.
- LinkedIn, Naukri, Wellfound, and Gmail stay unconfigured. The career-page connector can read the public Greenhouse job list only after you set `ENABLE_CAREER_PAGE_CONNECTOR` and `GREENHOUSE_BOARDS` in `.env`, and only when you call `POST /api/v1/sources/career_page/sync`. The hourly scheduler does not call it. No connector submits applications.
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

- Windows 10/11 with [Docker Desktop](https://www.docker.com/products/docker-desktop/) (WSL 2 backend, Linux containers). MongoDB and Redis stay on the Compose network and are not published on the host, so a local MongoDB install does not collide with them.
- Git, Node.js 20.15+ (22 recommended), Python 3.12 (`winget install Python.Python.3.12`)
- Optional: `winget install Gitleaks.Gitleaks` and `pip install pre-commit` for local secret scanning

## Quick start (PowerShell)

```powershell
Copy-Item .env.example .env      # then replace dummy-* values locally if needed
docker compose up --build
```

- Dashboard: http://localhost:5173 or http://127.0.0.1:5173
- API docs: http://localhost:8000/docs
- Health: http://localhost:8000/health

## Profile and original resume

Scoring reads two gitignored files. It does not create a sample profile, and it does not modify the resume.

1. Create `storage/profile.json` at the repository root. Put only facts you can confirm: `skills` (`name`, optional `years`), `preferred_roles`, `work_experience` (`title`, `start`, `end`, optional `domain`), `projects`, `preferred_locations`, `work_arrangement_preferences`, `excluded_arrangements`, and `resume_filename`. Leave out anything you have not confirmed. `name`, `email`, and `phone` are ignored and are not returned by the API.
2. Put the original resume in `storage/resumes/`. `resume_filename` is that file's name only, for example `resume.pdf`. PDF, `.txt`, and `.md` can be read. PDF text is extracted in memory with `pypdf`; the file is not rewritten.
3. Docker Compose mounts `storage/` read-only at `/storage` and sets `PROFILE_PATH=/storage/profile.json` and `RESUME_STORAGE_PATH=/storage/resumes`. You do not need to change those two values for Compose. A process you start yourself from `backend/` should keep the `../storage/...` paths in `.env`.

`GET /api/v1/profile/status` reports a missing or unreadable profile or resume. Until the profile file exists, jobs are not given assumed skills.

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
| Backend integration | `backend/tests/integration` | MongoDB. Uses database `job_agent_integration_test` only. Redis on localhost; if none is running, the suite starts a temporary container bound to `127.0.0.1` and removes it afterward. The Compose Redis service stays unpublished. |
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

## Current API

Versioned routes live under `/api/v1`. The original `/api/*` routes still work and use the same database records. Details are in [docs/API_SPEC.md](docs/API_SPEC.md).

```powershell
# Readiness (MongoDB and Redis)
Invoke-RestMethod http://localhost:8000/api/v1/ready

# Import a test job
Invoke-RestMethod -Method Post -Uri http://localhost:8000/api/v1/jobs/import -ContentType 'application/json' -Body '{"source":"manual","source_job_id":"demo-1","company":"Example Co","title":"Backend Engineer","location":"Bengaluru","description":"Python FastAPI REST API MongoDB backend role","canonical_url":"https://example.com/jobs/demo-1"}'

# List jobs
Invoke-RestMethod http://localhost:8000/api/v1/jobs

# Prepare a dry-run application (replace the ID). This does not submit anything.
Invoke-RestMethod -Method Post -Uri http://localhost:8000/api/v1/jobs/REPLACE_WITH_JOB_ID/prepare-application -ContentType 'application/json' -Body '{}'
```

Saved settings are in MongoDB (`automation_settings`). The API rejects `dry_run=false`.
