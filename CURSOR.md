# CURSOR.md - Project Memory

Read this first. Keep it short. Details live in `docs/`; this file summarizes and links.

## Goal
Personal AI job application agent: discover jobs (LinkedIn, Naukri, Wellfound, career pages, Gmail), score them against a verified profile (threshold 50), prepare and later submit applications through permitted channels using the **original resume only**, and track replies and follow-ups. Dry-run by default. Telegram/WhatsApp are out of scope.

## Stack
Python 3.12, FastAPI, Pydantic v2, MongoDB (PyMongo async from Phase 1; starter still uses Motor), Redis, Celery + Beat, React 19 + TypeScript + Vite 6, Vitest, Docker Compose on Windows. CI/CD on GitHub Actions; images on GHCR.

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
backend/app/main.py           starter routes (legacy /api/*), to be split in Phase 1
backend/app/{config,db,models,matching,tasks,worker}.py
backend/app/connectors/       base.py + stubs.py (all unconfigured)
backend/tests/unit|integration|smoke   fixtures.py = fictional test data
frontend/src/                 App.tsx (single page), api.ts, api.test.ts
scripts/ci.ps1  scripts/deploy.ps1
.github/workflows/ci.yml cd.yml
docker-compose.yml (dev)  docker-compose.release.yml (GHCR images)
```

## Current phase
**Phase 0 complete (design + repo + CI/CD).** Next: Phase 1 backend foundation (see IMPLEMENTATION_PLAN). Wait for user confirmation before starting each phase.

## Functionality inventory
Update this table whenever a function, endpoint, task, connector, or page is added, changed, or removed.

| Feature | Entry point | Module | Tests | Status |
|---|---|---|---|---|
| Liveness + Mongo ping | `GET /health` | app/main.py | integration/test_jobs_and_applications_api.py, smoke | legacy, replace with /api/v1/health+ready |
| Connector status list | `GET /api/connectors` | app/connectors/stubs.py | unit/test_connectors.py, smoke | all 5 unconfigured |
| Manual job import + score | `POST /api/jobs/import` | app/main.py, app/matching.py | integration, smoke | legacy |
| Job list / detail | `GET /api/jobs`, `GET /api/jobs/{id}` | app/main.py | integration | legacy |
| Dry-run application create | `POST /api/applications` | app/main.py | integration, smoke | dry-run only, dedup by unique index |
| Application list | `GET /api/applications` | app/main.py | integration | legacy |
| Settings (dry-run locked) | `GET/PUT /api/settings` | app/main.py | integration, smoke | in-memory, Phase 1 persists to Mongo |
| Match scoring (baseline) | `calculate_match_score()` | app/matching.py | unit/test_matching.py | hardcoded default skills; redesign in Phase 2 |
| Hourly scan placeholder | Celery `app.tasks.hourly_scan` | app/tasks.py, app/worker.py | unit/test_task_safety.py | no external calls |
| Dashboard (4 views) | `/` | frontend/src/App.tsx | src/api.test.ts (client only) | starter UI, rebuilt in Phase 6 |

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
- Docker Desktop not installed on the dev laptop yet; docker stages run only in CI until installed.
- Starter uses Motor and legacy `/api/*` routes; migration planned in Phase 1 and Phase 6.

## Change log
- 2026-10-25 Phase 0: git init + baseline commit; secret protection (gitignore, gitleaks, pre-commit, dummy .env.example); design docs; tests split into unit/integration/smoke with new integration and smoke suites; frontend deps pinned + first vitest; frontend Dockerfile; release compose; CI (scan, unit, frontend, integration+coverage, docker build, smoke, e2e placeholder) and CD (GHCR); scripts/ci.ps1, scripts/deploy.ps1; CURSOR.md + always-apply rule.
