import re
from typing import Any

from pydantic import BaseModel, Field

from app.matching import SKILL_TERMS

_JOB_SKILLS = {
    **SKILL_TERMS,
    "kubernetes": ["kubernetes"],
    "aws": ["aws"],
    "postgres": ["postgresql", "postgres"],
}

MATCHING_VERSION = "phase2-v1"
WEIGHTS = {
    "technical_skills": 30,
    "role": 25,
    "experience": 20,
    "domain": 15,
    "location": 10,
}
_TOKEN_RE = re.compile(r"[a-z0-9]+")
_STOP = {"and", "the", "for", "with", "job", "role"}
_REQUIRED_HEADING = re.compile(
    r"(?is)(?:requirements|qualifications|must[- ]have|required skills|what you(?:'|’)ll need)\s*[:\-]\s*(.+?)(?=(?:preferred|responsibilities|benefits|about us|about the)\s*[:\-]|$)"
)
_YEAR_RANGE = re.compile(r"(?i)(\d+)\s*(?:\+|plus)?\s*(?:-|to|–)\s*(\d+)\s*\+?\s*years")
_YEAR_MIN = re.compile(r"(?i)(\d+)\s*\+\s*years")
_YEAR_EXACT = re.compile(r"(?i)(\d+)\s+years")
_DATE = re.compile(r"^(\d{4})(?:-(\d{2}))?$")


class SkillFact(BaseModel):
    name: str
    years: float | None = None


class ExperienceFact(BaseModel):
    title: str
    start: str | None = None
    end: str | None = None
    domain: str | None = None


class ProjectFact(BaseModel):
    name: str | None = None
    domain: str | None = None


class ProfileFacts(BaseModel):
    candidate_id: str = "default-candidate"
    skills: list[SkillFact] = Field(default_factory=list)
    preferred_roles: list[str] = Field(default_factory=list)
    work_experience: list[ExperienceFact] = Field(default_factory=list)
    projects: list[ProjectFact] = Field(default_factory=list)
    preferred_locations: list[str] = Field(default_factory=list)
    work_arrangement_preferences: list[str] = Field(default_factory=list)
    excluded_arrangements: list[str] = Field(default_factory=list)
    resume_filename: str | None = None


class FactorScore(BaseModel):
    key: str
    weight: int
    status: str
    score: float | None = None
    findings: list[str] = Field(default_factory=list)


class MatchAssessment(BaseModel):
    candidate_id: str
    matching_version: str = MATCHING_VERSION
    total_score: float | None
    threshold: float
    meets_threshold: bool
    match_status: str
    factors: list[FactorScore]
    matched_skills: list[str] = Field(default_factory=list)
    missing_skills: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    weight_used: int = 0
    weight_excluded: int = 0


def score_job(
    job: dict[str, Any],
    profile: ProfileFacts | None,
    *,
    threshold: float,
    resume_text: str | None = None,
    warnings: list[str] | None = None,
) -> MatchAssessment:
    """Score one job from explicit profile and resume facts. Unknown factors are excluded."""
    notes = list(warnings or [])
    if profile is None or not _has_facts(profile):
        factors = [_unknown(key, "No confirmed profile facts are available for this category.") for key in WEIGHTS]
        notes.append("profile_missing")
        return _assemble(profile.candidate_id if profile else "default-candidate", factors, [], [], notes, threshold, "insufficient_profile")

    text = _job_text(job)
    possessed = _possessed_skills(profile, resume_text)
    required, preferred = _job_skills(text, possessed)
    skills = _score_skills(required, preferred, possessed)
    role = _score_role(str(job.get("title") or ""), profile)
    experience = _score_experience(text, profile)
    domain = _score_domain(text, profile)
    location = _score_location(job, text, profile)
    factors = [skills, role, experience, domain, location]
    status = "scored" if any(factor.score is not None for factor in factors) else "insufficient_information"
    if status != "scored":
        notes.append("no_comparable_facts")
    return _assemble(profile.candidate_id, factors, _matched(required, preferred, possessed), _missing(required, possessed), notes, threshold, status)


def _assemble(candidate_id, factors, matched, missing, notes, threshold, status) -> MatchAssessment:
    known = [factor for factor in factors if factor.score is not None]
    weight_used = sum(factor.weight for factor in known)
    weight_excluded = sum(WEIGHTS.values()) - weight_used
    total = None
    if known and weight_used:
        raw = sum((factor.score or 0) * factor.weight for factor in known) / weight_used
        total = round(min(100.0, max(0.0, raw)), 1)
    for factor in factors:
        if factor.status == "unknown":
            notes.append(f"unknown:{factor.key}")
    return MatchAssessment(
        candidate_id=candidate_id,
        total_score=total,
        threshold=threshold,
        meets_threshold=total is not None and total >= threshold,
        match_status=status,
        factors=factors,
        matched_skills=matched,
        missing_skills=missing,
        warnings=list(dict.fromkeys(notes)),
        weight_used=weight_used,
        weight_excluded=weight_excluded,
    )


