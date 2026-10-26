# Product Requirements Document

## 1. Purpose

A personal, background-running assistant that discovers relevant jobs, scores them against a verified candidate profile, prepares applications using the candidate's **original, unmodified resume**, submits through **verified and permitted** channels only, and tracks recruiter responses and follow-ups.

It is not a scraper and not a chatbot. It is a job discovery engine, matching engine, application orchestrator, set of source connectors, and a monitoring dashboard.

## 2. Users

One user: the candidate who owns the deployment, running it on their own Windows laptop with Docker Desktop.

## 3. Goals

1. Reduce manual effort in finding and applying to relevant jobs.
2. Never submit a duplicate application.
3. Never submit anything inaccurate (no fabricated skills, dates, or declarations).
4. Make every automated decision visible and auditable from the dashboard.
5. Add new job sources without changing core logic.

## 4. Non-goals

- Telegram and WhatsApp groups as sources (explicitly out of scope).
- Bypassing logins, CAPTCHAs, rate limits, anti-bot controls, or platform terms.
- Rewriting, regenerating, or "tailoring" the resume.
- Multi-user or SaaS hosting.
- Microservices.

## 5. Operating configuration

| Setting | Initial value |
|---|---|
| Sources | LinkedIn, Naukri, Wellfound, company career pages, Gmail recruiter emails |
| Minimum match score | 50 (configurable) |
| Resume | Original file only, SHA-256 verified before every use |
| Discovery frequency | Hourly, subject to per-source limits |
| Application mode | Dry-run first; live only per channel after tests pass and explicit enablement |
| Email provider | Gmail (OAuth 2.0, read-only first, send later) |
| Follow-ups | Enabled, reminders only at first (no automatic sending) |

## 6. Functional requirements

### 6.1 Discovery
- Each source is a connector that declares its capabilities, restrictions, and required configuration.
- Discovery methods depend on what each source actually permits: official API (only if verified), email alerts, public feeds, user-provided URLs, or permitted browser automation.
- An unconfigured connector reports `unconfigured` and returns no jobs. It never pretends success.

### 6.2 Normalization
Every job is converted to one internal schema (see [DATA_MODEL.md](DATA_MODEL.md)). Unknown fields stay `null`; nothing is invented.

### 6.3 Deduplication
Ordered signals: source + source job ID, canonical URL, company + normalized title. Fuzzy similarity is a secondary signal that flags a possible duplicate for review; it never merges by itself.

### 6.4 Matching
Weighted score 0-100: technical skills 30, role and responsibilities 25, experience 20, domain and projects 15, location and work arrangement 10. A score of at least the threshold (50) makes a job **eligible for evaluation**, never **authorized for submission**. Hard exclusions always win.

### 6.5 Resume
Original file stored privately with its SHA-256. Each application records the checksum used. The checksum is verified before attaching.

### 6.6 Applications
Channels: email, career page, job portal, recruiter contact, manual. Lifecycle statuses are defined in [LLD.md](LLD.md#5-state-machines). An application is only `submitted` with confirmation evidence.

### 6.7 Email
Gmail read-only ingestion first. Sending is a separate capability with its own OAuth scope, added later.

### 6.8 Follow-ups
Reminder created after a confirmed submission, paused on meaningful reply, cancelled on rejection, withdrawal, or offer. Follow-up messages are drafts reviewed by the user before sending.

### 6.9 Dashboard
Pages: Overview, Job Feed, Job Details, Application Tracker, Application Details, Recruiter Messages, Follow-Ups, Source Integrations, Automation Settings, Activity and Audit Logs. Search, filters, pagination, status indicators, and a global pause switch. All numbers come from the API.

## 7. Success metrics

- 0 duplicate submissions.
- 0 applications marked `submitted` without evidence.
- 100% of evaluated jobs have a stored score breakdown and decision reasons.
- Every important decision has an audit event.
- CI green on every merge; no manual test steps.

## 8. Constraints

- Backend: Python 3.12, FastAPI, Pydantic v2, PyMongo async, Celery and Celery Beat, Redis.
- Frontend: React, TypeScript, Vite, React Router, TanStack Query.
- Local deployment: Docker Desktop and Docker Compose on Windows.
- Public GitHub repository: only code, docs, and dummy credentials are committed. No personal data.
