"""
Download video/audio from external URLs (YouTube, Dropbox, etc.).
"""
from pathlib import Path

import requests
import yt_dlp


def download_youtube(url: str, output_path: Path) -> None:
    """
    Download audio from a YouTube URL to a WAV file using yt-dlp.
    output_path should end in .wav; yt-dlp will produce that file.
    """
    output_path = output_path.with_suffix(".wav")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    opts = {
        "format": "bestaudio/best",
        "outtmpl": str(output_path.with_suffix("")),
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "wav",
                "preferredquality": None,
            }
        ],
        "quiet": True,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([url])
    if not output_path.exists():
        raise RuntimeError("yt-dlp did not produce a WAV file")


def download_dropbox(url: str, output_path: Path) -> None:
    """
    Download file from a Dropbox shared link.
    Converts share links to direct download by appending ?dl=1 if needed.
    Saves to output_path (extension may not match; ffmpeg will detect format).
    """
    download_url = url.strip()
    if "dropbox.com" in download_url and "?dl=" not in download_url:
        download_url = download_url + ("&" if "?" in download_url else "?") + "dl=1"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    resp = requests.get(download_url, stream=True, timeout=120, allow_redirects=True)
    resp.raise_for_status()
    with open(output_path, "wb") as f:
        for chunk in resp.iter_content(chunk_size=8192):
            if chunk:
                f.write(chunk)
