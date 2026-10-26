# API Specification (`/api/v1`)

## Phase 1 status

Implemented and used by the dashboard:

- `GET /health` (legacy shape, kept)
- `GET /api/v1/health`, `GET /api/v1/ready`
- `GET/POST /api/v1/jobs`, `GET /api/v1/jobs/{job_id}`, `POST /api/v1/jobs/import`, `POST /api/v1/jobs/{job_id}/prepare-application`
- `GET /api/v1/applications`, `GET /api/v1/applications/{application_id}`
- `GET/PUT /api/v1/automation/settings`
- `GET /api/v1/sources`, `GET /api/v1/sources/{source_name}`

The starter routes under `/api/*` call the same services and keep their previous response shapes. Job import still requires the fields the starter accepted (`source_job_id`, `company`, `title`, `description`, `canonical_url`). URL-only import, evaluation tasks, profile, follow-ups, and live submission are later phases. `dry_run` cannot be set to false.

`GET /api/v1/sources` still returns the Phase 1 connector shape and does not include Greenhouse board tokens. `career_page` reports `configured` only when `ENABLE_CAREER_PAGE_CONNECTOR` is true and `GREENHOUSE_BOARDS` contains at least one valid `token|Company` pair.

Phase 2 milestone 2 adds scoring routes. They read `PROFILE_PATH` and, when the profile names one, a `.txt`, `.md`, or `.pdf` resume under `RESUME_STORAGE_PATH`. PDF text is extracted in memory with `pypdf`. The profile and the original resume are never written. Responses omit `name`, `email`, `phone`, and the resume text. A missing profile returns `match_status=insufficient_profile` and `total_score=null`. Invalid profile JSON returns `422 profile_invalid`.

`GET /api/v1/profile/status` returns `profile_present`, `profile_valid`, `resume_text_available`, `warnings`, and `message`. It does not return profile facts or a filename.

`GET /api/v1/jobs?min_score=` filters on the stored explainable `total_score` when `min_score` is greater than 0. A job with no assessment, or an assessment whose total is null, is excluded. The older import `match_score` is not used for that filter. `min_score=0` returns every stored job, including manual test records that have not been scored. Those records still include `origin` so the dashboard can label them.

| Method | Path | Result |
|---|---|---|
| POST | `/api/v1/jobs/score` | Recalculates every stored job and upserts `job_matches` for version `phase2-v1`. Body: `{scored, items[]}` |
| POST | `/api/v1/jobs/{job_id}/score` | One assessment. `404 not_found` when the id is missing or not an ObjectId |
| GET | `/api/v1/jobs` | Also accepts `origin=manual\|discovered`. Each item adds `origin`. `assessment` is present only when a stored match exists. `min_score` above 0 uses the explainable `total_score` and ignores the import score |
| GET | `/api/v1/jobs/{job_id}` | Adds the same `assessment` when one is stored |

`assessment` fields: `total_score` (number or null), `threshold` (the current stored minimum, default 50), `meets_threshold`, `match_status` (`scored`, `insufficient_profile`, or `insufficient_information`), `factors[]` (`key`, `weight`, `status`, `score`, `findings`), `matched_skills`, `missing_skills`, `warnings`, `weight_used`, `weight_excluded`. A factor with `status=unknown` has `score=null` and is left out of the weighted total. A confirmed mismatch is a numeric score, including 0. The total is renormalized over the factors that have a score and stays within 0–100.

Phase 2 milestone 3 adds a manual Greenhouse sync. It does not add a schedule, and it does not change `dry_run` or `automation_enabled`.

| Method | Path | Result |
|---|---|---|
| POST | `/api/v1/sources/career_page/sync` | One list sync for boards already set in `GREENHOUSE_BOARDS` |

