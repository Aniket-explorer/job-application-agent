# API Specification (`/api/v1`)

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
| 422 | `validation_error`, `policy_violation`, `below_threshold` |
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
