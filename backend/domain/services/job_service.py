import uuid
from pathlib import Path
from typing import List, Literal

from backend.domain.models import Job, JobStatus, Clip
from backend.domain.services.clip_ranker import process_audio_file, process_video_file
from backend.infrastructure.persistence.in_memory_repo import job_repository
from backend.infrastructure.downloaders import download_youtube, download_dropbox


def create_job() -> Job:
    """
    Create a new job in PROCESSING state.
    """
    job_id = str(uuid.uuid4())
    job = Job(id=job_id, status=JobStatus.PROCESSING)
    job_repository.save(job)
    return job


def run_job(job_id: str, video_path: Path) -> None:
    """
    Background processing for a job:
    - Run highlight discovery
    - Update job status and attach clips or error message
    """
    job = job_repository.get(job_id)
    if not job:
        return

    try:
        clips: List[Clip] = process_video_file(video_path)
        job.clips = clips
        job.status = JobStatus.COMPLETED
    except Exception as exc:  # noqa: BLE001 - top-level guard
        job.status = JobStatus.FAILED
        job.error_message = str(exc)
    finally:
        job_repository.save(job)


def get_job(job_id: str) -> Job | None:
    return job_repository.get(job_id)


def run_job_from_link(
    job_id: str,
    url: str,
    source: Literal["youtube", "dropbox"],
) -> None:
    """
    Download from URL (YouTube or Dropbox) then run highlight discovery.
    """
    job = job_repository.get(job_id)
    if not job:
        return

    jobs_dir = Path("jobs")
    jobs_dir.mkdir(parents=True, exist_ok=True)

    try:
        if source == "youtube":
            audio_path = jobs_dir / f"{job_id}.wav"
            download_youtube(url, audio_path)
            clips: List[Clip] = process_audio_file(audio_path)
        else:  # dropbox
            video_path = jobs_dir / f"{job_id}_dropbox.mp4"
            download_dropbox(url, video_path)
            clips = process_video_file(video_path)

        job.clips = clips
        job.status = JobStatus.COMPLETED
    except Exception as exc:
        job.status = JobStatus.FAILED
        job.error_message = str(exc)
    finally:
        job_repository.save(job)

