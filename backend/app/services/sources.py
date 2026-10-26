from app.connectors.stubs import CONNECTORS
from app.core.errors import UnknownSourceError


def list_sources() -> list[dict]:
    return [_status(connector) for connector in CONNECTORS.values()]


def get_source(source_name: str) -> dict:
    connector = CONNECTORS.get(source_name)
    if connector is None:
        raise UnknownSourceError(source_name)
    return _status(connector)


def _status(connector) -> dict:
    capabilities = connector.capabilities()
    return {
        "source": capabilities.source,
        "enabled": capabilities.enabled,
        "configured": capabilities.configured,
        "discovery_supported": capabilities.discovery_supported,
        "application_supported": capabilities.application_supported,
        "status": capabilities.status,
        "note": capabilities.note,
    }
