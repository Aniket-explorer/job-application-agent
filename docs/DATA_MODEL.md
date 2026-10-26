# Data Model (MongoDB)

Driver: PyMongo native async (`AsyncMongoClient`). All documents are validated through Pydantic models before writes. All timestamps are UTC `datetime`. Unknown values are stored as `null`, never guessed.

## candidate_profiles
| Field | Type | Notes |
|---|---|---|
| `_id` | ObjectId | |
| `candidate_id` | str | unique |
| `name`, `email` | str | |
| `phone` | str? | |
| `skills` | list[{name, years?, level?}] | verified only |
| `work_experience` | list[{company, title, start, end?, summary, skills[]}] | |
| `education` | list[{institution, degree, field?, start?, end?}] | |
| `projects` | list[{name, summary, skills[], domain?}] | |
| `preferred_roles`, `preferred_locations` | list[str] | |
| `work_arrangement_preferences` | list[`remote`, `hybrid`, `onsite`] | |
| `original_resume_storage_key` | str | opaque key, never a path exposed to API |
| `original_resume_sha256` | str | 64 hex |
| `created_at`, `updated_at` | datetime | |

Indexes: `candidate_id` unique.

The real profile is never committed. Tests use a fictional fixture. Milestone 2 reads `storage/profile.json` from disk instead of this collection. The file is not created automatically. A named `.pdf`, `.txt`, or `.md` resume is read from `storage/resumes/` and is not modified. PDF text extraction uses `pypdf`.

## jobs
| Field | Type | Notes |
|---|---|---|
| `_id` | ObjectId | |
| `source` | str | `manual`, `linkedin`, `naukri`, `wellfound`, `career_pages`, `gmail` |
| `source_job_id` | str? | null when the source has no reliable ID |
| `canonical_url` | str? | see LLD 4.1 |
| `company`, `title` | str? | |
| `company_normalized`, `title_normalized` | str? | dedup keys |
| `description` | str? | untrusted text |
| `required_skills`, `preferred_skills` | list[str] | |
| `experience_min`, `experience_max` | float? | years |
| `location` | str? | |
| `remote_type` | `remote`, `hybrid`, `onsite`, null | |
| `employment_type` | str? | |
| `salary_min`, `salary_max` | float? | |
| `currency` | str? | ISO 4217 |
| `posted_at` | datetime? | |
| `recruiter` | {name?, email?}? | |
| `application_method` | {type: `email`/`career_page`/`job_portal`/`recruiter_contact`/`manual`, target?} | |
| `first_seen_at`, `last_seen_at` | datetime | |
| `status` | `active`, `stale`, `closed`, `expired` | |
| `content_hash` | str | sha256 of normalized description, change detection |
| `possible_duplicate_of` | ObjectId? | set by fuzzy/cross-source signal |
| `created_at`, `updated_at` | datetime | |

Indexes: `(source, source_job_id)` unique, partial filter `source_job_id` exists and is a string; `canonical_url` (unique partial where set); `(company_normalized, title_normalized)`; `(status, last_seen_at)`; `first_seen_at`.

Phase 2 milestone 1 writes these fields on Greenhouse rows only: `origin=discovered`, `provider=greenhouse`, `board_digest`, `company_normalized`, `title_normalized`, `location_normalized`, `posted_at`, `content_hash`, `first_seen_at`, `last_seen_at`. Missing Greenhouse fields are stored as null. The extra unique `canonical_url` index is not created yet. Manual rows are not overwritten by discovery. `source_job_id` is `greenhouse:sha256:{digest}:{job_id}`. `digest` is the full SHA-256 hex of the stripped board token, with case preserved. The digest is not truncated; a hash collision would make the unique `(source, source_job_id)` index update the existing row. `board_digest` stores that same digest. The raw board token is not stored in `source_job_id` or `board_digest`. `canonical_url` is kept only when that URL does not contain the board slug as a host label, path segment, or query value. The Job Board list sample puts the board slug in `absolute_url`, and that response has no separate slug-free job URL. Those links are stored as null. A company-hosted `absolute_url` without the slug is stored as returned. No replacement URL is constructed. Title and description stay the public posting text, even when that text contains the slug. Each legacy `greenhouse:{token}:{job_id}` row is rewritten in one document update at the start of a sync, before any HTTP call. The job `_id` does not change, so applications and `job_matches` stay attached. A second run changes nothing. The sync lock is released if the loop stops early, and the next sync finishes the remaining rows. A legacy discovered row is deleted only when the hashed id already exists on another row and nothing references the legacy `_id`. A manual row, or a row with an application or match, is not deleted; its job response still shows the hashed id.

## job_matches
Implemented in Phase 2 milestone 2. One row per `(candidate_id, job_id, matching_version)`. Re-scoring replaces that row and does not rewrite the job or any application.

| Field | Type | Notes |
|---|---|---|
| `_id` | ObjectId | |
| `candidate_id` | str | `default-candidate` for the local profile |
| `job_id` | str | job ObjectId as a string |
| `matching_version` | str | `phase2-v1` |
| `total_score` | float? | null when no factor can be scored; otherwise 0..100 |
| `threshold` | float | settings value at score time |
| `meets_threshold` | bool | recomputed on read from the current settings threshold |
| `match_status` | str | `scored`, `insufficient_profile`, or `insufficient_information` |
| `factors` | list[{key, weight, status, score?, findings[]}] | `score` is null when `status` is `unknown` |
| `matched_skills`, `missing_skills` | list[str] | missing lists required skills only |
| `warnings` | list[str] | includes `unknown:{factor}` for excluded factors |
| `weight_used`, `weight_excluded` | int | weights are 30, 25, 20, 15, and 10 |
| `content_hash` | str | hash of the job fields that affect the score |
| `profile_fingerprint` | str | hash of the profile and resume text, not the resume body |
| `evaluated_at` | datetime | |

