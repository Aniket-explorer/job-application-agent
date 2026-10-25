from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

@dataclass
class ConnectorCapabilities:
    source: str
    enabled: bool = False
    configured: bool = False
    discovery_supported: bool = False
    application_supported: bool = False
    status: str = "not_configured"
    note: str = "No provider integration is configured."

class JobSourceConnector(ABC):
    """Provider adapter contract. Implement only after verifying provider-approved access."""
    source: str

    @abstractmethod
    def capabilities(self) -> ConnectorCapabilities:
        raise NotImplementedError

    async def discover_jobs(self) -> list[dict[str, Any]]:
        raise NotImplementedError(f"Discovery is not implemented for {self.source}")

    async def get_job_details(self, source_job_id: str) -> dict[str, Any] | None:
        raise NotImplementedError(f"Job detail retrieval is not implemented for {self.source}")

    async def apply(self, job: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
        raise PermissionError(f"Live application is not enabled for {self.source}")
