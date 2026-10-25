from datetime import datetime, timezone
from typing import Literal, Optional
from pydantic import BaseModel, Field, HttpUrl, ConfigDict

def utcnow() -> datetime:
    return datetime.now(timezone.utc)

SourceName = Literal["manual", "linkedin", "naukri", "wellfound", "career_page", "gmail"]

class JobImport(BaseModel):
    source: SourceName = "manual"
    source_job_id: str
    company: str
    title: str
    location: Optional[str] = None
    description: str
    canonical_url: HttpUrl
    recruiter_email: Optional[str] = None

class JobOut(BaseModel):
    id: str
    source: str
    source_job_id: str
    company: str
    title: str
    location: Optional[str] = None
    description: str
    canonical_url: str
    match_score: Optional[float] = None
    status: str = "active"
    created_at: datetime

class ApplicationCreate(BaseModel):
    job_id: str
    candidate_id: str = "default-candidate"

class ApplicationOut(BaseModel):
    id: str
    job_id: str
    candidate_id: str
    channel: str
    status: str
    match_score: float
    dry_run: bool = True
    created_at: datetime
    error: Optional[str] = None

class AutomationSettings(BaseModel):
    dry_run: bool = True
    minimum_match_score: int = Field(default=50, ge=0, le=100)
    search_interval_minutes: int = Field(default=60, ge=60, le=1440)
    followup_enabled: bool = True

class ConnectorStatus(BaseModel):
    source: str
    enabled: bool
    configured: bool
    discovery_supported: bool
    application_supported: bool
    status: str
    note: str

class MatchResult(BaseModel):
    score: float
    factors: dict[str, float]
    reasons: list[str] = Field(default_factory=list)