Index in use: `(candidate_id, job_id, matching_version)` unique. The extra `(candidate_id, total_score)` index is not created yet.

## applications
| Field | Type | Notes |
|---|---|---|
| `_id` | ObjectId | |
| `candidate_id` | str | |
| `job_id` | ObjectId | |
| `channel` | `email`, `career_page`, `job_portal`, `recruiter_contact`, `manual` | |
| `status` | see LLD 5.1 | |
| `match_score` | float | snapshot at preparation |
| `original_resume_sha256` | str | checksum actually used |
| `idempotency_key` | str | sha256(candidate, canonical job, channel) |
| `dry_run` | bool | |
| `submission_attempts` | list[{attempt_no, started_at, finished_at?, outcome, error_code?, evidence_ref?, dry_run}] | |
| `submission_started_at`, `submitted_at` | datetime? | |
| `external_confirmation_id` | str? | |
| `confirmation_evidence` | {type, reference, captured_at, note?}? | required for `submitted` |
| `error_code`, `error_message` | str? | message is sanitized |
| `next_followup_at` | datetime? | |
| `created_at`, `updated_at` | datetime | |

Indexes: `(candidate_id, job_id)` unique; `idempotency_key` unique; `(status, updated_at)`; `next_followup_at`.

## recruiter_messages
| Field | Type | Notes |
|---|---|---|
| `_id` | ObjectId | |
| `candidate_id` | str | |
| `application_id` | ObjectId? | |
| `provider` | `gmail` | |
| `provider_message_id`, `provider_thread_id` | str | |
| `sender`, `recipient`, `subject` | str | |
| `snippet` | str? | short excerpt only; no full bodies stored |
| `received_at`, `sent_at` | datetime? | |
| `direction` | `inbound`, `outbound` | |
| `classification` | `job_alert`, `recruiter_outreach`, `interview_invite`, `rejection`, `acknowledgement`, `other` | |
| `classification_confidence` | float 0..1 | |
| `processing_status` | `new`, `processed`, `ignored`, `error` | |
| `created_at` | datetime | |

Indexes: `(provider, provider_message_id)` unique; `provider_thread_id`; `(application_id, received_at)`.

## followups
| Field | Type |
|---|---|
| `_id` | ObjectId |
| `candidate_id` | str |
| `application_id` | ObjectId |
| `due_at` | datetime |
| `status` | see LLD 5.2 |
| `type` | `first_followup`, `second_followup`, `thank_you`, `custom` |
| `draft_message` | str? |
| `sent_at`, `completed_at` | datetime? |
| `cancellation_reason` | str? |
| `created_at`, `updated_at` | datetime |

Indexes: `(status, due_at)`; `(application_id, type)` unique.

## source_integrations
| Field | Type | Notes |
|---|---|---|
| `_id` | ObjectId | |
| `source` | str | unique |
| `enabled` | bool | |
| `capabilities` | dict[capability, status] | snapshot from connector |
| `configuration_status` | `configured`, `unconfigured`, `invalid` | |
| `last_success_at`, `last_error_at` | datetime? | |
| `last_error_code` | str? | |
| `next_allowed_run_at` | datetime? | |
| `rate_limit_configuration` | {max_requests, window_seconds, min_interval_minutes} | |
| `created_at`, `updated_at` | datetime | |

Never stores tokens. OAuth tokens live in the gitignored `secrets/` token store (encrypted at rest from Phase 7).

Indexes: `source` unique; `next_allowed_run_at`.

## audit_events
| Field | Type |
|---|---|
| `_id` | ObjectId |
| `actor_type` | `user`, `system`, `worker`, `scheduler` |
| `actor_id` | str |
| `event_type` | str (e.g. `application.prepared`, `application.blocked`, `automation.paused`) |
| `entity_type`, `entity_id` | str |
| `correlation_id` | str |
| `outcome` | `success`, `failure`, `blocked`, `skipped` |
| `reason` | str? |
| `metadata` | dict (redacted; no credentials or message bodies) |
| `created_at` | datetime |

Indexes: `created_at`; `(entity_type, entity_id, created_at)`; `(event_type, created_at)`.

## Additional collections

### automation_settings (singleton, `_id: "global"`)
Implemented in Phase 1. Fields stored: `dry_run`, `minimum_match_score`, `search_interval_minutes`, `followup_enabled`, `global_pause`, `automation_enabled`, `updated_at`.

Seeded from the environment on first start. After that, MongoDB is the source of truth and is reloaded on startup. Reads and writes force `dry_run=true` and `automation_enabled=false`, so a saved document cannot turn live submission on. `live_channels` is added with the orchestrator in a later phase.

### task_runs
`_id`, `task_name`, `run_key` (e.g. `discovery:linkedin:2026-10-25T18`), `correlation_id`, `status` (`queued`, `running`, `succeeded`, `failed`, `skipped`), `started_at`, `finished_at`, `attempt`, `result_summary`, `error_code`. Indexes: `run_key` unique; `(task_name, started_at)`. A TTL index on `finished_at` (90 days) is allowed here because task runs are operational logs, not application records.

## Retention rule
No TTL indexes on `applications`, `audit_events`, `job_matches`, `followups`, or `recruiter_messages`.
