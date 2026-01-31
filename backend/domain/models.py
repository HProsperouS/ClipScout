from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


@dataclass
class Clip:
    start: float
    end: float
    score: float
    energy_score: float
    speech_density_score: float
    reason: str
    keyword_score: float = 0.0  # 0–1, from Whisper keyword relevance


class JobStatus(str, Enum):
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class Job:
    id: str
    status: JobStatus
    clips: List[Clip] = field(default_factory=list)
    error_message: Optional[str] = None

