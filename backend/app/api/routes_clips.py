import tempfile
from pathlib import Path
from typing import List

from fastapi import APIRouter, File, HTTPException, UploadFile

from backend.app.schemas.clips import ClipOut, ProcessResponse
from backend.domain.models import Clip
from backend.domain.services.clip_ranker import process_video_file


router = APIRouter(tags=["clips"])


@router.post("/process", response_model=ProcessResponse)
async def process_video(file: UploadFile = File(...)):
    """
    Accepts an uploaded video file, runs highlight discovery and
    returns the Top 3 clips with explanations.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file uploaded")

    suffix = Path(file.filename).suffix or ".mp4"

    with tempfile.TemporaryDirectory() as tmpdir:
        video_path = Path(tmpdir) / f"input{suffix}"

        # Save uploaded video
        with video_path.open("wb") as f:
            content = await file.read()
            if not content:
                raise HTTPException(status_code=400, detail="Uploaded file is empty")
            f.write(content)

        try:
            clips: List[Clip] = process_video_file(video_path)
        except RuntimeError as e:
            raise HTTPException(status_code=500, detail=str(e))

    clip_out = [
        ClipOut(
            start=c.start,
            end=c.end,
            score=c.score,
            energy_score=c.energy_score,
            speech_density_score=c.speech_density_score,
            keyword_score=c.keyword_score,
            reason=c.reason,
        )
        for c in clips
    ]

    return ProcessResponse(status="completed", clips=clip_out)