def _unknown(key: str, finding: str) -> FactorScore:
    return FactorScore(key=key, weight=WEIGHTS[key], status="unknown", score=None, findings=[finding])


def _factor(key: str, score: float, findings: list[str]) -> FactorScore:
    bounded = round(min(100.0, max(0.0, score)), 1)
    if bounded >= 100:
        status = "matched"
    elif bounded <= 0:
        status = "mismatch"
    else:
        status = "partial"
    return FactorScore(key=key, weight=WEIGHTS[key], status=status, score=bounded, findings=findings)


def _has_facts(profile: ProfileFacts) -> bool:
    return any(
        [
            profile.skills,
            profile.preferred_roles,
            profile.work_experience,
            profile.projects,
            profile.preferred_locations,
            profile.work_arrangement_preferences,
            profile.excluded_arrangements,
        ]
    )


def _job_text(job: dict) -> str:
    parts = [job.get("title"), job.get("description"), job.get("location")]
    return "\n".join(part for part in parts if isinstance(part, str))


def _possessed_skills(profile: ProfileFacts, resume_text: str | None) -> dict[str, float | None]:
    possessed: dict[str, float | None] = {}
    for skill in profile.skills:
        name = skill.name.strip().lower()
        if name:
            possessed[name] = skill.years
    if not resume_text:
        return possessed
    lowered = resume_text.lower()
    for name, terms in {**_JOB_SKILLS, **{key: [key] for key in possessed}}.items():
        if any(_mentioned(lowered, term) for term in terms):
            possessed.setdefault(name, None)
    return possessed


def _job_skills(text: str, possessed: dict[str, float | None]) -> tuple[list[str], list[str]]:
    catalog = dict(_JOB_SKILLS)
    for name in possessed:
        catalog.setdefault(name, [name])
    found = [name for name, terms in catalog.items() if any(_mentioned(text.lower(), term) for term in terms)]
    heading = _REQUIRED_HEADING.search(text)
    if heading is None:
        return [], found
    required_text = heading.group(1).lower()
    required = [name for name in found if any(_mentioned(required_text, term) for term in catalog[name])]
    preferred = [name for name in found if name not in required]
    return required, preferred


def _score_skills(required: list[str], preferred: list[str], possessed: dict[str, float | None]) -> FactorScore:
    if not required and not preferred:
        return _unknown("technical_skills", "The job does not state a recognized skill.")
    if required:
        earned = sum(2 for name in required if name in possessed) + sum(1 for name in preferred if name in possessed)
        possible = 2 * len(required) + len(preferred)
    else:
        earned = sum(1 for name in preferred if name in possessed)
        possible = len(preferred)
    score = 100 * earned / possible if possible else 0
    findings = []
    if required:
        findings.append("Required skills are weighted twice as much as preferred skills.")
    return _factor("technical_skills", score, findings)


def _matched(required, preferred, possessed) -> list[str]:
    names = required + [name for name in preferred if name not in required]
    return [name for name in names if name in possessed]


def _missing(required, possessed) -> list[str]:
    return [name for name in required if name not in possessed]


def _score_role(title: str, profile: ProfileFacts) -> FactorScore:
    stated = [item for item in [*profile.preferred_roles, *[job.title for job in profile.work_experience]] if item.strip()]
    if not stated:
        return _unknown("role", "No target role or experience title is confirmed.")
    if not title.strip():
        return _unknown("role", "The job has no title to compare.")
    title_tokens = _tokens(title)
    stated_tokens = _tokens(" ".join(stated))
    if not title_tokens or not stated_tokens:
        return _unknown("role", "The role text has no comparable words.")
    if any(item.lower() in title.lower() or title.lower() in item.lower() for item in stated):
        return _factor("role", 100, [f"Title matches a stated role: {title.strip()}."])
    overlap = title_tokens & stated_tokens
    if not overlap:
        return _factor("role", 0, [f"Title '{title.strip()}' does not match the stated roles."])
    score = 100 * len(overlap) / len(title_tokens)
    return _factor("role", score, [f"Title shares words with stated roles: {', '.join(sorted(overlap))}."])


def _score_experience(text: str, profile: ProfileFacts) -> FactorScore:
    candidate_years = _candidate_years(profile)
    job_range = _job_years(text)
    if candidate_years is None:
        return _unknown("experience", "Confirmed experience dates are missing, so years were not assumed.")
    if job_range is None:
        return _unknown("experience", "The job does not state an experience range.")
    minimum, maximum = job_range
    if minimum <= candidate_years and (maximum is None or candidate_years <= maximum):
        return _factor("experience", 100, [f"Confirmed {candidate_years:g} years sits inside the stated range."])
    gap = minimum - candidate_years if candidate_years < minimum else candidate_years - (maximum or minimum)
    return _factor("experience", max(0, 100 - 25 * gap), [f"Confirmed {candidate_years:g} years is {gap:g} years outside the stated range."])


