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
backend/app/repositories/      jobs, applications, automation_settings, audit, matches
backend/app/services/          jobs, applications, settings, sources, scoring
backend/app/scoring/           profile reader and phase2-v1 factor engine
backend/app/api/v1/            versioned routes
backend/app/api/legacy.py      original /api/* routes, same services
backend/app/connectors/        base.py, stubs.py, career_page/greenhouse.py (list API, off by default)
backend/tests/unit|integration|smoke
frontend/src/                  App.tsx (4 pages), api.ts loadWorkspace()
```

## Current phase
**Phase 2 in progress.** Milestone 1 (Greenhouse job-list connector) passed review. Milestone 2 (explainable matching) is implemented locally. Milestone 3 adds a manual career-page sync endpoint. Milestone 4 adds a confirmed Sync jobs button on the Connectors page. Beat does not call Greenhouse. `dry_run` stays true and `automation_enabled` stays false.

## Functionality inventory
Update this table whenever a function, endpoint, task, connector, or page is added, changed, or removed.

| Feature | Entry point | Module | Tests | Status |
|---|---|---|---|---|
| Liveness | `GET /health`, `GET /api/v1/health` | app/main.py, api/v1/routes/health.py | integration, smoke | legacy health includes Mongo and dry_run |
| Readiness | `GET /api/v1/ready` | api/v1/routes/health.py | integration/test_v1_api.py, smoke | Mongo + Redis, 503 when either is down |
| Connector status | `GET /api/v1/sources`, `GET /api/connectors` | services/sources.py | unit/test_connectors.py, integration, smoke | four sources unconfigured; career_page is Greenhouse list-only and disabled unless configured |
| Greenhouse job list | `CareerPageConnector`, `sync_greenhouse_boards()` | connectors/career_page, services/discovery.py | unit/test_greenhouse.py, integration/test_greenhouse_sync.py | fixture tests only; Beat does not call it; no apply endpoint |
| Manual Greenhouse sync | `POST /api/v1/sources/career_page/sync` | api/v1/routes/sources.py, services/discovery.py | integration/test_career_page_sync_api.py, unit/test_greenhouse.py, unit/test_task_safety.py | disabled and empty boards return 422 with no HTTP call; scores discovered rows with the existing scorer |
| Manual job import + score | `POST /api/v1/jobs/import`, `POST /api/jobs/import` | services/jobs.py | integration, smoke | same records on both routes |
| Job list / detail | `GET /api/v1/jobs`, `GET /api/jobs/{id}` | services/jobs.py | integration | v1 returns a page envelope |
| Dry-run application | `POST /api/v1/jobs/{id}/prepare-application`, `POST /api/applications` | services/applications.py | integration, smoke | dry-run only; v1 duplicate is 409 |
| Application list / detail | `GET /api/v1/applications` | services/applications.py | integration | existing documents stay readable |
| Settings | `GET/PUT /api/v1/automation/settings`, `GET/PUT /api/settings` | services/settings.py | integration/test_v1_api.py, unit/test_config.py | Mongo singleton; dry_run forced true |
| Match scoring (baseline import) | `calculate_match_score()` | app/matching.py | unit/test_matching.py | still used by manual import; job documents are not rewritten by the new scorer |
| Explainable match scoring | `POST /api/v1/jobs/score`, `POST /api/v1/jobs/{id}/score` | scoring/engine.py, services/scoring.py | unit/test_scoring.py, integration/test_scoring_api.py | unknown factors are excluded; threshold is the stored minimum |
| Profile and resume status | `GET /api/v1/profile/status` | scoring/profile.py | unit/test_profile.py, integration/test_scoring_api.py | read-only; PDF text via pypdf; missing files are reported and not invented |
| Job match storage | `job_matches` | repositories/matches.py | integration/test_scoring_api.py | unique on candidate, job, and matching version |
| Hourly scan placeholder | Celery `app.tasks.hourly_scan` | app/tasks.py | unit/test_task_safety.py | no external calls |
| Dashboard (4 views) | `/` | frontend/src/App.tsx, JobsPage.tsx, CareerPageSync.tsx, api.ts | src/api.test.ts, src/jobFeed.test.tsx, src/syncJobs.test.tsx | Jobs page separates manual test records from discovered listings. Connectors page confirms before a manual Greenhouse sync |

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
- 2026-10-26 Phase 2 milestone 4: Connectors page Sync jobs button calls the manual career-page sync route after confirmation, shows the safe summary, and refreshes the job list. It does not run on page load or change connector settings.
- 2026-10-26 Phase 2 milestone 3 tests: mixed-board rate limit, lock release after a board-loop exception, manual source-id collision, and a non-default stored threshold. httpx request logs stay at WARNING so board tokens in request URLs are not written.
- 2026-10-26 Phase 2 milestone 3: manual `POST /api/v1/sources/career_page/sync` imports Greenhouse list fixtures, updates existing discovered rows, and scores them with the existing explainable scorer. Disabled or empty board configuration makes no external request. Beat is unchanged.
- 2026-10-26 Phase 2 milestone 2 review: `min_score` uses the explainable total, missing profile and resume are reported, PDF text is read with pypdf without writing the file, and CORS allows the dashboard on both localhost and 127.0.0.1.
- 2026-10-26 Phase 2 milestone 2: explainable match scores in `job_matches`, versioned score endpoints, and a Jobs page that filters on the stored minimum and labels manual test records separately. Unknown factors stay unscored. Greenhouse stays disabled.
- 2026-10-26 Phase 2 milestone 1: Greenhouse Job Board list connector for `career_page`, with normalization, retries, rate limit, sync lock, and idempotent discovered-job upsert. Disabled by default. No scheduler calls and no submission.
- 2026-10-26 Phase 1 test fix: integration readiness test starts an isolated Redis on 127.0.0.1 when the host has none. Compose Redis stays unpublished. Integration tests always use database `job_agent_integration_test`.
- 2026-10-26 Phase 1: PyMongo async replaces Motor; repositories for jobs, applications, settings, and audit; `/api/v1` health, ready, jobs, applications, sources, and settings; legacy routes kept; settings persist in Mongo with dry-run forced on; dashboard reads `/api/v1`; compose healthchecks and localhost-only ports.
- 2026-10-25 Phase 0: git init + baseline commit; secret protection; design docs; unit/integration/smoke tests; CI/CD; CURSOR.md.
