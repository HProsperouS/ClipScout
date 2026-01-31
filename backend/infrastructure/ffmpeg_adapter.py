from pathlib import Path

import ffmpeg


def extract_audio(input_video: Path, output_audio: Path, *, sample_rate: int = 16000) -> None:
    """
    Extract mono WAV audio suitable for analysis from a video file.
    """
    try:
        (
            ffmpeg.input(str(input_video))
            .output(
                str(output_audio),
                ac=1,  # mono
                ar=sample_rate,
                format="wav",
            )
            .overwrite_output()
            .run(quiet=True)
        )
    except ffmpeg.Error as e:
        raise RuntimeError(f"ffmpeg failed: {e}") from e

