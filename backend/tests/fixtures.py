"""Fictional test data. Never put real personal details in this repository."""

TEST_CANDIDATE = {
    "candidate_id": "test-candidate",
    "name": "Test Candidate",
    "email": "candidate@example.com",
    "skills": ["Python", "FastAPI", "MongoDB", "Redis", "REST APIs"],
}


def job_payload(source_job_id: str, **overrides) -> dict:
    payload = {
        "source": "manual",
        "source_job_id": source_job_id,
        "company": "Example Co",
        "title": "Backend Engineer",
        "location": "Remote",
        "description": "Backend software engineer building REST API services with Python, FastAPI, MongoDB and Redis.",
        "canonical_url": f"https://jobs.example.com/{source_job_id}",
    }
    payload.update(overrides)
    return payload
