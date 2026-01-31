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
  - Optional deployment: single Docker container on **AWS EC2** (no ALB); see [Deploying to AWS](#deploying-to-aws-ec2) below.

- **Domain design**
  - `Job` – represents a single processing run (`id`, `status`, `clips`, `error_message`).
  - `Clip` – candidate highlight (`start`, `end`, `score`, `energy_score`, `speech_density_score`, `keyword_score`, `reason`).
  - Layers:
    - `backend/app` – FastAPI wiring, HTTP schemas and routes.
    - `backend/domain` – business logic (clip ranking, job orchestration).
    - `backend/infrastructure` – ffmpeg, Whisper ASR, YouTube/Dropbox downloaders, in‑memory persistence.

---

## How clip ranking works (Top 3 Clips)

There is intentionally no strict definition of “best” clips in the exercise. The strategy here is simple, explainable, and robust within the 5‑hour constraint:

### Core intuition

> Moments where people talk a lot and the audio energy changes more are usually where the content is important, emotional, or has a narrative peak.

Each candidate clip is scored using up to three signals:

1. **Audio energy** – how loud / dynamic the segment is (RMS, normalized).
2. **Speech activity density** – how much of the segment contains active speech or strong audio (simple energy-based VAD proxy).
3. **Keyword relevance** (optional) – when Whisper ASR is available, we transcribe the audio, extract top keywords by frequency (excluding stopwords), and score each clip by how many of those keywords appear in speech within that clip’s time range.

Signals are normalized to \[0, 1\] and combined:

\[
score = w_\text{energy} \cdot energy\_score + w_\text{speech} \cdot speech\_density\_score + w_\text{keyword} \cdot keyword\_score
\]

Default weights when Whisper is used: \(w_\text{energy} = 0.35\), \(w_\text{speech} = 0.35\), \(w_\text{keyword} = 0.3\). If Whisper is not installed or fails, we fall back to energy + speech only (e.g. 0.4 and 0.6).

### Detailed pipeline

1. **Extract audio from video**
   - Use `ffmpeg` (via `backend/infrastructure/ffmpeg_adapter.py`) to extract mono 16 kHz WAV audio from the input video.

2. **Frame the audio**
   - Resample to 16 kHz and split into **non‑overlapping 1‑second frames**.
   - Each frame represents 1 second of audio for which we compute features.

3. **Compute per‑frame energy**
   - For each frame, compute **RMS energy**.
   - Normalize energies so the maximum observed energy becomes 1.0 and others fall in \[0, 1\].

4. **Approximate speech activity (simple VAD proxy)**
   - Instead of using a heavy ASR model, approximate speech activity directly from energy:
     - Values above a threshold (default 0.3) are treated as “more likely speech or meaningful audio”.
     - Map energies into \[0, 1\] so we obtain a **speech activity score per frame**.
   - This keeps the system lightweight and easy to run anywhere, while still capturing where the content is active.

5. **Build candidate clips with a sliding window**
   - Choose a fixed clip length, e.g. **15 seconds**, and a step size, e.g. **5 seconds**.
   - Slide a window over the per‑second frames to construct overlapping candidate clips.
   - For each candidate clip:
     - `energy_score` = mean energy across all frames in the window.
     - `speech_density_score` = mean speech activity across all frames in the window.

6. **Optional: Whisper ASR and keyword scoring**
   - If `openai-whisper` is installed, we transcribe the audio to segments with timestamps, extract top‑20 keywords (by frequency, excluding stopwords), and compute per‑clip `keyword_score` from keyword hits in that time range. This is blended into the final score.

7. **Score and select Top 3**
   - For each candidate clip, compute the weighted score (energy + speech + optional keyword).
   - Sort all candidates by score (descending).
   - Return the **top 3** as the final results.

8. **Human‑readable explanations**
   - For each selected clip we generate a short text explanation (time range, energy/speech/keyword signals, and a prose reason). These are returned to the frontend so the ranking is **transparent and easy to justify**.

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

Rather than a single “RPC‑style” `/process` endpoint, the backend models processing as a **Job resource**, which is more idiomatic for REST and makes progress tracking explicit.

- **Create job (file upload)**
  - `POST /api/jobs`
  - Request: `multipart/form-data` with a `file` field (video file).
  - Behavior: saves the video under `jobs/`, creates a `Job` with status `processing`, schedules background processing, returns `202 Accepted` with `id`, `status="processing"`, empty `clips`.

- **Create job (YouTube or Dropbox link)**
  - `POST /api/jobs/from-link`
  - Request: JSON body `{ "url": "<link>", "source": "youtube" | "dropbox" }`.
  - Behavior: downloads content (yt-dlp for YouTube, HTTP for Dropbox), then same processing as above; returns `202 Accepted`.

- **Get job status and results**
  - `GET /api/jobs/{job_id}`
  - Response:
    - `id`
    - `status`: `"processing" | "completed" | "failed"`
    - `clips`: array of clip objects once completed.
    - `error_message`: error info if the job failed.

- **Get clips only**
  - `GET /api/jobs/{job_id}/clips`
  - Returns the clip array when `status="completed"`.
  - Returns `409` if the job is not completed yet.

This design makes it natural for the frontend to:

- Fire an upload request once.
- Poll `GET /api/jobs/{job_id}` every few seconds.
- Stop polling when the job reaches `"completed"` or `"failed"`.

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
- **No ALB** – access the app via the instance **public IP** (or an Elastic IP). Open port **80** (and optionally **22** for SSH) in the security group.
- **Storage** – uploaded videos and extracted audio are stored under a directory on the instance (e.g. `jobs/`). For persistence across restarts, use the instance root volume or attach an EBS volume.

### Terraform (recommended)

Use the `terraform/` directory to provision EC2 + security group (no ALB). See **terraform/README.md** for:

- `terraform init` → `terraform plan` → `terraform apply`
- Set `key_name` in `terraform.tfvars` (EC2 key pair for SSH)
- After apply: SSH to the instance, build/run the Docker image, then open `http://<public_ip>:8000`

### Steps (outline)

1. **Build and run with Docker** (from project root):
   - `docker build -t clipscout .` then `docker run -p 8000:8000 clipscout`. The image includes the backend, built frontend, ffmpeg, and Python deps (including `openai-whisper` for keyword scoring). FastAPI serves both `/api/*` and the static SPA on port 8000.
   - On EC2, expose port 8000 in the security group and use `http://<public-ip>:8000`, or put Nginx/Caddy on port 80 proxying to 8000.

2. **Launch EC2**
   - AMI: Amazon Linux 2 or Ubuntu.
   - Instance type: **t2.micro** or **t3.micro** (Free Tier).
   - Security group: allow **22** (SSH), **80** (HTTP); if you skip a reverse proxy, allow **8000** and use `http://<public-ip>:8000`.

3. **On the instance**
   - Install Docker (and Docker Compose if you use it), clone the repo, build the image, and run the container. Ensure the app listens on `0.0.0.0` and that the `jobs` directory is writable (e.g. a volume or host path).

4. **Frontend API base**
   - When serving the SPA from the same host as the API, set the frontend `API_BASE` to `""` (relative URLs) so the browser uses the same origin.

5. **Optional: Whisper on 1 GB RAM**
   - For t2.micro/t3.micro, use Whisper **tiny** (or **base** with care) to reduce memory use; you can set the model size via environment or config.

6. **YouTube “Sign in to confirm you’re not a bot” (EC2)**
   - When running on EC2, YouTube may require bot verification. Export YouTube cookies from your browser (Netscape format; e.g. “Get cookies.txt” extension), put the file on the instance, and run the container with `-e YT_COOKIES_FILE=/app/cookies.txt -v /path/on/ec2/cookies.txt:/app/cookies.txt:ro`. Rebuild/restart the container after adding the volume and env. See [yt-dlp FAQ](https://github.com/yt-dlp/yt-dlp/wiki/FAQ#how-do-i-pass-cookies-to-yt-dlp).

Once the container is running and the security group allows traffic, open `http://<public-ip>:8000` in a browser to use ClipScout.

---

## Trade‑offs and possible improvements

With more time, the following improvements would be high‑value:

- **Richer clip quality model**
  - Whisper + keyword scoring is already in place; possible extensions: sentence‑level importance (e.g. embeddings + clustering), topic or sentiment weighting.

- **Better VAD / diarization**
  - Replace the simple energy‑threshold proxy with a real VAD model.
  - Optionally identify speaker turns and prioritize segments with more interaction.

- **Adaptive clip length**
  - Dynamically adjust clip length based on speaking pace and scene changes.
  - Optionally merge overlapping high‑score windows into a single longer highlight.

- **Persistence and scalability**
  - Replace the in‑memory Job repository with DynamoDB or a relational database.
  - Store original videos and extracted audios on S3.
  - Add background workers (e.g. Celery, AWS SQS + Lambda) for heavy processing.

- **More UX polish**
  - Show a visual progress indicator while processing.
  - Add a small embedded video player that can seek directly to each clip.

Even without these extensions, the current solution satisfies the core requirements of the exercise, with a clear, explainable ranking strategy and a clean, RESTful architecture suitable for production‑style discussions.

