# CURSOR.md - Project Memory

Read this first. Keep it short. Details live in `docs/`; this file summarizes and links.

## Goal
Personal AI job application agent: discover jobs (LinkedIn, Naukri, Wellfound, career pages, Gmail), score them against a verified profile (threshold 50), prepare and later submit applications through permitted channels using the **original resume only**, and track replies and follow-ups. Dry-run by default. Telegram/WhatsApp are out of scope.

## Stack
Python 3.12, FastAPI, Pydantic v2, MongoDB (PyMongo async), Redis, Celery + Beat, React 19 + TypeScript + Vite 6, Vitest, Docker Compose on Windows. CI/CD on GitHub Actions; images on GHCR.

## Key decisions (see docs/HLD.md section 5)
- Modular monolith: api, worker, beat processes share Mongo and Redis.
- Mongo is the source of truth; Redis only for broker, locks, rate limits.
- `ApplicationOrchestrator` is the only code path to submission; it enforces pause, dry-run, threshold, exclusions, duplicates, capability, permissions, resume SHA-256, verified answers (docs/LLD.md section 6).
- Connectors declare capabilities; unverified or unconfigured means no calls, never fake success.
- Public repo: only `dummy-*` placeholders committed; real secrets in `.env`/`secrets/`, personal data in `storage/` (all gitignored).

## Docs map
`docs/PRD.md` requirements - `docs/HLD.md` architecture - `docs/LLD.md` interfaces, services, state machines, tasks - `docs/API_SPEC.md` `/api/v1` contracts - `docs/DATA_MODEL.md` collections and indexes - `docs/SECURITY.md` threats, OAuth scopes, secrets - `docs/IMPLEMENTATION_PLAN.md` phase checklist and integration verification table.

## Directory map (current)
```
backend/app/main.py            app factory, correlation id, error handlers, legacy /health
backend/app/core/              config, JSON logging, error envelope
backend/app/db/                PyMongo async client, indexes
backend/app/repositories/      jobs, applications, automation_settings, audit
backend/app/services/          jobs, applications, settings, sources
backend/app/api/v1/            versioned routes
backend/app/api/legacy.py      original /api/* routes, same services
backend/app/connectors/        base.py + stubs.py (all unconfigured)
backend/tests/unit|integration|smoke
frontend/src/                  App.tsx (4 pages), api.ts loadWorkspace()
```

## Current phase
**Phase 1 complete (versioned API, repositories, persisted settings).** Next: Phase 2 job domain (normalization, dedup signals, matching redesign). Wait for user confirmation.

## Functionality inventory
Update this table whenever a function, endpoint, task, connector, or page is added, changed, or removed.

| Feature | Entry point | Module | Tests | Status |
|---|---|---|---|---|
| Liveness | `GET /health`, `GET /api/v1/health` | app/main.py, api/v1/routes/health.py | integration, smoke | legacy health includes Mongo and dry_run |
| Readiness | `GET /api/v1/ready` | api/v1/routes/health.py | integration/test_v1_api.py, smoke | Mongo + Redis, 503 when either is down |
| Connector status | `GET /api/v1/sources`, `GET /api/connectors` | services/sources.py | unit/test_connectors.py, integration, smoke | all 5 unconfigured |
| Manual job import + score | `POST /api/v1/jobs/import`, `POST /api/jobs/import` | services/jobs.py | integration, smoke | same records on both routes |
| Job list / detail | `GET /api/v1/jobs`, `GET /api/jobs/{id}` | services/jobs.py | integration | v1 returns a page envelope |
| Dry-run application | `POST /api/v1/jobs/{id}/prepare-application`, `POST /api/applications` | services/applications.py | integration, smoke | dry-run only; v1 duplicate is 409 |
| Application list / detail | `GET /api/v1/applications` | services/applications.py | integration | existing documents stay readable |
| Settings | `GET/PUT /api/v1/automation/settings`, `GET/PUT /api/settings` | services/settings.py | integration/test_v1_api.py, unit/test_config.py | Mongo singleton; dry_run forced true |
| Match scoring (baseline) | `calculate_match_score()` | app/matching.py | unit/test_matching.py | hardcoded default skills; redesign in Phase 2 |
| Hourly scan placeholder | Celery `app.tasks.hourly_scan` | app/tasks.py | unit/test_task_safety.py | no external calls |
| Dashboard (4 views) | `/` | frontend/src/App.tsx, api.ts | src/api.test.ts | loads `/api/v1`, loading and error states |

## Conventions
- Layers: routes -> services -> repositories/connectors. No DB or external calls in routes.
- Every new or changed function ships with automated tests. No manual testing.
- Test layout: `backend/tests/unit` (no I/O), `integration` (real Mongo/Redis; skip locally if absent, required in CI), `smoke` (against compose stack, `SMOKE_BASE_URL`), `frontend/src/**/*.test.ts(x)`, `e2e/` (Phase 6).
- Branch per phase `phase-N-name`, PR, CI green, merge. CD publishes images from `main`.
- Never commit secrets or personal data. Never enable live submission by default.

## How to run
- Local CI mirror: `.\scripts\ci.ps1` (`-SkipDocker` without Docker).
- Dev stack: `Copy-Item .env.example .env; docker compose up --build`.
- Deploy published images: set `GHCR_OWNER` in `.env`, then `.\scripts\deploy.ps1`.
- Backend venv: `backend\.venv` (Python 3.12). Local system Python 3.8 is too old; use `py -3.12`.

## Known gaps / environment notes
- Docker Desktop 29.9.2 (Linux containers) is installed. Compose ports bind to 127.0.0.1.
- Legacy `/api/*` routes remain and share the PyMongo repositories with `/api/v1`.

## Change log
- 2026-10-26 Phase 1 test fix: integration readiness test starts an isolated Redis on 127.0.0.1 when the host has none. Compose Redis stays unpublished. Integration tests always use database `job_agent_integration_test`.
- 2026-10-26 Phase 1: PyMongo async replaces Motor; repositories for jobs, applications, settings, and audit; `/api/v1` health, ready, jobs, applications, sources, and settings; legacy routes kept; settings persist in Mongo with dry-run forced on; dashboard reads `/api/v1`; compose healthchecks and localhost-only ports.
- 2026-10-25 Phase 0: git init + baseline commit; secret protection; design docs; unit/integration/smoke tests; CI/CD; CURSOR.md.
