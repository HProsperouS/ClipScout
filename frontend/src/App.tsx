import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";

type Clip = {
  start: number;
  end: number;
  score: number;
  energy_score: number;
  speech_density_score: number;
  reason: string;
};

type JobStatus = "processing" | "completed" | "failed";

type JobDetail = {
  id: string;
  status: JobStatus;
  clips: Clip[];
  error_message?: string | null;
};

type UiState = "idle" | "submitting" | "polling";

const API_BASE =
  import.meta.env.VITE_API_BASE ??
  (import.meta.env.DEV ? "http://localhost:8000" : "");

function formatTime(seconds: number): string {
  const s = Math.max(0, Math.round(seconds));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  return `${h.toString().padStart(2, "0")}:${m.toString().padStart(2, "0")}:${sec.toString().padStart(2, "0")}`;
}

type LinkSource = "youtube" | "dropbox";

function App() {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [linkUrl, setLinkUrl] = useState("");
  const [linkSource, setLinkSource] = useState<LinkSource>("youtube");
  const [job, setJob] = useState<JobDetail | null>(null);
  const [uiState, setUiState] = useState<UiState>("idle");
  const [error, setError] = useState<string | null>(null);

  // Poll job status while it's processing
  useEffect(() => {
    if (!job || job.status !== "processing") return;

    setUiState("polling");

    const id = setInterval(async () => {
      try {
        const res = await fetch(`${API_BASE}/api/jobs/${job.id}`);
        if (!res.ok) {
          throw new Error("Failed to fetch job");
        }
        const data: JobDetail = await res.json();
        setJob(data);

        if (data.status !== "processing") {
          clearInterval(id);
          setUiState("idle");
        }
      } catch (e) {
        console.error(e);
        setError("Failed to poll job status. Please try again.");
        clearInterval(id);
        setUiState("idle");
      }
    }, 2000);

    return () => clearInterval(id);
  }, [job]);

  const handleFileChange: React.ChangeEventHandler<HTMLInputElement> = (e) => {
    const file = e.target.files?.[0] ?? null;
    setSelectedFile(file);
    setJob(null);
    setError(null);
  };

  const handleLinkSubmit: React.FormEventHandler<HTMLFormElement> = async (e) => {
    e.preventDefault();
    setError(null);
    const url = linkUrl.trim();
    if (!url) {
      setError("Please paste a YouTube or Dropbox link.");
      return;
    }
    try {
      setUiState("submitting");
      const res = await fetch(`${API_BASE}/api/jobs/from-link`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url, source: linkSource }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || "Failed to create job from link");
      }
      const data: JobDetail = await res.json();
      setJob(data);
    } catch (e) {
      console.error(e);
      setError(e instanceof Error ? e.message : "Failed to create job from link.");
      setUiState("idle");
    }
  };

  const handleSubmit: React.FormEventHandler<HTMLFormElement> = async (e) => {
    e.preventDefault();
    setError(null);

    if (!selectedFile) {
      setError("Please select a video file first.");
      return;
    }

    try {
      setUiState("submitting");
      const formData = new FormData();
      formData.append("file", selectedFile);

      const res = await fetch(`${API_BASE}/api/jobs`, {
        method: "POST",
        body: formData,
      });

      if (!res.ok) {
        throw new Error("Failed to create job");
      }

      const data: JobDetail = await res.json();
      setJob(data);
    } catch (e) {
      console.error(e);
      setError("Failed to create processing job. Check that the backend is running.");
      setUiState("idle");
    }
  };

  const renderStatus = (status?: JobStatus) => {
    if (!status) return "Idle";
    if (status === "processing") return "Processing…";
    if (status === "completed") return "Completed";
    if (status === "failed") return "Failed";
    return status;
  };

  const isBusy = uiState === "submitting" || uiState === "polling";

  return (
    <div className="min-h-screen bg-background text-foreground">
      <div className="mx-auto flex max-w-4xl flex-col gap-6 px-4 py-8">
        <header className="space-y-2">
          <h1 className="text-3xl font-semibold tracking-tight">ClipScout</h1>
          <p className="text-sm text-muted-foreground">
            Upload a long-form video and automatically discover the top 3 highlight clips.
          </p>
        </header>

        {/* Upload section */}
        <section className="space-y-4 rounded-xl border bg-card p-4">
          <h2 className="text-base font-medium">1. Upload video</h2>
          <form
            onSubmit={handleSubmit}
            className="flex flex-col gap-3 sm:flex-row sm:items-center"
          >
            <input
              type="file"
              accept="video/*"
              onChange={handleFileChange}
              disabled={isBusy}
              className="text-sm file:mr-3 file:rounded-md file:border file:border-input file:bg-background file:px-3 file:py-1.5 file:text-sm file:font-medium hover:file:bg-accent hover:file:text-accent-foreground"
            />
            <Button type="submit" disabled={!selectedFile || isBusy}>
              {uiState === "submitting" ? "Starting job…" : "Start processing"}
            </Button>
          </form>
          {selectedFile && (
            <p className="text-xs text-muted-foreground">
              Selected: <span className="font-medium">{selectedFile.name}</span>{" "}
              ({(selectedFile.size / (1024 * 1024)).toFixed(1)} MB)
            </p>
          )}
          {error && <p className="text-xs text-red-500">{error}</p>}
        </section>

        {/* YouTube / Dropbox link section */}
        <section className="space-y-4 rounded-xl border bg-card p-4">
          <h2 className="text-base font-medium">Or paste a link</h2>
          <form
            onSubmit={handleLinkSubmit}
            className="flex flex-col gap-3 sm:flex-row sm:items-center sm:gap-2"
          >
            <select
              value={linkSource}
              onChange={(e) => setLinkSource(e.target.value as LinkSource)}
              disabled={isBusy}
              className="rounded-md border border-input bg-background px-3 py-2 text-sm"
            >
              <option value="youtube">YouTube</option>
              <option value="dropbox">Dropbox</option>
            </select>
            <input
              type="url"
              placeholder={linkSource === "youtube" ? "https://www.youtube.com/watch?v=..." : "https://www.dropbox.com/..."}
              value={linkUrl}
              onChange={(e) => setLinkUrl(e.target.value)}
              disabled={isBusy}
              className="min-w-0 flex-1 rounded-md border border-input bg-background px-3 py-2 text-sm"
            />
            <Button type="submit" disabled={!linkUrl.trim() || isBusy}>
              Process from link
            </Button>
          </form>
        </section>

        {/* Status section */}
        <section className="space-y-2 rounded-xl border bg-card p-4">
          <h2 className="text-base font-medium">2. Job status</h2>
          <p className="text-sm">
            Status:{" "}
            <span className="inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium">
              {renderStatus(job?.status)}
            </span>
          </p>
          {job && (
            <p className="break-all text-xs text-muted-foreground">
              Job ID: <code>{job.id}</code>
            </p>
          )}
          {job?.status === "failed" && job.error_message && (
            <p className="mt-1 text-xs text-red-500">
              Error: {job.error_message}
            </p>
          )}
        </section>

        {/* Results section */}
        <section className="space-y-3 rounded-xl border bg-card p-4">
          <h2 className="text-base font-medium">3. Top 3 clips</h2>
          {job?.clips?.length ? (
            <div className="space-y-3">
              {job.clips.map((clip, idx) => (
                <div
                  key={`${clip.start}-${clip.end}-${idx}`}
                  className="space-y-1.5 rounded-lg border bg-background/60 p-3 text-sm"
                >
                  <div className="flex items-center justify-between">
                    <span className="font-semibold">Clip #{idx + 1}</span>
                    <span className="text-xs text-muted-foreground">
                      {formatTime(clip.start)}–{formatTime(clip.end)}
                    </span>
                  </div>
                  <div className="text-xs text-muted-foreground">
                    Score: {clip.score.toFixed(3)} (energy {clip.energy_score.toFixed(2)}, speech{" "}
                    {clip.speech_density_score.toFixed(2)})
                  </div>
                  <p className="whitespace-pre-line text-sm leading-snug">{clip.reason}</p>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">
              No clips yet. Create a job and wait until the status becomes{" "}
              <span className="font-medium">Completed</span> to see the top 3 clips here.
            </p>
          )}
        </section>
      </div>
    </div>
  );
}

export default App;
