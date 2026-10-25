import re

# Starter heuristic only. Replace with a calibrated evaluator and reviewed profile facts.
SKILL_TERMS = {
    "python": ["python"], "fastapi": ["fastapi"], "api": ["rest api", "restful", "api development"],
    "mongodb": ["mongodb", "mongo db"], "redis": ["redis"], "react": ["react", "react.js"],
    "typescript": ["typescript"], "sql": ["sql", "postgresql", "mysql"], "docker": ["docker"],
    "java": ["java"], "javascript": ["javascript", "es6"], "angular": ["angular"],
}

def calculate_match_score(description: str, verified_skills: list[str] | None = None) -> dict:
    """Deterministic baseline. Scores only known skills and role keywords; not an AI verdict."""
    text = description.lower()
    skills = [s.lower() for s in (verified_skills or ["Python", "FastAPI", "MongoDB", "Redis", "REST APIs"])]
    skill_hits = 0
    skill_total = max(len(skills), 1)
    matched = []
    for skill in skills:
        terms = SKILL_TERMS.get(skill, [skill])
        if any(re.search(r"(?<![a-z0-9])" + re.escape(term.lower()) + r"(?![a-z0-9])", text) for term in terms):
            skill_hits += 1
            matched.append(skill)
    skill_score = skill_hits / skill_total * 100
    role_terms = ["engineer", "developer", "software", "backend", "full stack", "sde"]
    role_score = 100.0 if any(term in text for term in role_terms) else 25.0
    # In absence of reliable experience/location facts, keep those dimensions neutral, not fabricated.
    experience_score = 50.0
    domain_score = 50.0
    location_score = 50.0
    score = round(skill_score * .30 + role_score * .25 + experience_score * .20 + domain_score * .15 + location_score * .10, 1)
    reasons = [f"Matched skills: {', '.join(matched) if matched else 'none detected'}", "Experience, domain, and location use neutral placeholders until profile facts are configured."]
    return {"score": score, "factors": {"skills": round(skill_score,1), "role": role_score, "experience": experience_score, "domain": domain_score, "location": location_score}, "reasons": reasons}
