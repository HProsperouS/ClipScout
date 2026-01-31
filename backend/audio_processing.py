import math
from dataclasses import dataclass
from typing import List

import librosa
import numpy as np


@dataclass
class ClipResult:
    start: float
    end: float
    score: float
    energy_score: float
    speech_density_score: float
    reason: str


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
    # RMS energy per frame
    rms = np.sqrt(np.mean(frames ** 2, axis=1) + 1e-9)
    if rms.max() > 0:
        rms /= rms.max()
    return rms


def _compute_speech_activity(frames: np.ndarray, energy: np.ndarray, threshold: float = 0.3) -> np.ndarray:
    """
    Very simple VAD proxy based on normalized energy.

    Returns an array in [0, 1] representing "speech likelihood" per frame.
    """
    # Smooth threshold: map energy above threshold closer to 1, below closer to 0.
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
        # Fallback: single clip covering all frames
        indices.append((0, num_frames))

    return indices


def _build_reason(
    start: float,
    end: float,
    energy_score: float,
    speech_density_score: float,
) -> str:
    """
    Construct a human-readable explanation for why this clip was selected.
    """
    duration = end - start
    energy_pct = int(energy_score * 100)
    speech_pct = int(speech_density_score * 100)

    parts = [
        f"Duration {duration:.1f}s, from {start:.1f}s to {end:.1f}s.",
        f"Average audio energy is around top {energy_pct}% of the video.",
        f"Speech (or active audio) covers about {speech_pct}% of this segment.",
    ]
    if energy_score > 0.7 and speech_density_score > 0.6:
        parts.append(
            "This likely captures a high-energy, information-dense moment such as a key explanation, highlight, or emotional peak."
        )
    elif speech_density_score > 0.7:
        parts.append(
            "Most of this segment is active speech, suggesting a focused explanation or important discussion."
        )
    elif energy_score > 0.7:
        parts.append(
            "The audio energy spikes here, which often corresponds to dramatic or emotionally intense moments."
        )
    else:
        parts.append(
            "This segment balances moderate energy and speech activity, making it a potentially useful supporting highlight."
        )

    return " ".join(parts)


def extract_top_clips(
    audio_path: str,
    target_sr: int = 16000,
    frame_duration_seconds: float = 1.0,
    clip_length_seconds: float = 15.0,
    step_seconds: float = 5.0,
    w_energy: float = 0.4,
    w_speech: float = 0.6,
    top_k: int = 3,
) -> List[ClipResult]:
    """
    Core algorithm:
    - Load audio
    - Split into fixed-length frames
    - Compute energy and a simple speech-activity proxy
    - Slide a window over frames to build candidate clips
    - Score each clip using a weighted combination of energy & speech density
    - Return the top_k clips with explanations
    """
    y, sr = librosa.load(audio_path, sr=target_sr, mono=True)

    if len(y) == 0:
        return []

    frames = _frame_signal(y, sr=sr, window_seconds=frame_duration_seconds)
    num_frames = frames.shape[0]

    energy = _compute_window_energy(frames)
    speech_activity = _compute_speech_activity(frames, energy)

    indices = _sliding_window_indices(
        num_frames=num_frames,
        clip_length_seconds=clip_length_seconds,
        step_seconds=step_seconds,
        frame_duration_seconds=frame_duration_seconds,
    )

    clip_results: List[ClipResult] = []
    for start_idx, end_idx in indices:
        window_energy = energy[start_idx:end_idx]
        window_speech = speech_activity[start_idx:end_idx]

        if len(window_energy) == 0:
            continue

        energy_score = float(window_energy.mean())
        speech_density_score = float(window_speech.mean())

        # Combined score; tweakable weights
        score = w_energy * energy_score + w_speech * speech_density_score

        # Convert from frame indices to seconds
        start_sec = start_idx * frame_duration_seconds
        end_sec = end_idx * frame_duration_seconds

        reason = _build_reason(
            start=start_sec,
            end=end_sec,
            energy_score=energy_score,
            speech_density_score=speech_density_score,
        )

        clip_results.append(
            ClipResult(
                start=start_sec,
                end=end_sec,
                score=score,
                energy_score=energy_score,
                speech_density_score=speech_density_score,
                reason=reason,
            )
        )

    # Sort by score descending and take top_k
    clip_results.sort(key=lambda c: c.score, reverse=True)
    return clip_results[:top_k]

