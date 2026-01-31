from typing import List

from pydantic import BaseModel


class ClipOut(BaseModel):
    start: float
    end: float
    score: float
    energy_score: float
    speech_density_score: float
    keyword_score: float = 0.0
    reason: str


class ProcessResponse(BaseModel):
    status: str
    clips: List[ClipOut]

