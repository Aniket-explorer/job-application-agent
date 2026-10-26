from typing import Any

from app.connectors.base import ConnectorCapabilities, JobSourceConnector
from app.connectors.career_page.greenhouse import ConnectorUnavailable, parse_greenhouse_boards
from app.core.config import settings
from app.services.discovery import sync_greenhouse_boards


class CareerPageConnector(JobSourceConnector):
    """Greenhouse job-list adapter. Submission stays disabled."""

    source = "career_page"

    def capabilities(self) -> ConnectorCapabilities:
        boards = parse_greenhouse_boards(settings.greenhouse_boards)
        configured = bool(settings.enable_career_page_connector and boards)
        if configured:
            note = "Greenhouse job-list sync is configured. Application submission is not implemented."
            status = "configured"
        else:
            note = (
                "Greenhouse Job Board list API is implemented and disabled. "
                "Set ENABLE_CAREER_PAGE_CONNECTOR and GREENHOUSE_BOARDS locally. "
                "No application endpoint is called."
            )
            status = "not_configured"
        return ConnectorCapabilities(
            source=self.source,
            enabled=bool(settings.enable_career_page_connector),
            configured=configured,
            discovery_supported=configured,
            application_supported=False,
            status=status,
            note=note,
        )

    async def discover_jobs(self) -> list[dict[str, Any]]:
        if not self.capabilities().discovery_supported:
            raise ConnectorUnavailable("career_page discovery is not configured")
        result = await sync_greenhouse_boards(allow_network=True)
        return [{"created": result.created, "updated": result.updated, "status": result.status}]

    async def apply(self, job: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
        raise PermissionError("Live application is not enabled for career_page")
