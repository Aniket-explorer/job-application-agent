# Phase 2 plan — job discovery

Status: approved. Milestone 1 (Greenhouse list connector) passed review and stays disabled. Milestone 2 (explainable matching and the Jobs page) is implemented locally. Milestone 3 (manual sync API) and milestone 4 (dashboard Sync jobs control) are implemented locally. The connector stays disabled. Beat does not call Greenhouse, and no live Greenhouse call has been made.

Checked on 2026-10-26 against the local `phase-2-job-discovery` branch (`7458a75`, the squash merge of Phase 1) and the provider pages cited below.

This phase pulls the job-domain, connector, and discovery-scheduling work that `docs/IMPLEMENTATION_PLAN.md` currently splits across Phases 2–4. Application submission, Gmail, LinkedIn, Naukri, and Wellfound stay out. On approval, `docs/IMPLEMENTATION_PLAN.md`, `docs/API_SPEC.md`, `docs/DATA_MODEL.md`, `CURSOR.md`, and `README.md` are updated with the code. They are not changed by this plan.

## 1. Recommended first source

Use the existing `career_page` connector to read the **Greenhouse Job Board API** for an allowlist of company board tokens that you supply.

Official reference: [Greenhouse Job Board API](https://docs.greenhouse.io/job-board), reviewed 2026-10-26.

Evidence:

- List jobs is `GET https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs`.
- Greenhouse states: “Job Board data is publicly available, so authentication is not required for any GET endpoints.”
- `?content=true` adds the description, departments, and offices in the same response. The documented `content` value is HTML with entities already escaped.
- The list response includes `id`, `title`, `location.name`, `absolute_url`, `updated_at`, and `meta.total`. The official sample does not include a company name, so the company label comes from your board configuration.
- The documented list call returns the board’s posts in one response. There is no official page or cursor parameter.
- The only authenticated method in that document is application submission: `POST /v1/boards/{board_token}/jobs/{id}` with a Job Board API key. This phase does not call that method and does not ask you for that key.
- Cost is zero. No Greenhouse account is required to read a published board.
- The board token is the public slug, for example the token in `https://boards.greenhouse.io/{board_token}`.

What you must set up before a live sync:

- A local, gitignored list of boards: token plus the company display name you want stored.
- `ENABLE_CAREER_PAGE_CONNECTOR=true` in `.env` only. `.env.example` keeps the flag false and a `dummy-*` token.
- No API key, OAuth client, or Greenhouse login.

Limits of this choice:

- Greenhouse documents the API for building a career site from a company’s own published board. This phase calls only tokens you name. It does not search Greenhouse for every company, crawl career websites, or follow `absolute_url`.
- Official docs do not publish a numeric rate limit. The client treats that as unknown and uses the conservative limits in section 6.
- A board that is not hosted on Greenhouse returns an error for that token only. Lever and Ashby are later adapters, not part of the first sync.
- Jobs on LinkedIn, Naukri, Wellfound, or a company’s own site that does not use this API are not discovered in this phase.

### Sources considered

| Source | What was verified | Decision |
|---|---|---|
| Greenhouse Job Board API | Public GET, no key, official docs, one response per board | First integration |
| Lever Postings API | Official [postings-api](https://github.com/lever/postings-api): `GET https://api.lever.co/v0/postings/{site}?mode=json`, `skip`/`limit` (max 100), no key for published posts | Later `career_page` adapter |
| Ashby public Job Postings API | Official [public job posting API](https://developers.ashbyhq.com/docs/public-job-posting-api): `GET https://api.ashbyhq.com/posting-api/job-board/{name}`, no key | Later `career_page` adapter |
| LinkedIn | [Job Posting API](https://learn.microsoft.com/en-us/linkedin/talent/job-postings/api/overview) is for approved partners posting jobs, and it requires an API agreement. No personal job-search API was found | Stay `unconfigured`. No scraping |
| Naukri | No public developer portal or job-search API. Employer integrations are commercial (Freshteam and Workable both require a Naukri-issued token or paid module). The public site is behind bot checks | Stay `unconfigured`. No session or CAPTCHA bypass |
| Wellfound | [Jobs Terms](https://wellfound.com/terms/jobs) describe the website product. No public candidate job-list API was found. The published programmatic surface found is a recruiter applications MCP, which is the wrong direction | Stay `unconfigured` |
| Arbitrary career-page HTML | No single documented API. Fetching user-supplied URLs would add SSRF and per-site terms risk | Not in this phase |

## 2. Architecture and connector interface

Reuse the Phase 1 path: routes call services, services call repositories and connectors. `ApplicationOrchestrator` is still not a submission path. `apply()` keeps raising `PermissionError`.

New and extended modules:

- `backend/app/connectors/base.py` — extend the current `JobSourceConnector` toward the contract already written in `docs/LLD.md` section 2. Keep `capabilities()` so the current sources API still works.
- `backend/app/connectors/career_page/greenhouse.py` — the only network adapter.
- `backend/app/services/discovery.py` — one sync run: lock, health, fetch, normalize, dedup, match, record history.
- `backend/app/services/normalization.py` — URL canonicalizer and Greenhouse payload mapping.
- `backend/app/services/matching.py` — factor scoring. `app/matching.py` remains as a wrapper so current import tests keep a single entry point until callers move.
- `backend/app/repositories/matches.py`, `sync_runs.py`, `source_integrations.py`.
- Celery tasks stay in `app/tasks.py` and the worker in `app/worker.py`.

```text
POST /api/v1/sources/career_page/sync
        -> DiscoveryService
            -> Redis lock
            -> GreenhouseConnector.discover_jobs()
            -> normalize -> jobs repository (idempotent upsert)
            -> matching -> job_matches
            -> sync_runs + source_integrations
Celery Beat hourly_scan
        -> same DiscoveryService when the connector is enabled
```

Connector contract for this phase:

| Method | Behavior |
|---|---|
| `capabilities()` | `discovery_supported=true` only when the flag is on and at least one valid board is configured. `application_supported=false` always |
| `health_check()` | Checks configuration. It does not call Greenhouse until a sync or an explicit health request |
| `discover_jobs(since)` | For each allowlisted board, one GET. `since` filters already-stored posts by `updated_at` after the response arrives; it is not a Greenhouse query parameter |
| `fetch_job_details(source_job_id)` | Optional single-job GET only if a list item has no description. Same host allowlist |
| `normalize_job(raw)` | Pure function. Invalid rows are skipped and counted, not invented |
| `apply()` | Still raises `PermissionError` |

Every connector call has an explicit timeout (15 seconds), a connect timeout (5 seconds), and no redirect following. Retries: up to 3 for HTTP 429, 502, 503, and 504, using `Retry-After` when it is a positive number of seconds, otherwise exponential backoff starting at 2 seconds. HTTP 400, 401, 403, and 404 are permanent for that board and are not retried. A failure on one board does not discard jobs already imported from earlier boards in the same run.

Pagination is part of the interface even though Greenhouse’s list endpoint has one page: `discover_jobs` returns pages of `RawJob` plus `next_cursor: None`. A future Lever adapter can use `skip`/`limit` without changing the service.

Sync history is a `sync_runs` document per attempt. `source_integrations.career_page` stores the last successful finish time and the last error code. Error text stored in Mongo and returned by the API is a short code (`board_not_found`, `timeout`, `rate_limited`, `invalid_payload`). Request URLs may be logged with the board token redacted. Response bodies are not logged.

Idempotency:

- `source_job_id` is `greenhouse:sha256:{digest}:{job_id}`, where `digest` is the SHA-256 hex of the stripped board token. The raw token is not stored or returned.
- The existing unique index on `(source, source_job_id)` makes a repeat sync update `last_seen_at`, `updated_at`, and changed content instead of inserting a second job.
- The same `canonical_url` updates that same job.
- Same company, title, and location on this source only is a probable duplicate and is linked, not merged, when the source ids differ.
- Cross-source fuzzy merge is not implemented.
- Manual imports keep `source=manual` and are never overwritten by discovery.

SSRF guard: the only host the connector may call is `boards-api.greenhouse.io` over HTTPS on port 443. A board token must match `^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$`. `absolute_url` is stored after canonicalization and is not fetched.

Jobs missing from a later successful board response are marked `stale`. They are not deleted. Existing manual smoke records are never marked stale by this rule.

## 3. Database changes

Existing collections and the three manual smoke jobs stay. New fields are optional so Phase 1 documents still read.

### `jobs` additions

| Field | Notes |
|---|---|
| `origin` | `manual` or `discovered`. Missing on old rows; API treats missing plus `source=manual` as manual |
| `provider` | `greenhouse` for discovered rows |
| `board_digest` | SHA-256 of the public board slug; the raw slug is not stored |
| `company_normalized`, `title_normalized`, `location_normalized` | lowercase trimmed dedup keys |
| `required_skills`, `preferred_skills` | only strings found in the posting |
| `experience_min`, `experience_max` | years, or null when the posting does not state them |
| `remote_type` | `remote`, `hybrid`, `onsite`, or null |
| `content_hash` | SHA-256 of normalized description |
| `first_seen_at`, `last_seen_at` | UTC |
| `possible_duplicate_of` | job id or null |
| `match_score`, `match_factors`, `match_reasons` | kept as the list-view snapshot already written by Phase 1 |

Indexes to add:

- unique partial `canonical_url` where the value is a string
- `(company_normalized, title_normalized, location_normalized)`
- `(origin, last_seen_at)`

The current non-unique `canonical_url` index is replaced by the unique partial index only after a startup check shows no duplicate URLs. If duplicates exist, startup logs a count and skips that index rather than deleting jobs.

### `job_matches`

As in `docs/DATA_MODEL.md`: one document per `(candidate_id, job_id, matching_version)`. The jobs list reads the latest version. Re-scoring inserts a new version and does not rewrite history.

### `source_integrations`

One document, `source=career_page`. Stores enabled flag, capability snapshot, `configuration_status`, `last_success_at`, `last_error_at`, `last_error_code`, `next_allowed_run_at`, and the rate-limit numbers. No tokens and no board list secrets beyond the public slugs.

### `sync_runs`

| Field | Notes |
|---|---|
| `source` | `career_page` |
| `trigger` | `manual` or `schedule` |
| `status` | `queued`, `running`, `succeeded`, `failed`, `skipped` |
| `started_at`, `finished_at` | UTC |
| `boards_attempted`, `boards_failed` | counts |
| `jobs_seen`, `jobs_created`, `jobs_updated`, `jobs_skipped` | counts |
| `error_code` | sanitized |
| `correlation_id` | from the request or the task |

Indexes: `started_at` descending; `(source, status)`.

### `candidate_profiles`

One local profile, `candidate_id=default-candidate`. Fields used in this phase: `skills[]` with name and optional years, `preferred_roles[]`, `work_experience[]` titles and date ranges, `preferred_locations[]`, `work_arrangement_preferences[]`, `original_resume_sha256`, `original_resume_storage_key`. The resume file stays under the gitignored `storage/resumes/` path from `.env.example`. The service reads it and never writes it. Tests use a fictional profile and a fictional resume fixture, never your file.

If the profile file is absent, discovery still stores jobs, and matching records `insufficient_profile` with no score. It does not fill skills from the job text.

## 4. API changes

All new routes are under `/api/v1`. Legacy `/api/*` stays as it is and does not gain a sync action.

| Method | Path | Change |
|---|---|---|
| `GET` | `/api/v1/jobs` | Add `origin=manual\|discovered` and `source`. Response items include `origin`, `provider`, and `match_status` (`scored` or `insufficient_profile`) |
| `GET` | `/api/v1/jobs/{id}` | Add factor breakdown from the latest `job_matches` row: scores, explanations, missing stated requirements, and “not stated” for unknown years or location |
| `POST` | `/api/v1/jobs/import` | Unchanged manual import. Sets `origin=manual` |
| `GET` | `/api/v1/sources` | Add `last_success_at`, `last_error_code`, `configuration_status`. Notes stay free of credentials |
| `POST` | `/api/v1/sources/career_page/sync` | `202` with `sync_id` when a run starts. `409` when a run for that source is already active. `422` when the connector is disabled or no valid board is configured |
| `GET` | `/api/v1/sources/career_page/syncs` | Recent runs, newest first |
| `GET` | `/api/v1/syncs/{id}` | One run |

`dry_run` and `automation_enabled` responses stay forced to `true` and `false`. Sync does not accept a flag that turns either off.

## 5. Matching algorithm

Version string: `phase2-v1`. Default threshold remains the persisted `minimum_match_score` of 50. A job passes only when `total_score >= threshold`.

```text
total = 0.30*skills + 0.25*role + 0.20*experience + 0.15*domain + 0.10*location
```

Each factor is clamped to 0–100 and rounded to one decimal. The total is rounded to one decimal.

Facts the scorer may use:

- Skills, roles, experience dates, locations, and work arrangement that you put in the profile.
- Exact skill terms that also occur in the original resume text, using the versioned synonym list already started in `app/matching.py`. A synonym counts only as that profile skill, not as a new skill.
- Requirements that appear in the job text. A skill is required only when it occurs under a heading such as “Requirements”, “Qualifications”, or “Must have”. Otherwise a detected skill is preferred.
- Years and remote or location phrases only when the posting states them.

Facts the scorer must not use:

- Skills that appear in the job but not in the profile or resume.
- Years, degrees, or employers inferred to fill a gap.
- A neutral 50 for a factor the posting or the profile does not state. Unknown factors are excluded from the average, stored with `score=null` and `status=unknown`, and named in `warnings`. A confirmed mismatch is a real number, including 0.

Factor rules, as implemented in milestone 2:

- **Skills (30).** Required hits count double versus preferred hits. The denominator is the weighted required skills, or the preferred skills when the posting has no required section. No possessed or requested skills leaves the factor unknown. A required skill absent from the profile and resume lowers the score and is listed as missing. It is not a hard block in this phase.
- **Role (25).** 100 when the full preferred role or experience title is contained in the job title. Otherwise the score is the share of overlapping title tokens. No overlap is 0. No preferred roles and no experience titles leaves the factor unknown. There is no generic engineering bonus.
- **Experience (20).** 100 when the years computed from profile start and end dates fall inside a range stated by the posting. Each year outside that range removes 25 points, floored at 0. If either side has no years, the factor is unknown.
- **Domain (15).** Overlap of explicit project and experience domain strings with the job text. If the profile states domains and none appear in the job text, the score is 0. If the profile states no domain, the factor is unknown.
- **Location (10).** 100 when the stated arrangement is preferred, or the stated place matches `preferred_locations`. 0 when the arrangement is excluded, the arrangement is known and not preferred, or a stated place does not match. If neither side states a place or an arrangement, the factor is unknown.

The total uses only factors with a numeric score. Their weights are renormalized, and the result is clamped to 0–100. If every factor is unknown, `total_score` is null and `meets_threshold` is false. The comparison uses the persisted `minimum_match_score`, which defaults to 50.

The Jobs page shows the total, the five factors, the matched skills, and the missing stated skills. Prepare dry-run continues to use the existing application service and still refuses live submission.

## 6. Scheduling and rate limits

`app.tasks.hourly_scan` remains the Beat entry so the current schedule does not grow a second timer. Its body becomes “dispatch discovery”, not a direct HTTP call.

- Beat keeps the 3600-second schedule already in `worker.py`.
- The task returns `skipped` without a network call when the career-page flag is off, the board list is empty, `global_pause` is true, or `next_allowed_run_at` is in the future.
- The interval used after a successful run is `search_interval_minutes` from persisted settings (already bounded to 60–1440).
- A manual `POST .../sync` is allowed while `global_pause` is true because you asked for it. It still takes the same lock and the same rate limit. It cannot set `automation_enabled`.
- Overlap: Redis `SET lock:discovery:career_page {token} NX PX 900000`. The holder refreshes the lock while the run is alive. Release is compare-and-delete. A second manual or scheduled run gets `409` / `skipped` and does not call Greenhouse.
- Per run: at most 25 boards, one HTTP request per board, at least 2 seconds between boards.
- Per board: at most one list request per 60 minutes, tracked by Redis key `ratelimit:greenhouse:sha256:{digest}`. The key does not contain the raw board token.
- The worker process is the only process that performs the HTTP calls. The API process enqueues the Celery task and returns `202`. In tests, a synchronous executor replaces Celery so the suite does not need a running worker.

`prepare_application` is unchanged and still returns submitted false.

## 7. Testing and acceptance

Automated tests ship with the code. CI does not call Greenhouse.

- Unit: canonical URL, board-token and host rejection, HTML-entity description decoding using the official sample shape, skill extraction that does not add skills absent from the fixture profile, scores at 49.9, 50.0, and 50.1 against the threshold, unknown experience staying 50 with an explicit reason.
- Integration, real Mongo and Redis, HTTP mocked at the client boundary: first sync inserts rows; second sync updates the same ids; a parallel sync is skipped; a 404 on one board is recorded and other fixture boards still import; manual jobs with `source=manual` stay `origin=manual`; settings remain `dry_run=true` and `automation_enabled=false`.
- Frontend: the jobs payload marks manual and discovered rows, and the sync button posts to the versioned sync route.
- Smoke tests must not call Greenhouse and must not add another persisted demo job. The existing smoke import stays behind the current smoke script only.

Acceptance, all required:

1. With a fixture board response, the dashboard list shows those jobs as discovered, with a score and a written breakdown.
2. The three existing manual smoke jobs remain, labeled manual, and are not rewritten.
3. A second sync does not duplicate fixture jobs.
4. Scheduled and manual runs cannot overlap.
5. LinkedIn, Naukri, Wellfound, and Gmail still report not configured, and no code path calls them.
6. Logs and API responses contain no resume body and no secret values.
7. A live check, which you approve separately by putting real board tokens in `.env`, imports at least one unchanged Greenhouse job for a token you choose. Until that check passes, the connector status in the UI says configured for local fixtures only when the flag is on, and the phase is not described as verified against Greenhouse.

## 8. Credentials, configuration, cost, and risks

| Item | Plan |
|---|---|
| Credentials | None for Greenhouse GET. Do not create a Job Board API key |
| Local config | `ENABLE_CAREER_PAGE_CONNECTOR`, `GREENHOUSE_BOARDS` as `token\|Company Name` pairs separated by commas. Example file keeps `dummy-board\|Dummy Company` |
| Profile and resume | You place them in gitignored `storage/` after approval. The app reads the resume and does not write it |
| Cost | Greenhouse public GET: no fee. Infrastructure stays local Compose |
| Data already in Mongo | The three dry-run smoke jobs and their applications stay |

Risks:

- Board tokens can be wrong or the company can withdraw the board. The run records `board_not_found` and continues.
- Greenhouse can change or throttle the undocumented limit. The client stops on 429 and waits for the next allowed window.
- Using the public board API for a personal allowlist is narrower than a job-board crawl, and it still depends on Greenhouse continuing to publish unauthenticated GETs. If the docs or terms later forbid this use, the connector returns `unconfigured` and makes no calls.
- Description HTML is untrusted. The API returns text, and the dashboard does not render description HTML.
- Skill headings will be wrong on some posts. Scores stay explainable, and missing skills are listed rather than blocked.
- Your real profile is personal data. It stays in `storage/` and out of git, logs, and fixtures.

## 9. Implementation milestones

Each milestone is implemented only after you approve this plan, and each one stops with tests before the next.

1. **Profile and matching, no network.** Read-only profile and resume checksum, factor scorer, `job_matches`, explanations. Existing import path uses the new scorer.
2. **Greenhouse adapter against fixtures.** Connector interface, host allowlist, normalization, idempotent upsert, stale marking, sync history.
3. **Manual sync API.** `202`, `409`, and `422` cases. Worker task calls the same service. API process does not fetch jobs itself.
4. **Beat dispatch and rate limits.** Pause skips the schedule. Locks and per-board spacing covered by tests.
5. **Dashboard.** Jobs page separates manual and discovered rows and shows the breakdown. Connectors page shows career-page health, last sync, and a Sync button. Other connectors stay unchanged.
6. **Live check, only when you provide board tokens.** One opted-in test against `boards-api.greenhouse.io`. No sync is run as part of planning or as part of milestones 1–5.

Still deferred: live applications, resume edits, Gmail, LinkedIn, Naukri, Wellfound, Lever, Ashby, and fetching arbitrary career-page URLs.
