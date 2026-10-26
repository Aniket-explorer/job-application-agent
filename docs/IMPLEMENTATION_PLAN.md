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
- [ ] Package layout from LLD 1; app factory; routers under `/api/v1`
- [ ] `core/config.py` with all `.env` keys, startup validation
- [ ] PyMongo async client, `db/indexes.py`, remove Motor
- [ ] Repository base class; `automation_settings` repository (replaces in-memory global)
- [ ] Structured JSON logging, correlation ID middleware, redaction filter
- [ ] Error envelope and exception handlers
- [ ] `/api/v1/health`, `/api/v1/ready` (Mongo + Redis)
- [ ] Compose: healthchecks, ports bound to `127.0.0.1`, `depends_on: condition: service_healthy`
- [ ] Pinned backend dependencies
- [ ] Tests: config validation, ready endpoint (up/down), error envelope, settings persistence

Exit: backend starts, `/ready` reports Mongo and Redis ok; CI green.

## Phase 2 - Job domain
- [ ] Job models, repository, URL canonicalizer + SSRF guard
- [ ] Normalization and deduplication services
- [ ] `/api/v1/jobs` list (filters, pagination), details, import
- [ ] Matching service with factor rules (LLD 4.3), `job_matches` repository
- [ ] Tests: schema validation, normalization, dedup signals, score calc, threshold 49/50/51, unsafe URLs

Exit: a manually imported job is scored and returned with its breakdown.

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
| Company career pages | Public ATS job-board APIs (for example Greenhouse and Lever job boards) and JSON-LD `JobPosting` on public pages | Per site; only where a documented, permitted application method exists | List of target companies | To verify |
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
