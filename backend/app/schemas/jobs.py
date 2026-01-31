from typing import List, Literal, Optional

from pydantic import BaseModel

from backend.app.schemas.clips import ClipOut
from backend.domain.models import JobStatus


class JobSummary(BaseModel):
    id: str
    status: JobStatus


class JobDetail(BaseModel):
    id: str
    status: JobStatus
    clips: List[ClipOut] = []
    error_message: Optional[str] = None


class JobCreatedResponse(JobDetail):
    pass


class JobFromLinkRequest(BaseModel):
    url: str
    source: Literal["youtube", "dropbox"]

