from app.connectors.base import JobSourceConnector, ConnectorCapabilities
from app.connectors.career_page.connector import CareerPageConnector

class UnconfiguredConnector(JobSourceConnector):
    def __init__(self, source: str, note: str):
        self.source = source
        self.note = note
    def capabilities(self) -> ConnectorCapabilities:
        return ConnectorCapabilities(source=self.source, note=self.note)

CONNECTORS = {
    "linkedin": UnconfiguredConnector("linkedin", "No API access assumed. Verify current LinkedIn terms and permitted integration options before implementation."),
    "naukri": UnconfiguredConnector("naukri", "No API access assumed. Configure only an authorized integration or permitted import path."),
    "wellfound": UnconfiguredConnector("wellfound", "No API access assumed. Configure only after verifying current access and application rules."),
    "career_page": CareerPageConnector(),
    "gmail": UnconfiguredConnector("gmail", "Gmail OAuth/API integration is not implemented. Configure Google Cloud OAuth and scopes after reviewing Gmail API requirements."),
}
