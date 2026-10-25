from app.models import AutomationSettings

def test_settings_defaults_to_dry_run():
    settings = AutomationSettings()
    assert settings.dry_run is True
    assert settings.minimum_match_score == 50
    assert settings.search_interval_minutes == 60