def _score_domain(text: str, profile: ProfileFacts) -> FactorScore:
    domains = []
    for item in [*profile.projects, *profile.work_experience]:
        if item.domain and item.domain.strip():
            domains.append(item.domain.strip())
    unique = list(dict.fromkeys(domains))
    if not unique:
        return _unknown("domain", "No project or experience domain is confirmed.")
    if not text.strip():
        return _unknown("domain", "The job has no text to compare with confirmed domains.")
    matched = [domain for domain in unique if domain.casefold() in text.casefold()]
    if not matched:
        return _factor("domain", 0, ["None of the confirmed domains appear in the job text."])
    return _factor("domain", 100 * len(matched) / len(unique), [f"Confirmed domains found in the job: {', '.join(matched)}."])


def _score_location(job: dict, text: str, profile: ProfileFacts) -> FactorScore:
    preferences = {_arrangement(item) for item in profile.work_arrangement_preferences}
    preferences.discard("")
    excluded = {_arrangement(item) for item in profile.excluded_arrangements}
    excluded.discard("")
    places = [place.strip() for place in profile.preferred_locations if place.strip()]
    if not preferences and not excluded and not places:
        return _unknown("location", "No location or work-arrangement preference is confirmed.")
    arrangement = _job_arrangement(job, text)
    place_match = _place_match(job, places)
    if arrangement is None and place_match is None:
        return _unknown("location", "The job does not state a location or work arrangement.")
    if arrangement and arrangement in excluded:
        return _factor("location", 0, [f"The job states {arrangement}, which is excluded."])
    if arrangement and preferences and arrangement in preferences:
        return _factor("location", 100, [f"The job states {arrangement}, which is a confirmed preference."])
    if arrangement and preferences and arrangement not in preferences:
        return _factor("location", 0, [f"The job states {arrangement}, which is not a confirmed preference."])
    if place_match is True:
        return _factor("location", 100, ["The job location matches a confirmed place."])
    if place_match is False:
        return _factor("location", 0, ["The job location does not match a confirmed place."])
    return _unknown("location", "Location could not be compared without inventing a preference.")


def _candidate_years(profile: ProfileFacts) -> float | None:
    spans = []
    for item in profile.work_experience:
        start = _date_index(item.start)
        end = _date_index(item.end) if item.end else _date_index("2026-10")
        if start is None or end is None or end < start:
            continue
        spans.append((end - start) / 12)
    if not spans:
        return None
    return round(sum(spans), 2)


def _job_years(text: str) -> tuple[float, float | None] | None:
    ranged = _YEAR_RANGE.search(text)
    if ranged:
        low, high = float(ranged.group(1)), float(ranged.group(2))
        return (min(low, high), max(low, high))
    minimum = _YEAR_MIN.search(text)
    if minimum:
        return (float(minimum.group(1)), None)
    exact = _YEAR_EXACT.search(text)
    if exact:
        value = float(exact.group(1))
        return (value, value)
    return None


def _date_index(value: str | None) -> int | None:
    if not value:
        return None
    match = _DATE.match(value.strip())
    if match is None:
        return None
    month = int(match.group(2) or "1")
    if month < 1 or month > 12:
        return None
    return int(match.group(1)) * 12 + month


def _job_arrangement(job: dict, text: str) -> str | None:
    stated = _arrangement(str(job.get("remote_type") or ""))
    if stated:
        return stated
    lowered = text.lower()
    if "hybrid" in lowered:
        return "hybrid"
    if re.search(r"(?<![a-z])remote(?![a-z])|work from home", lowered):
        return "remote"
    if re.search(r"on-?site|in[- ]office", lowered):
        return "onsite"
    return None


def _place_match(job: dict, places: list[str]) -> bool | None:
    if not places:
        return None
    location = job.get("location")
    if not isinstance(location, str) or not location.strip():
        return None
    lowered = location.casefold()
    return any(place.casefold() in lowered for place in places)


def _arrangement(value: str) -> str:
    cleaned = value.strip().lower().replace("-", "").replace(" ", "")
    if cleaned in {"remote", "wfh"}:
        return "remote"
    if cleaned == "hybrid":
        return "hybrid"
    if cleaned in {"onsite", "on-site", "office"}:
        return "onsite"
    return ""


def _tokens(value: str) -> set[str]:
    return {token for token in _TOKEN_RE.findall(value.lower()) if len(token) > 2 and token not in _STOP}


def _mentioned(text: str, term: str) -> bool:
    pattern = r"(?<![a-z0-9])" + re.escape(term.lower()) + r"(?![a-z0-9])"
    return re.search(pattern, text.lower()) is not None
