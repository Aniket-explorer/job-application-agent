from app.connectors.stubs import CONNECTORS
from app.core.config import settings

def test_all_connectors_are_explicitly_unconfigured(monkeypatch):
    monkeypatch.setattr(settings, "enable_career_page_connector", False)
    monkeypatch.setattr(settings, "greenhouse_boards", "")
    assert {"linkedin", "naukri", "wellfound", "career_page", "gmail"}.issubset(CONNECTORS)
    for connector in CONNECTORS.values():
        cap = connector.capabilities()
        assert cap.configured is False
        assert cap.application_supported is False
        assert cap.discovery_supported is False
