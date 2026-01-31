from pathlib import Path
from typing import List, Optional

import librosa
import numpy as np

from backend.domain.models import Clip
from backend.infrastructure.ffmpeg_adapter import extract_audio
from backend.infrastructure.whisper_adapter import (
    TranscriptSegment,
    transcribe,
    extract_keywords,
    get_text_in_time_range,
)


def _frame_signal(
    y: np.ndarray,
    sr: int,
    window_seconds: float = 1.0,
) -> np.ndarray:
    """Split audio into non-overlapping windows of fixed duration."""
    samples_per_window = int(window_seconds * sr)
    total_windows = len(y) // samples_per_window
    trimmed = y[: total_windows * samples_per_window]
    return trimmed.reshape(total_windows, samples_per_window)


def _compute_window_energy(frames: np.ndarray) -> np.ndarray:
    """Compute RMS energy per frame and normalize to [0, 1]."""
    rms = np.sqrt(np.mean(frames ** 2, axis=1) + 1e-9)
    if rms.max() > 0:
        rms /= rms.max()
    return rms


def _compute_speech_activity(energy: np.ndarray, threshold: float = 0.3) -> np.ndarray:
    """
    Very simple VAD proxy based on normalized energy.
    Returns an array in [0, 1] representing "speech likelihood" per frame.
    """
    activity = (energy - threshold) / (1.0 - threshold)
    activity = np.clip(activity, 0.0, 1.0)
    return activity


def _sliding_window_indices(
    num_frames: int,
    clip_length_seconds: float,
    step_seconds: float,
    frame_duration_seconds: float,
) -> List[tuple]:
    """Generate (start_frame, end_frame) indices for candidate clips."""
    frames_per_clip = int(clip_length_seconds / frame_duration_seconds)
    step_frames = int(step_seconds / frame_duration_seconds)

    indices = []
    start = 0
    while start + frames_per_clip <= num_frames:
        indices.append((start, start + frames_per_clip))
        start += max(step_frames, 1)

    if not indices and num_frames > 0:
        indices.append((0, num_frames))

    return indices


def _format_time(seconds: float) -> str:
    """Format seconds as HH:MM:SS."""
    s = max(0, int(round(seconds)))
    h = s // 3600
    m = (s % 3600) // 60
    sec = s % 60
    return f"{h:02d}:{m:02d}:{sec:02d}"


def _build_reason(
    start: float,
    end: float,
    energy_score: float,
    speech_density_score: float,
    keyword_score: float = 0.0,
) -> str:
    """
    Construct a human-readable explanation for why this clip was selected.
    """
    duration = end - start
    energy_pct = int(round(energy_score * 100))
    speech_pct = int(round(speech_density_score * 100))

    signals_line = (
        f"Signals: average audio energy around top {energy_pct}% of the video; "
        f"speech or active audio covers about {speech_pct}% of this segment."
    )
    if keyword_score > 0:
        kw_pct = int(round(keyword_score * 100))
        signals_line += f" Keyword relevance (from speech) about top {kw_pct}%."

    if energy_score > 0.7 and speech_density_score > 0.6:
        detailed_reason = (
            "This segment combines high audio energy with dense speech activity, which "
            "typically corresponds to a key highlight where the speaker is actively explaining "
            "or reacting to something important."
        )
    elif speech_density_score > 0.7:
        detailed_reason = (
            "Most of this segment is continuous speech, suggesting a focused explanation or "
            "discussion where information density is high."
        )
    elif energy_score > 0.7:
        detailed_reason = (
            "The audio energy spikes here while speech is intermittent, which often matches "
            "emotional reactions, emphasis, or dramatic transitions in the content."
        )
    else:
        detailed_reason = (
            "Both energy and speech activity are in a moderate range, making this segment a "
            "supporting moment that connects more intense highlights before and after it."
        )
    if keyword_score > 0.5:
        detailed_reason += (
            " The speech in this segment contains prominent keywords from the transcript."
        )

    return (
        f"Time: {_format_time(start)}–{_format_time(end)} ({duration:.1f}s)\n"
        f"{signals_line}\n"
        f"Reason: {detailed_reason}"
    )


def _keyword_score_for_clip(
    start_sec: float,
    end_sec: float,
    segments: List[TranscriptSegment],
    keywords: List[str],
) -> float:
    """
    Score [start_sec, end_sec] by how many keywords appear in speech in that range.
    Returns value in [0, 1] (normalized by max possible hits in this clip).
    """
    if not keywords:
        return 0.0
    text = get_text_in_time_range(segments, start_sec, end_sec)
    text_lower = text.lower()
    words = set()
    for w in text_lower.split():
        w = "".join(c for c in w if c.isalnum())
        if len(w) >= 2:
            words.add(w)
    hits = sum(1 for kw in keywords if kw.lower() in words)
    return min(1.0, hits / max(1, len(keywords) * 0.3))


