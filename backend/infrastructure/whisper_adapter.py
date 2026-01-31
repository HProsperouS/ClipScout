"""
Whisper ASR adapter: transcribe audio to segments with timestamps,
and extract top keywords from the transcript for clip scoring.
"""
from dataclasses import dataclass
from pathlib import Path
import re
from typing import List

# Simple English stopwords for keyword extraction (subset to avoid heavy deps)
_STOPWORDS = frozenset(
    {
        "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
        "of", "with", "by", "from", "as", "is", "was", "are", "were", "been",
        "be", "have", "has", "had", "do", "does", "did", "will", "would",
        "could", "should", "may", "might", "must", "shall", "can", "this",
        "that", "these", "those", "i", "you", "he", "she", "it", "we", "they",
        "what", "which", "who", "when", "where", "why", "how", "all", "each",
        "every", "both", "few", "more", "most", "other", "some", "such", "no",
        "nor", "not", "only", "own", "same", "so", "than", "too", "very", "just",
    }
)


@dataclass
class TranscriptSegment:
    """One segment from Whisper with start/end times (seconds) and text."""
    start: float
    end: float
    text: str


def transcribe(audio_path: Path, *, model_size: str = "base") -> List[TranscriptSegment]:
    """
    Run Whisper on an audio file and return segments with timestamps.
    Uses the given model size (tiny, base, small, medium, large).
    """
    import whisper

    model = whisper.load_model(model_size)
    result = model.transcribe(str(audio_path), language=None, fp16=False)
    segments: List[TranscriptSegment] = []
    for seg in result.get("segments", []):
        start = float(seg.get("start", 0))
        end = float(seg.get("end", start))
        text = (seg.get("text") or "").strip()
        if text:
            segments.append(TranscriptSegment(start=start, end=end, text=text))
    return segments


def _tokenize(text: str) -> List[str]:
    """Lowercase and split on non-alphanumeric, keep words of length >= 2."""
    text = text.lower()
    words = re.findall(r"[a-z0-9]{2,}", text)
    return words


def extract_keywords(
    segments: List[TranscriptSegment],
    top_k: int = 20,
    min_freq: int = 1,
) -> List[str]:
    """
    Extract top keywords from transcript segments by frequency,
    excluding stopwords. Returns list of words ordered by count (desc).
    """
    from collections import Counter

    counter: Counter[str] = Counter()
    for seg in segments:
        for word in _tokenize(seg.text):
            if word not in _STOPWORDS:
                counter[word] += 1

    # Return top_k by count; require min_freq
    ordered = [w for w, c in counter.most_common(top_k * 2) if c >= min_freq]
    return ordered[:top_k]


def get_text_in_time_range(
    segments: List[TranscriptSegment],
    start_sec: float,
    end_sec: float,
) -> str:
    """Return concatenated text of segments that overlap [start_sec, end_sec]."""
    parts = []
    for seg in segments:
        if seg.end < start_sec or seg.start > end_sec:
            continue
        parts.append(seg.text)
    return " ".join(parts)
