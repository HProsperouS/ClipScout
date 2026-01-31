## ClipScout

Automatic highlight discovery for long-form videos.

This project is an internship exercise implementation for Videotto. The goal is to take a long video, automatically identify the top 3 highlight clips, and expose them through an AWS‑hosted Python backend and a React (Vite + shadcn/ui + Tailwind) frontend.

---

## High‑level architecture

- **Frontend**
  - React + TypeScript, Vite, Tailwind, shadcn/ui.
  - Single‑page app for:
    - Uploading a local video file, or pasting a YouTube / Dropbox link.
    - Creating an asynchronous processing job.
    - Polling job status.
    - Displaying the top 3 clips with explanations (energy, speech density, keyword relevance when available).

- **Backend**
  - Python + FastAPI.
  - RESTful, job‑oriented API:
    - `POST /api/jobs` – create a processing job from an uploaded video file.
    - `POST /api/jobs/from-link` – create a job from a YouTube or Dropbox link.
    - `GET /api/jobs/{job_id}` – fetch job status and (when ready) clip results.
    - `GET /api/jobs/{job_id}/clips` – fetch only the clips (409 if not completed).
  - Deployment: single Docker container on **AWS EC2**; see [Deploying to AWS](#deploying-to-aws-ec2) below.

- **Domain design**
  - `Job` – represents a single processing run (`id`, `status`, `clips`, `error_message`).
  - `Clip` – candidate highlight (`start`, `end`, `score`, `energy_score`, `speech_density_score`, `keyword_score`, `reason`).
  - Layers:
    - `backend/app` – FastAPI wiring, HTTP schemas and routes.
    - `backend/domain` – business logic (clip ranking, job orchestration).
    - `backend/infrastructure` – **ffmpeg** (extracts mono 16 kHz WAV from video for energy/speech analysis), **Whisper ASR** (transcribes audio to timestamped text and extracts keywords for clip scoring), YouTube/Dropbox downloaders, in‑memory job store (job state in RAM; uploaded video files are written to disk under `jobs/`).

---

## How clip ranking works (Top 3 Clips)

There is intentionally no strict definition of “best” clips in the exercise. The strategy here is simple, explainable, and robust within the 5‑hour constraint:

### Core intuition

> Moments where people talk a lot and the audio energy changes more are usually where the content is important, emotional, or has a narrative peak.

Each candidate clip is scored using up to three signals:

1. **Audio energy** – how loud / dynamic the segment is (RMS, normalized).
2. **Speech activity density** – how much of the segment contains active speech or strong audio (simple energy-based VAD proxy).
3. **Keyword relevance** – We also transcribe the audio, extract top keywords by frequency (excluding stopwords), and score each clip by how many of those keywords appear in speech within that clip’s time range. If Whisper is missing or fails, we use only energy and speech density (keyword_score = 0).

All three signals are in [0, 1]. The combined score is:

```
score = w_energy × energy_score + w_speech × speech_density_score + w_keyword × keyword_score
```

- **When Whisper is used:** `w_energy = 0.35`, `w_speech = 0.35`, `w_keyword = 0.3` (weights are normalized).
- **When Whisper is missing or fails:** `keyword_score = 0` and we use only energy and speech (`w_energy = 0.35`, `w_speech = 0.35`, effectively 50/50).

### Detailed pipeline

1. **Extract audio from video** (`backend/infrastructure/ffmpeg_adapter.py`)
   - ffmpeg extracts **mono 16 kHz WAV** from the input video (`extract_audio()`). This WAV is used for energy/speech analysis and (when used) Whisper.

2. **Frame the audio** (`clip_ranker`: `_frame_signal`, librosa)
   - Load the WAV at 16 kHz and split into **non-overlapping 1-second frames** (`frame_duration_seconds=1.0`). Each frame is one second of audio for feature computation.

3. **Compute per-frame energy** (`_compute_window_energy`)
   - For each frame, compute **RMS energy**, then normalize so the maximum over all frames is 1.0 and values lie in [0, 1].

4. **Approximate speech activity** (`_compute_speech_activity`)
   - Simple VAD proxy from energy: threshold = 0.3; map energy to [0, 1] with `(energy - 0.3) / (1 - 0.3)` and clip. Yields a **speech activity score per frame** without a separate ASR model.

5. **Build candidate clips** (`_sliding_window_indices`)
   - **Clip length 15 s**, **step 5 s**. Slide the window over frames to get overlapping candidate clips. For each candidate: `energy_score` = mean of frame energies in the window; `speech_density_score` = mean of speech activity in the window.

6. **Whisper ASR and keyword scoring** (`whisper_adapter`, `_keyword_score_for_clip`)
   - When Whisper is used: transcribe to timestamped segments (default model `tiny`, env `WHISPER_MODEL`), extract **top 20 keywords** by frequency (excluding stopwords), then for each candidate clip get the text in that time range and score by keyword hits (normalized). If Whisper is missing or fails, `keyword_score = 0`.

7. **Score and select top 3** (`_extract_top_clips_from_audio`)
   - For each candidate, compute the weighted score (energy + speech + keyword). Sort by score descending and return the **top 3** clips (`top_k=3`).

8. **Human-readable explanations** (`_build_reason`)
   - For each selected clip, build a short explanation: time range (HH:MM:SS), energy/speech (and keyword if used) percentages, and a prose reason. Returned to the frontend so the ranking is transparent.

### Why this approach

- **Pros**
  - Works on any video; no subtitles required. Optional Whisper adds semantic keyword relevance.
  - Explainable: scores come from audio statistics and (when used) transcript keywords.
  - Robust fallback: if Whisper is missing or fails, ranking uses energy + speech only.

- **Limitations**
  - Fixed clip length and simple thresholds; not adaptive to different video types.
  - Keyword set is per-video (top frequency words); no cross-video topic model.

---

## RESTful API design (status & progress)

The backend models processing as a **Job resource** (`backend/app/api/routes_jobs.py`; schemas in `backend/app/schemas/jobs.py` and `clips.py`). Progress is tracked explicitly via job status.

- **Create job (file upload)** — `POST /api/jobs`
  - Request: `multipart/form-data` with a `file` field (video file). Upload is streamed to disk in chunks; no hard size limit by default (set `MAX_UPLOAD_MB` in env to cap).
  - Success: `202 Accepted` with `{ "id", "status": "processing", "clips": [], "error_message": null }`.
  - Errors: `400` (no file / empty file), `413` (file too large when `MAX_UPLOAD_MB` set), `507` (disk full), `500` (upload/server error); response body includes a `detail` message.

- **Create job (YouTube or Dropbox link)** — `POST /api/jobs/from-link`
  - Request: JSON `{ "url": "<link>", "source": "youtube" | "dropbox" }`. YouTube uses yt-dlp; Dropbox uses HTTP with `?dl=1`. On EC2, set `YT_COOKIES_FILE` if YouTube returns "sign in to confirm you're not a bot".
  - Success: `202 Accepted` (same shape as above). Errors: `400` (missing url, invalid source, invalid URL).

- **Get job status and results** — `GET /api/jobs/{job_id}`
  - Response: `{ "id", "status": "processing" | "completed" | "failed", "clips": [...], "error_message": null | string }`. Each clip has `start`, `end`, `score`, `energy_score`, `speech_density_score`, `keyword_score`, `reason`. Errors: `404` if job not found.

- **Get clips only** — `GET /api/jobs/{job_id}/clips`
  - Returns the clip array when `status="completed"`. Errors: `404` (job not found), `409` (job not completed yet).

**Frontend flow:** Send one upload request; poll `GET /api/jobs/{job_id}` every few seconds; stop when `status` is `"completed"` or `"failed"` and display clips or `error_message`.

---

## Frontend behaviour (React + shadcn/ui)

The frontend is a small React SPA built with Vite and shadcn/ui:

- **Upload / link section**
  - Lets the user pick a local video file (sends `POST /api/jobs` with `FormData`) or paste a YouTube / Dropbox link (sends `POST /api/jobs/from-link` with JSON).
  - Shows basic file metadata when a file is selected.

- **Status section**
  - Shows the current job status: `Idle`, `Processing…`, `Completed`, `Failed`, and the job ID.

- **Results section**
  - Once the job is completed, displays the top 3 clips:
    - Start / end timestamps, final score, energy and speech density (and keyword relevance when available).
    - The generated explanation string.

The UI is intentionally simple and clean, using shadcn/ui’s primitives (e.g. `Button`, cards, typography) to give it a professional feel without over‑engineering the visual layer.

---

## Running the project locally

### Prerequisites

- Python 3.11+ (virtualenv recommended).
- Node.js + npm.
- `ffmpeg` installed and available on the system `PATH`.

### Backend

From the project root:

```bash
python -m venv .venv
source .venv/bin/activate  # on Windows: .venv\Scripts\activate
pip install -r requirements.txt

python -m uvicorn backend.main:app --reload --port 8000
```

Verify it is running:

- `http://127.0.0.1:8000/health` → `{"status": "ok"}`
- `http://127.0.0.1:8000/docs` → interactive Swagger UI.

### Frontend

From the `frontend` directory:

```bash
npm install
npm run dev
```

Then open **`http://localhost:5173`** in the browser (not `http://localhost:8000`). The frontend talks to the API at `http://localhost:8000` by default when in dev mode (`VITE_API_BASE` can override this).

### Running with Docker

From the project root, build and run a single container (frontend built inside the image, served by FastAPI):

```bash
docker build -t clipscout .
docker run -p 8000:8000 clipscout
```

Then open `http://localhost:8000` in the browser. The API is at `/api/jobs`, `/health`, etc.; the SPA is served at `/`. Uploaded files are stored in the container’s `jobs/` directory (use a volume if you need persistence: e.g. `-v $(pwd)/jobs:/app/jobs`).

---

## Deploying to AWS (EC2)

A simple production setup uses **one EC2 instance** (no Application Load Balancer), suitable for **Free Tier** (e.g. t2.micro / t3.micro: 1 vCPU, 1 GB RAM, 750 hours/month for 12 months).

### Architecture

- **EC2** – single instance; install Docker and run one container that serves the FastAPI app plus the built React static files.
- **Storage** – uploaded videos and extracted audio are stored under a directory on the instance (e.g. `jobs/`). For persistence across restarts, use the instance root volume or attach an EBS volume.

### Terraform

Using Terraform (infrastructure as code) keeps EC2 and security group definitions in versioned config files: you can **reproduce** the same environment anywhere, **review changes** with `terraform plan` before applying, **tear down** and recreate resources in one command, and **share** the setup with the team. No manual clicking in the AWS console; one `terraform apply` provisions the instance and opens the right ports.

Use the `terraform/` directory to provision EC2 + security group. See **terraform/README.md** for:

- `terraform init` → `terraform plan` → `terraform apply`
- Set `key_name` in `terraform.tfvars` (EC2 key pair for SSH)
- After apply: SSH to the instance, build/run the Docker image, then open `http://54.169.218.27:8000`

---

## Trade‑offs and possible improvements

With more time, the following improvements would be high‑value:

- **Richer clip quality model**
  - We already use Whisper and keyword scoring. For example: add **sentiment** so that anger or other strong emotions push a clip up or down; or when someone uploads a **YouTube link**, use the video **title** (and maybe description) and score clips by how well their keywords match the title—so highlights stay on-topic instead of just “loud + speechy”.

- **Better VAD(Voice Activity Detection)**
  - Replace the simple energy‑threshold proxy with a real VAD model.
  - Optionally identify speaker turns and prioritize segments with more interaction.

- **Adaptive clip length**
  - Right now every clip is a fixed 15 seconds. We can  **change clip length by context**: e.g. shorter when people talk fast (so one “idea” fits in one clip), longer when they talk slow; or align clip boundaries with **scene cuts** so a highlight doesn’t cut in the middle of a scene. Also **merge** overlapping high‑score segments (e.g. 0–15s and 5–20s) into one longer highlight instead of returning two overlapping clips.

- **Persistence and scalability**
  - Replace the in‑memory Job repository with DynamoDB or a relational database.
  - Store original videos and extracted audios on S3. Turn on **S3 lifecycle rules** to expire or transition old objects (e.g. delete after 7 days, or move to Glacier); that keeps storage costs down by cleaning up files automatically.

- **More UX polish**
  - Embed a small video player so users can jump straight to each highlight instead of copying timestamps elsewhere.