`422 connector_disabled` when `ENABLE_CAREER_PAGE_CONNECTOR` is false. `422 no_boards` when the board list is empty or has no valid `token|Company` pair. Both responses are returned before any HTTP client is created. `409 sync_in_progress` when another career-page sync holds the Redis lock. A completed run returns `200` with `boards_checked`, `jobs_fetched`, `jobs_created`, `jobs_updated`, `duplicates_skipped`, `jobs_skipped`, `matches_written`, and `errors` (`[{code}]`). Error codes are short (`board_not_found`, `rate_limited`, `profile_invalid`, and the connector's existing codes). The body does not include board tokens, resume text, or profile contact fields.

The Connectors page shows a Sync jobs button for this route. The button asks for confirmation, stays disabled while the request is in progress, and is not called on page load. A disabled connector or an empty board list is explained from `GET /api/v1/sources` and the button stays disabled. The dashboard does not change `ENABLE_CAREER_PAGE_CONNECTOR` or `GREENHOUSE_BOARDS`.

Discovered rows are stored with `origin=discovered`. `source_job_id` is `greenhouse:sha256:{digest}:{job_id}`, where `digest` is the SHA-256 hex of the board token. Job responses, source status, sync summaries, and error codes do not include the raw token. A legacy id still in the database is returned as that hashed id. The list response's documented job URL is `absolute_url`. The published sample is `https://boards.greenhouse.io/{board_token}/jobs/{id}`, and the payload has no other job URL. `canonical_url` is null when that URL contains the board slug. A company-hosted `absolute_url` is returned unchanged only when Greenhouse includes one and it does not contain the slug. The API does not construct a replacement link. The Jobs page says the external link is unavailable because it contains a protected board identifier. Posting titles and descriptions are returned as published. A repeated sync updates the same `(source, source_job_id)` row. An older `greenhouse:{token}:{job_id}` row is rewritten to the hashed id before the fetch, and a manual row with that key is counted in `duplicates_skipped` and is not overwritten. Jobs missing from a later response are left in place. Created and updated discovered jobs are scored with the existing phase2-v1 algorithm and the stored minimum score. The sync does not create applications and does not call an apply endpoint. Beat still runs only `hourly_scan`, which makes no external request. The Redis rate-limit key is `ratelimit:greenhouse:sha256:{digest}` and still allows one fetch per board per hour.

## 1. Conventions

- JSON only. Timestamps are ISO 8601 UTC. IDs are Mongo ObjectId strings.
- Every response carries an `X-Correlation-ID` header (echoed if the client sent one).
- Authentication: a bearer token (`Authorization: Bearer <token>`) is required on all endpoints except `/health` and `/ready` from Phase 9, and before anything is exposed beyond localhost. Until then the API binds to `127.0.0.1` only.

### Pagination envelope
Query: `page` (default 1, >= 1), `page_size` (default 25, 1..100), `sort` (field, `-` prefix for descending).
```json
{ "items": [], "total": 0, "page": 1, "page_size": 25 }
```

### Error envelope
```json
{ "code": "invalid_state_transition", "message": "Application is not in a retryable state", "correlation_id": "c0ffee...", "details": {} }
```
Internal exception text is never returned.

| HTTP | Codes |
|---|---|
| 400 | `bad_request`, `unsafe_url` |
| 401 / 403 | `unauthenticated`, `forbidden` |
| 404 | `not_found`, `unknown_source` |
| 409 | `conflict`, `duplicate`, `invalid_state_transition` |
| 422 | `validation_error`, `policy_violation`, `below_threshold`, `profile_invalid` |
| 423 | `automation_paused` |
| 429 | `rate_limited` |
| 503 | `integration_unconfigured`, `dependency_unavailable` |
| 500 | `internal_error` |

## 2. Health

| Method | Path | Response |
|---|---|---|
| GET | `/api/v1/health` | `{status: "ok"}` (process alive, no dependency checks) |
| GET | `/api/v1/ready` | `{status: "ready" or "not_ready", checks: {mongodb, redis}}`; 503 when not ready |

## 3. Profile

| Method | Path | Notes |
|---|---|---|
| GET | `/api/v1/profile` | Candidate profile (verified data only) |
| PUT | `/api/v1/profile` | Full replace; validated. Cannot set `original_resume_sha256` directly |
| GET | `/api/v1/profile/resume` | Metadata `{filename, size_bytes, sha256, uploaded_at}`; `?download=true` streams the file. Auth required. Never returns a storage path |
| PUT | `/api/v1/profile/resume` | Multipart upload of the original resume (PDF/DOCX, <= 5 MB); stores file and SHA-256 |

## 4. Jobs

| Method | Path | Notes |
|---|---|---|
| GET | `/api/v1/jobs` | Paginated. Filters: `source`, `status`, `min_score`, `max_score`, `remote_type`, `q` (title/company text), `posted_after` |
| GET | `/api/v1/jobs/{job_id}` | Job plus latest match (factor breakdown, exclusions, explanation) |
| POST | `/api/v1/jobs/import` | Manual import. Body: `JobImportRequest` (url required; other fields optional). URL passes the SSRF guard. Returns `201 {job, created: true}` or `200 {job, created: false, duplicate_of}` |
| POST | `/api/v1/jobs/{job_id}/evaluate` | Enqueues `evaluate_job_match`; `202 {task_run_id}` |
| POST | `/api/v1/jobs/{job_id}/prepare-application` | Runs orchestrator `prepare`. `201 {application}`; `409 duplicate`; `422 below_threshold or policy_violation` with reasons |

`JobImportRequest`:
```json
{ "url": "https://...", "source": "manual", "source_job_id": null, "company": null,
  "title": null, "description": null, "location": null, "remote_type": null }
```

## 5. Applications

| Method | Path | Precondition | Effect |
|---|---|---|---|
| GET | `/api/v1/applications` | - | Paginated. Filters: `status`, `channel`, `dry_run`, `job_id` |
| GET | `/api/v1/applications/{id}` | - | Includes `submission_attempts`, audit trail summary |
| POST | `/api/v1/applications/{id}/retry` | status `failed`, retryable `error_code`, no ambiguous attempt | -> `queued`, enqueue execution (still subject to all orchestrator checks) |
| POST | `/api/v1/applications/{id}/cancel` | status in `needs_review`, `queued`, `failed` | -> `withdrawn` |
| POST | `/api/v1/applications/{id}/confirm` | status `pending_confirmation` or `submitting` timed out | Body `{evidence: {type, reference, note}}` required -> `submitted` |

Invalid state returns `409 invalid_state_transition`.

## 6. Sources

| Method | Path | Notes |
|---|---|---|
| GET | `/api/v1/sources` | All registered connectors: `{source, enabled, configuration_status, capabilities, restrictions, last_success_at, last_error_code, next_allowed_run_at}` |
| GET | `/api/v1/sources/{source_name}` | Single source detail |
| PUT | `/api/v1/sources/{source_name}/settings` | `{enabled, rate_limit_configuration}`. Cannot enable a source whose configuration is `unconfigured`/`invalid` (`503 integration_unconfigured`). Never accepts tokens |
| POST | `/api/v1/sources/{source_name}/health-check` | `202 {task_run_id}` |
| POST | `/api/v1/sources/{source_name}/discover` | `202 {task_run_id}`; `503` if unconfigured; `429` if inside rate-limit window; `423` if paused |

## 7. Automation

| Method | Path | Notes |
|---|---|---|
| GET | `/api/v1/automation/settings` | `{dry_run, global_pause, automation_enabled, min_match_score, discovery_interval_minutes, followups_enabled, live_channels[]}` |
| PUT | `/api/v1/automation/settings` | Validated. Setting `dry_run=false` or adding to `live_channels` is rejected (`422 policy_violation`) unless every listed channel reports `SUBMIT_APPLICATION`/`SEND_EMAIL` = `supported` and the source is enabled |
| POST | `/api/v1/automation/pause` | Sets `global_pause=true` immediately; audit event |
| POST | `/api/v1/automation/resume` | Sets `global_pause=false` only. **Does not** change `dry_run` or `live_channels` |

## 8. Follow-ups

| Method | Path | Notes |
|---|---|---|
| GET | `/api/v1/followups` | Paginated. Filters: `status`, `due_before`, `application_id` |
| POST | `/api/v1/followups` | `{application_id, due_at, type, draft_message?}`; application must be `submitted` or later |
| PATCH | `/api/v1/followups/{id}` | Edit `due_at`, `draft_message`, or `status` (`paused`, `scheduled`, `cancelled` with reason) |
| POST | `/api/v1/followups/{id}/complete` | -> `completed` |

## 9. Activity

| Method | Path | Notes |
|---|---|---|
| GET | `/api/v1/audit-events` | Paginated. Filters: `entity_type`, `entity_id`, `event_type`, `outcome`, `from`, `to` |
| GET | `/api/v1/stats/overview` | Dashboard counts computed from Mongo: discovered, matching threshold, submitted, pending_confirmation, needs_review, failed, upcoming follow-ups, recent replies |

## 10. Legacy starter routes (deprecated)

| Starter route | Replacement | Removal |
|---|---|---|
| `GET /health` | `GET /api/v1/health`, `GET /api/v1/ready` | Phase 6 |
| `GET /api/connectors` | `GET /api/v1/sources` | Phase 6 |
| `POST /api/jobs/import` | `POST /api/v1/jobs/import` | Phase 6 |
| `GET /api/jobs`, `GET /api/jobs/{id}` | `/api/v1/jobs...` | Phase 6 |
| `POST /api/applications` | `POST /api/v1/jobs/{id}/prepare-application` | Phase 6 |
| `GET /api/applications` | `GET /api/v1/applications` | Phase 6 |
| `GET/PUT /api/settings` | `/api/v1/automation/settings` | Phase 6 |
