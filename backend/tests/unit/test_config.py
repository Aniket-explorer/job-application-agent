import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.repositories.settings import default_settings


def test_rejects_a_non_mongodb_url():
    with pytest.raises(ValidationError):
        Settings(mongodb_url="http://localhost:27017")


def test_rejects_a_match_score_above_100():
    with pytest.raises(ValidationError):
        Settings(min_match_score=150)


def test_rejects_an_unknown_log_level():
    with pytest.raises(ValidationError):
        Settings(log_level="verbose")


def test_seed_keeps_dry_run_even_if_the_environment_disables_it():
    config = Settings(
        dry_run=False,
        automation_enabled=True,
        min_match_score=40,
        discovery_interval_minutes=120,
        global_pause=False,
    )
    seeded = default_settings(config)
    assert seeded.dry_run is True
    assert seeded.automation_enabled is False
    assert seeded.minimum_match_score == 40
    assert seeded.search_interval_minutes == 120
    assert seeded.global_pause is False
