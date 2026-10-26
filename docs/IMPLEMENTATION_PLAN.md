# Implementation Plan

Every phase: branch `phase-N-<name>`, open a PR, CI must be green, update `README.md` and `CURSOR.md`, merge. The app must still run after each phase.

## Phase 0 - Repository inspection and design (this PR)
- [x] Inspect starter, record findings in `CURSOR.md`
- [x] git init, baseline commit, `.gitignore`, `.gitattributes`
- [x] Secret protection: gitleaks config, pre-commit hooks, dummy `.env.example`
- [x] Design docs: PRD, HLD, LLD, API_SPEC, DATA_MODEL, SECURITY, this plan
- [x] CI/CD workflows, `scripts/ci.ps1`, `scripts/deploy.ps1`
- [x] Tests reorganized into `unit/`, `integration/`, `smoke/`
- [x] Public GitHub repo, secret scanning and push protection, branch protection

## Phase 1 - Backend foundation
- [x] Package layout for this phase: `core/`, `db/`, `repositories/`, `services/`, `api/v1/`
- [x] `core/config.py` with the `.env` keys and startup validation
- [x] PyMongo async client, `db/indexes.py`, Motor removed
- [x] Repositories for jobs, applications, settings, and audit. Settings replace the in-memory global
- [x] Structured JSON logging, correlation ID middleware, secret redaction
- [x] Error envelope and exception handlers
- [x] `/api/v1/health`, `/api/v1/ready` (Mongo + Redis)
- [x] Versioned job, application, source, and settings routes. Legacy `/api/*` routes call the same services
- [x] Dashboard reads `/api/v1` and shows loading and error text
- [x] Compose: healthchecks, ports bound to `127.0.0.1`, `depends_on: condition: service_healthy`
- [x] Pinned backend dependencies
- [x] Tests: config validation, ready endpoint, error envelope, settings persistence, duplicate prevention, existing document shape

Exit: backend starts, `/ready` reports Mongo and Redis ok. Matching redesign, SSRF checks, and background evaluation stay in Phase 2. Live submission stays off.

## Phase 2 - Job domain
- [ ] Job models, repository, URL canonicalizer + SSRF guard
- [ ] Normalization and deduplication services
- [ ] `/api/v1/jobs` list (filters, pagination), details, import
- [ ] Matching service with factor rules (LLD 4.3), `job_matches` repository
- [ ] Tests: schema validation, normalization, dedup signals, score calc, threshold 49/50/51, unsafe URLs

Exit: a manually imported job is scored and returned with its breakdown.

Milestone 1 of the approved `PHASE_2_PLAN.md` is the Greenhouse list connector. Milestone 2 stores explainable scores in `job_matches` and shows them on the Jobs page. Unknown factors are excluded instead of scored as 50. Milestone 3 adds a manual `POST /api/v1/sources/career_page/sync`. Milestone 4 adds a confirmed Sync jobs button on the Connectors page. The checklist above is still open. Beat does not call Greenhouse.

## Phase 3 - Connector framework
- [ ] `Capability`, `CapabilityStatus`, `JobSourceConnector`, `ApplicationChannel`
- [ ] Connector registry; packages for linkedin, naukri, wellfound, career_pages, gmail (unconfigured/unverified)
- [ ] Mock connectors
- [ ] `source_integrations` repository; `/api/v1/sources*` endpoints
- [ ] Tests: missing credentials -> unconfigured, unsupported capability raises, registry lists all five

Exit: all five sources appear; unsupported operations fail safely.

## Phase 4 - Background processing
- [ ] `tasks/` package, Celery config, Beat schedule
- [ ] `task_runs`, Redis locks, rate limiter
- [ ] `dispatch_discovery`, `discover_source_jobs`, `normalize_discovered_job`, `evaluate_job_match`
- [ ] Retry policy (transient vs permanent)
- [ ] Tests: idempotent tasks, overlap prevention, rate-limit enforcement, unconfigured sources skipped

Exit: scheduled discovery runs with mock connector, no duplicates, no submissions.

## Phase 5 - Application domain
- [ ] Profile and resume endpoints; private storage; SHA-256
- [ ] Application model, state machine, repository with conditional transitions
- [ ] Eligibility service, orchestrator (LLD 6), audit service
- [ ] `/api/v1/applications*`, `/api/v1/automation/*`
- [ ] Tests: dry-run blocks external call, pause blocks, duplicates prevented, state transitions, checksum mismatch blocks

Exit: dry-run applications are created and tracked safely.

## Phase 6 - React dashboard
- [ ] Pinned deps, React Router, TanStack Query, API client with error envelope
- [ ] All ten pages; pause switch; dry-run banner; status labels
- [ ] `/api/v1/stats/overview`; remove legacy `/api/*` routes
- [ ] Vitest + RTL tests; Playwright e2e suite enabled in CI

Exit: dashboard shows backend data and accurate dry-run status.

## Phase 7 - Gmail ingestion
- [ ] OAuth flow (readonly scope), encrypted token store
- [ ] Ingestion task, alert parsing, job URL extraction -> import pipeline
- [ ] Recruiter reply association
- [ ] Tests with recorded/mocked Gmail API responses

Exit: authorized emails are ingested; nothing is sent.

## Phase 8 - Permitted application integrations
- [ ] Per source: verify documentation, document capabilities below, implement only permitted workflows
- [ ] First: one career page with a documented, permitted integration
- [ ] Gmail send as separate capability and consent
- [ ] Tests: duplicate protection, confirmation evidence; live stays disabled until passing

## Phase 9 - Follow-ups and hardening
- [ ] Follow-up scheduling, classification, cancellation rules
- [ ] Authentication; integration disconnect and token revocation
- [ ] Monitoring, backup and restore docs (`mongodump` script), e2e tests

Exit: runs locally and is safely monitored from the dashboard.

## External integrations requiring verification

Nothing below is assumed. Each row must be checked against the provider's current documentation and terms before any implementation, and the result recorded here.

| Source | Discovery candidates | Submission | Needs from you | Status |
|---|---|---|---|---|
| LinkedIn | Job alert emails via Gmail; user-provided job URLs | No public apply API for individuals is known; treat as `manual` channel unless verified otherwise | Job alerts enabled on your account | To verify |
| Naukri | Job alert emails via Gmail; user-provided URLs | Not assumed; `manual` until verified | Job alerts enabled | To verify |
| Wellfound | Job alert emails via Gmail; user-provided URLs | Not assumed; `manual` until verified | Job alerts enabled | To verify |
| Company career pages | Greenhouse Job Board API `GET /v1/boards/{token}/jobs?content=true` (public, no key). Lever and Ashby later. No HTML crawling | Not implemented. The Greenhouse apply POST is not called | `ENABLE_CAREER_PAGE_CONNECTOR` and `GREENHOUSE_BOARDS` in `.env` | List read implemented, disabled by default, not scheduled |
| Gmail | Gmail API, `gmail.readonly` | `gmail.send` in Phase 8 | Google Cloud project, OAuth consent screen, OAuth client (Desktop/Web) | To configure |

## CI/CD stages (no manual testing)
1. `secrets-scan` - gitleaks
2. `backend-unit` - ruff + pytest unit
3. `frontend` - typecheck, vitest, build
4. `backend-integration` - pytest against Mongo and Redis service containers, coverage gate
5. `docker-build` - build images, validate compose
6. `smoke` - compose stack up, smoke tests through the API
7. `e2e` - Playwright (enabled in Phase 6)
8. CD on `main` - publish images to GHCR; local `scripts/deploy.ps1`
