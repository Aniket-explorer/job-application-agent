from app.scoring.engine import WEIGHTS, ProfileFacts, score_job

THRESHOLD = 50


def _profile(**kwargs) -> ProfileFacts:
    return ProfileFacts(**kwargs)


def test_weights_and_a_full_match_score_100():
    assert WEIGHTS == {"technical_skills": 30, "role": 25, "experience": 20, "domain": 15, "location": 10}
    assert sum(WEIGHTS.values()) == 100
    result = score_job(
        {
            "title": "Backend Engineer",
            "description": "Requirements: Python. 3-5 years. Remote payments platform.",
            "location": "Bengaluru",
        },
        _profile(
            skills=[{"name": "Python"}],
            preferred_roles=["Backend Engineer"],
            work_experience=[{"title": "Backend Engineer", "start": "2020-01", "end": "2024-01", "domain": "payments"}],
            work_arrangement_preferences=["remote"],
            preferred_locations=["Bengaluru"],
        ),
        threshold=THRESHOLD,
    )
    assert result.total_score == 100
    assert result.meets_threshold is True
    assert result.match_status == "scored"
    assert [factor.score for factor in result.factors] == [100, 100, 100, 100, 100]
    again = score_job(
        {
            "title": "Backend Engineer",
            "description": "Requirements: Python. 3-5 years. Remote payments platform.",
            "location": "Bengaluru",
        },
        _profile(
            skills=[{"name": "Python"}],
            preferred_roles=["Backend Engineer"],
            work_experience=[{"title": "Backend Engineer", "start": "2020-01", "end": "2024-01", "domain": "payments"}],
            work_arrangement_preferences=["remote"],
            preferred_locations=["Bengaluru"],
        ),
        threshold=THRESHOLD,
    )
    assert result == again


def test_a_confirmed_role_mismatch_uses_its_25_percent_weight():
    result = score_job(
        {
            "title": "Accountant",
            "description": "Requirements: Python. 3-5 years. Remote payments platform.",
            "location": "Bengaluru",
        },
        _profile(
            skills=[{"name": "Python"}],
            preferred_roles=["Backend Engineer"],
            work_experience=[{"title": "Backend Engineer", "start": "2020-01", "end": "2024-01", "domain": "payments"}],
            work_arrangement_preferences=["remote"],
            preferred_locations=["Bengaluru"],
        ),
        threshold=THRESHOLD,
    )
    role = next(factor for factor in result.factors if factor.key == "role")
    assert role.status == "mismatch"
    assert role.score == 0
    assert result.total_score == 75
    assert result.meets_threshold is True


def test_unknown_skills_are_excluded_instead_of_scoring_50():
    result = score_job(
        {"title": "Writer", "description": "Write release notes for the team."},
        _profile(skills=[{"name": "Python"}]),
        threshold=THRESHOLD,
    )
    skills = next(factor for factor in result.factors if factor.key == "technical_skills")
    assert skills.status == "unknown"
    assert skills.score is None
    assert 50 not in [factor.score for factor in result.factors]
    assert "unknown:technical_skills" in result.warnings
    assert result.weight_excluded > 0


def test_missing_required_skill_is_a_mismatch_and_matched_skill_is_listed():
    result = score_job(
        {"title": "Backend Engineer", "description": "Requirements: Python and Kubernetes."},
        _profile(skills=[{"name": "Python"}], preferred_roles=["Backend Engineer"]),
        threshold=THRESHOLD,
    )
    assert result.matched_skills == ["python"]
    assert result.missing_skills == ["kubernetes"]
    skills = next(factor for factor in result.factors if factor.key == "technical_skills")
    assert skills.status == "partial"
    assert skills.score == 50


def test_resume_text_confirms_a_skill_that_is_not_in_the_profile():
    result = score_job(
        {"title": "Backend Engineer", "description": "Requirements: Python."},
        _profile(preferred_roles=["Backend Engineer"]),
        threshold=THRESHOLD,
        resume_text="Built services with Python.",
    )
    assert result.matched_skills == ["python"]
    assert result.missing_skills == []


def test_experience_boundaries_and_missing_years():
    profile = _profile(work_experience=[{"title": "Engineer", "start": "2020-01", "end": "2024-01"}])
    inside = score_job({"title": "Engineer", "description": "3-5 years of work"}, profile, threshold=THRESHOLD)
    outside = score_job({"title": "Engineer", "description": "8+ years of work"}, profile, threshold=THRESHOLD)
    near = score_job({"title": "Engineer", "description": "6-7 years of work"}, profile, threshold=THRESHOLD)
    unknown = score_job({"title": "Engineer", "description": "No tenure stated"}, profile, threshold=THRESHOLD)
    assert _factor(inside, "experience").score == 100
    assert _factor(outside, "experience").score == 0
    assert _factor(outside, "experience").status == "mismatch"
    assert _factor(near, "experience").score == 50
    assert _factor(unknown, "experience").status == "unknown"
    assert _factor(unknown, "experience").score is None


def test_domain_and_location_distinguish_unknown_from_mismatch():
    profile = _profile(
        projects=[{"name": "Ledger", "domain": "payments"}],
        work_arrangement_preferences=["remote"],
        preferred_locations=["Bengaluru"],
    )
    matched = score_job(
        {"title": "Engineer", "description": "Remote payments platform", "location": "Bengaluru"},
        profile,
        threshold=THRESHOLD,
    )
    mismatched = score_job(
        {"title": "Engineer", "description": "Onsite healthcare clinic", "location": "London"},
        profile,
        threshold=THRESHOLD,
    )
    unknown = score_job({"title": "Engineer", "description": "Join our team."}, _profile(), threshold=THRESHOLD)
    assert _factor(matched, "domain").score == 100
    assert _factor(matched, "location").score == 100
    assert _factor(mismatched, "domain").status == "mismatch"
    assert _factor(mismatched, "domain").score == 0
    assert _factor(mismatched, "location").status == "mismatch"
    assert _factor(unknown, "domain").status == "unknown"
    assert _factor(unknown, "location").status == "unknown"
    vague = score_job({"title": "Engineer", "description": "Join our team."}, profile, threshold=THRESHOLD)
    assert _factor(vague, "domain").status == "mismatch"
    assert _factor(vague, "location").status == "unknown"


def test_missing_profile_has_no_score_and_does_not_meet_the_threshold():
    result = score_job({"title": "Backend Engineer", "description": "Python"}, None, threshold=THRESHOLD)
    assert result.total_score is None
    assert result.meets_threshold is False
    assert result.match_status == "insufficient_profile"
    assert result.threshold == 50
    below = score_job(
        {"title": "Accountant", "description": "Requirements: Kubernetes."},
        _profile(skills=[{"name": "Python"}], preferred_roles=["Backend Engineer"]),
        threshold=50.1,
    )
    assert below.total_score is not None
    assert below.total_score < 50.1
    assert below.meets_threshold is False


def _factor(result, key):
    return next(factor for factor in result.factors if factor.key == key)