def _extract_top_clips_from_audio(
    audio_path: Path,
    target_sr: int = 16000,
    frame_duration_seconds: float = 1.0,
    clip_length_seconds: float = 15.0,
    step_seconds: float = 5.0,
    w_energy: float = 0.4,
    w_speech: float = 0.6,
    w_keyword: float = 0.0,
    segments: Optional[List[TranscriptSegment]] = None,
    keywords: Optional[List[str]] = None,
    top_k: int = 3,
) -> List[Clip]:
    """
    Core algorithm working on a prepared audio file.
    If segments and keywords are provided (from Whisper), keyword_score is computed and blended.
    """
    y, sr = librosa.load(str(audio_path), sr=target_sr, mono=True)

    if len(y) == 0:
        return []

    use_keywords = w_keyword > 0 and segments is not None and keywords is not None
    if use_keywords:
        total = w_energy + w_speech + w_keyword
        w_energy, w_speech, w_keyword = w_energy / total, w_speech / total, w_keyword / total
    else:
        w_keyword = 0.0

    frames = _frame_signal(y, sr=sr, window_seconds=frame_duration_seconds)
    num_frames = frames.shape[0]

    energy = _compute_window_energy(frames)
    speech_activity = _compute_speech_activity(energy)

    indices = _sliding_window_indices(
        num_frames=num_frames,
        clip_length_seconds=clip_length_seconds,
        step_seconds=step_seconds,
        frame_duration_seconds=frame_duration_seconds,
    )

    clips: List[Clip] = []
    for start_idx, end_idx in indices:
        window_energy = energy[start_idx:end_idx]
        window_speech = speech_activity[start_idx:end_idx]

        if len(window_energy) == 0:
            continue

        energy_score = float(window_energy.mean())
        speech_density_score = float(window_speech.mean())

        start_sec = start_idx * frame_duration_seconds
        end_sec = end_idx * frame_duration_seconds

        keyword_score = 0.0
        if use_keywords and segments and keywords:
            keyword_score = _keyword_score_for_clip(start_sec, end_sec, segments, keywords)

        score = (
            w_energy * energy_score
            + w_speech * speech_density_score
            + w_keyword * keyword_score
        )

        reason = _build_reason(
            start=start_sec,
            end=end_sec,
            energy_score=energy_score,
            speech_density_score=speech_density_score,
            keyword_score=keyword_score,
        )

        clips.append(
            Clip(
                start=start_sec,
                end=end_sec,
                score=score,
                energy_score=energy_score,
                speech_density_score=speech_density_score,
                reason=reason,
                keyword_score=keyword_score,
            )
        )

    clips.sort(key=lambda c: c.score, reverse=True)
    return clips[:top_k]


def process_video_file(video_path: Path) -> List[Clip]:
    """
    High-level domain service:
    - Extract audio from video
    - Transcribe with Whisper and extract keywords
    - Run highlight discovery (energy + speech + keyword relevance)
    - Return the Top 3 clips
    """
    audio_path = video_path.with_suffix(".analysis.wav")
    extract_audio(video_path, audio_path)
    return _run_highlight_discovery(
        audio_path,
        w_energy=0.35,
        w_speech=0.35,
        w_keyword=0.3,
    )


def process_audio_file(audio_path: Path) -> List[Clip]:
    """
    Run highlight discovery on an existing audio file (e.g. from YouTube download).
    Uses Whisper for ASR and keyword-based scoring when available.
    """
    return _run_highlight_discovery(
        audio_path,
        w_energy=0.35,
        w_speech=0.35,
        w_keyword=0.3,
    )


def _run_highlight_discovery(
    audio_path: Path,
    *,
    w_energy: float = 0.35,
    w_speech: float = 0.35,
    w_keyword: float = 0.3,
    whisper_model: str | None = None,
) -> List[Clip]:
    """
    Run ASR with Whisper, extract keywords, then score clips.
    On Whisper failure, falls back to energy + speech only (keyword_score=0).
    whisper_model: "tiny" | "base" | "small" | ...; default from env WHISPER_MODEL or "tiny".
    """
    import os
    model_size = whisper_model or os.environ.get("WHISPER_MODEL", "tiny")
    segments: Optional[List[TranscriptSegment]] = None
    keywords: Optional[List[str]] = None
    try:
        segments = transcribe(audio_path, model_size=model_size)
        if segments:
            keywords = extract_keywords(segments, top_k=20)
    except Exception:
        segments = None
        keywords = None

    return _extract_top_clips_from_audio(
        audio_path,
        w_energy=w_energy,
        w_speech=w_speech,
        w_keyword=w_keyword if (segments and keywords) else 0.0,
        segments=segments,
        keywords=keywords,
    )
