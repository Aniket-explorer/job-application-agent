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

The real profile is never committed. Tests use a fictional fixture.

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

## job_matches
| Field | Type |
|---|---|
| `_id` | ObjectId |
| `candidate_id` | str |
| `job_id` | ObjectId |
| `technical_skills_score`, `role_responsibility_score`, `experience_score`, `domain_relevance_score`, `location_score` | float 0..100 |
| `total_score` | float 0..100 |
| `threshold` | float |
| `hard_exclusions` | list[{code, detail}] |
| `explanation` | list[str] |
| `evaluated_at` | datetime |
| `matching_version` | str |

Indexes: `(candidate_id, job_id, matching_version)` unique; `(candidate_id, total_score)`.

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
`dry_run` (default true), `global_pause` (default true), `automation_enabled` (default false), `min_match_score` (50), `discovery_interval_minutes` (60), `followups_enabled` (true), `live_channels` ([]), `updated_at`, `updated_by`. Seeded from environment on first start; afterwards Mongo is the source of truth.

### task_runs
`_id`, `task_name`, `run_key` (e.g. `discovery:linkedin:2026-10-25T18`), `correlation_id`, `status` (`queued`, `running`, `succeeded`, `failed`, `skipped`), `started_at`, `finished_at`, `attempt`, `result_summary`, `error_code`. Indexes: `run_key` unique; `(task_name, started_at)`. A TTL index on `finished_at` (90 days) is allowed here because task runs are operational logs, not application records.

## Retention rule
No TTL indexes on `applications`, `audit_events`, `job_matches`, `followups`, or `recruiter_messages`.
