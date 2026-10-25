from app.matching import calculate_match_score

def test_matching_is_deterministic_and_bounded():
    a = calculate_match_score("Backend engineer using Python FastAPI MongoDB Redis REST API")
    b = calculate_match_score("Backend engineer using Python FastAPI MongoDB Redis REST API")
    assert a == b
    assert 0 <= a["score"] <= 100
    assert "skills" in a["factors"]

def test_irrelevant_description_has_lower_score():
    relevant = calculate_match_score("Backend Software Engineer Python FastAPI MongoDB Redis REST API")
    irrelevant = calculate_match_score("Seasonal gardening and landscape design")
    assert relevant["score"] > irrelevant["score"]
