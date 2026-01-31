from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, UploadFile

from backend.app.schemas.clips import ClipOut
from backend.app.schemas.jobs import JobCreatedResponse, JobDetail, JobFromLinkRequest
from backend.domain.models import JobStatus
from backend.domain.services.job_service import create_job, get_job, run_job, run_job_from_link


router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.post("", response_model=JobCreatedResponse, status_code=202)
async def create_processing_job(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
):
    """
    Create a new processing job from an uploaded video file.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file uploaded")

    job = create_job()
    suffix = Path(file.filename).suffix or ".mp4"
    jobs_dir = Path("jobs")
    jobs_dir.mkdir(parents=True, exist_ok=True)
    video_path = jobs_dir / f"{job.id}{suffix}"

    with video_path.open("wb") as f:
        content = await file.read()
        if not content:
            raise HTTPException(status_code=400, detail="Uploaded file is empty")
        f.write(content)

    background_tasks.add_task(run_job, job.id, video_path)

    return JobCreatedResponse(
        id=job.id,
        status=job.status,
        clips=[],
        error_message=None,
    )


@router.post("/from-link", response_model=JobCreatedResponse, status_code=202)
async def create_job_from_link(
    background_tasks: BackgroundTasks,
    body: JobFromLinkRequest,
):
    """
    Create a new processing job from a YouTube URL or Dropbox link.
    """
    url = (body.url or "").strip()
    if not url:
        raise HTTPException(status_code=400, detail="URL is required")

    source = (body.source or "").lower()
    if source not in ("youtube", "dropbox"):
        raise HTTPException(
            status_code=400,
            detail="source must be 'youtube' or 'dropbox'",
        )

    if source == "youtube" and "youtube.com" not in url and "youtu.be" not in url:
        raise HTTPException(status_code=400, detail="Invalid YouTube URL")
    if source == "dropbox" and "dropbox.com" not in url:
        raise HTTPException(status_code=400, detail="Invalid Dropbox URL")

    job = create_job()
    background_tasks.add_task(run_job_from_link, job.id, url, source)

    return JobCreatedResponse(
        id=job.id,
        status=job.status,
        clips=[],
        error_message=None,
    )


@router.get("/{job_id}", response_model=JobDetail)
async def get_job_status(job_id: str):
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    clips = [
        ClipOut(
            start=c.start,
            end=c.end,
            score=c.score,
            energy_score=c.energy_score,
            speech_density_score=c.speech_density_score,
            keyword_score=c.keyword_score,
            reason=c.reason,
        )
        for c in job.clips
    ]

    return JobDetail(
        id=job.id,
        status=job.status,
        clips=clips,
        error_message=job.error_message,
    )


@router.get("/{job_id}/clips", response_model=list[ClipOut])
async def get_job_clips(job_id: str):
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.status != JobStatus.COMPLETED:
        raise HTTPException(
            status_code=409,
            detail=f"Job not completed yet (status={job.status})",
        )

    return [
        ClipOut(
            start=c.start,
            end=c.end,
            score=c.score,
            energy_score=c.energy_score,
            speech_density_score=c.speech_density_score,
            keyword_score=c.keyword_score,
            reason=c.reason,
        )
        for c in job.clips
    ]
