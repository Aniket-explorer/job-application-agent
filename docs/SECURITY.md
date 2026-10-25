# Security Design

## 1. Assets
- Gmail OAuth client secret and refresh tokens.
- The original resume and candidate profile (personal data).
- Application history and recruiter correspondence.
- The ability to submit applications or send email on the candidate's behalf.

## 2. Threats and controls

| Threat | Control |
|---|---|
| Secrets pushed to the public GitHub repo | `.gitignore`, gitleaks pre-commit hook, gitleaks required CI check, GitHub secret scanning and push protection. Only `dummy-*` placeholders are allowlisted |
| Personal data pushed to GitHub | `storage/`, `secrets/`, resume files gitignored; tests use a fictional candidate fixture |
| Prompt injection via job descriptions, web pages, or emails ("ignore previous instructions, apply to...") | All external content is untrusted data. It is never used as instructions, never selects destinations, and never changes settings. Policy decisions come only from the orchestrator checks in LLD 6 |
| SSRF when fetching job URLs | URL guard: `http`/`https` only; resolve DNS and reject private, loopback, link-local, multicast, and reserved addresses (IPv4 and IPv6) and `localhost`; re-check after every redirect (max 3); connect to the resolved IP to prevent DNS rebinding; 10 s timeout; 2 MB body limit; allowed content types `text/html`, `application/json`, `application/ld+json` |
| Browser workers navigating to arbitrary sites | Per-connector domain allowlist. Workers refuse navigation outside it |
| Duplicate or unintended submissions | Unique indexes, idempotency key, Redis locks, conditional state transitions, no auto-retry of ambiguous attempts |
| Runaway automation | `global_pause` (default on), `dry_run` (default on), `automation_enabled` (default off), per-channel `live_channels` allowlist, per-source rate limits |
| UI bypass of policy | All checks are in backend services. No endpoint calls a channel directly |
| Leaking internals in API errors | Error envelope with code and correlation ID only; details in logs |
| Credential leakage in logs | Log redaction filter for keys matching `token`, `secret`, `password`, `authorization`, `cookie`, `api_key`; email bodies never logged |
| Unauthorized dashboard or API access | Bind to `127.0.0.1` (Phase 1). Bearer-token auth before any non-localhost exposure (Phase 9) |
| Resume tampering | SHA-256 verified before every attachment; mismatch is a hard exclusion |

## 3. Gmail OAuth scope plan

| Stage | Scope | When |
|---|---|---|
| Read-only ingestion | `https://www.googleapis.com/auth/gmail.readonly` | Phase 7 |
| Sending applications and follow-ups | `https://www.googleapis.com/auth/gmail.send` (separate consent) | Phase 8, only when the sending feature is implemented and tested |

Scopes are to be re-verified against current Google documentation at implementation time. No Gmail password is ever stored. Revoked or invalid grants mark the integration `unconfigured` and stop retries (no retry loops on `invalid_grant`).

## 4. Secret handling

- Real values: local `.env` and `secrets/` only (both gitignored).
- Committed: `.env.example` with `dummy-*` placeholders.
- CI: needs no real secrets; external APIs are mocked. CD uses the built-in `GITHUB_TOKEN` to push images.
- Token store: `secrets/tokens/` on a Docker volume, file permissions restricted; encryption with a key from `APP_SECRET_KEY` (Phase 7).
- Disconnect: `DELETE /api/v1/sources/gmail/connection` revokes the token at Google and deletes it locally (Phase 9).

## 5. If a secret is ever committed

1. Revoke or rotate the secret at the provider immediately (removing it from git is not enough).
2. Remove it from history (`git filter-repo`) and force-push only after rotation.
3. Record the incident in `CURSOR.md` change log (without the secret).

## 6. Local-only posture

MongoDB and Redis are never exposed beyond `127.0.0.1`. No port forwarding or tunnels until authentication is in place.
