from __future__ import annotations

import math
import os
import tempfile
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Optional
from tempfile import NamedTemporaryFile

SUPPORTED_AUDIO_TYPES = {
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
    "audio/mpeg": ".mp3",
    "audio/mp3": ".mp3",
    "audio/mp4": ".m4a",
    "audio/x-m4a": ".m4a",
    "audio/webm": ".webm",
    "audio/ogg": ".ogg",
}

# Video containers accepted by the video endpoint.  Only the audio track
# is ever decoded on the server; frames are analysed in the browser.
SUPPORTED_VIDEO_TYPES = {
    "video/webm": ".webm",
    "video/mp4": ".mp4",
    "video/quicktime": ".mov",
    "video/x-matroska": ".mkv",
}

MAX_AUDIO_SIZE_BYTES = 25 * 1024 * 1024
MAX_VIDEO_SIZE_BYTES = 100 * 1024 * 1024


@lru_cache(maxsize=1)
def load_whisper_model():
    try:
        import whisper
    except ImportError as exc:
        raise RuntimeError(
            "Whisper is not installed. Run: pip install openai-whisper"
        ) from exc

    model_name = os.getenv("WHISPER_MODEL", "base")
    return whisper.load_model(model_name)


def transcribe_audio(audio_path: str) -> Dict[str, Any]:
    try:
        model = load_whisper_model()
        result = model.transcribe(audio_path, fp16=False)

        return {
            "available": True,
            "text": result.get("text", "").strip(),
            "language": result.get("language") or "unknown",
            "segments": result.get("segments", []),
        }
    except Exception as exc:
        return {
            "available": False,
            "text": "",
            "language": "unknown",
            "segments": [],
            "error": str(exc),
        }


def validate_audio(
    filename: Optional[str],
    content_type: Optional[str],
    file_size: int,
) -> None:
    if file_size <= 0:
        raise ValueError("Audio file is empty.")

    if file_size > MAX_AUDIO_SIZE_BYTES:
        raise ValueError("Audio file exceeds the 25 MB limit.")

    if content_type:
        normalized_type = content_type.lower().strip()

        if normalized_type not in SUPPORTED_AUDIO_TYPES:
            raise ValueError(
                f"Unsupported audio type: {content_type}"
            )

    if not filename:
        raise ValueError("Invalid audio filename.")

    path = Path(filename)

    if (
        path.name != filename
        or path.name in {".", ".."}
    ):
        raise ValueError("Invalid audio filename.")

    extension = path.suffix.lower()
    supported_extensions = set(SUPPORTED_AUDIO_TYPES.values())

    if extension and extension not in supported_extensions:
        raise ValueError(
            f"Unsupported audio extension: {extension}"
        )

def validate_media(
    filename: Optional[str],
    content_type: Optional[str],
    file_size: int,
) -> str:
    """
    Validate an upload that may be either audio or a video container.

    Returns ``"audio"`` or ``"video"``.
    """
    if file_size <= 0:
        raise ValueError("Media file is empty.")

    normalized_type = (content_type or "").lower().strip().split(";", 1)[0]
    extension = Path(filename or "").suffix.lower()

    is_video = (
        normalized_type in SUPPORTED_VIDEO_TYPES
        or (not normalized_type and extension in set(SUPPORTED_VIDEO_TYPES.values()))
        # audio/webm and video/webm share an extension; trust the MIME type.
    )

    if is_video:
        if file_size > MAX_VIDEO_SIZE_BYTES:
            raise ValueError("Video file exceeds the 100 MB limit.")
        if not filename:
            raise ValueError("Invalid media filename.")
        path = Path(filename)
        if path.name != filename or path.name in {".", ".."}:
            raise ValueError("Invalid media filename.")
        if extension and extension not in set(SUPPORTED_VIDEO_TYPES.values()):
            raise ValueError(f"Unsupported video extension: {extension}")
        return "video"

    validate_audio(filename=filename, content_type=content_type, file_size=file_size)
    return "audio"


def save_uploaded_media(file_bytes: bytes, filename: str) -> str:
    """Save an audio OR video upload to a temporary file."""
    if not filename:
        raise ValueError("Invalid media filename.")

    original_name = Path(filename)
    if original_name.name != filename or original_name.name in {".", ".."}:
        raise ValueError("Invalid media filename.")

    extension = original_name.suffix.lower()
    allowed = set(SUPPORTED_AUDIO_TYPES.values()) | set(SUPPORTED_VIDEO_TYPES.values())
    if extension not in allowed:
        raise ValueError("Unsupported media format.")

    if not file_bytes:
        raise ValueError("Media file is empty.")

    with NamedTemporaryFile(delete=False, suffix=extension) as temp_file:
        temp_file.write(file_bytes)
        return temp_file.name


def extract_audio_track(media_path: str) -> str:
    """
    Extract the audio track from a video and convert it to
    16 kHz mono WAV using ffmpeg.
    """
    import shutil
    import subprocess

    ffmpeg = shutil.which("ffmpeg")

    if not ffmpeg:
        raise RuntimeError(
            "FFmpeg is required to process video recordings but was not found."
        )

    with NamedTemporaryFile(delete=False, suffix=".wav") as temp_file:
        wav_path = temp_file.name

    command = [
        ffmpeg,
        "-y",
        "-loglevel", "error",
        "-i", media_path,
        "-vn",
        "-ac", "1",
        "-ar", "16000",
        "-f", "wav",
        wav_path,
    ]

    try:
        result = subprocess.run(
            command,
            check=True,
            timeout=120,
            capture_output=True,
            text=True,
        )

        if not os.path.exists(wav_path):
            raise RuntimeError("FFmpeg did not create the extracted audio file.")

        wav_size = os.path.getsize(wav_path)

        if wav_size <= 44:
            raise RuntimeError("FFmpeg extracted an empty audio track.")

        print(
            f"[video-audio] extracted WAV: "
            f"{wav_size} bytes from {media_path}"
        )

        return wav_path

    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").strip()

        try:
            if os.path.exists(wav_path):
                os.remove(wav_path)
        except OSError:
            pass

        raise RuntimeError(
            f"FFmpeg could not extract the audio track: {stderr or 'unknown FFmpeg error'}"
        ) from exc

    except Exception:
        try:
            if os.path.exists(wav_path):
                os.remove(wav_path)
        except OSError:
            pass
        raise
    """
    Extract the audio track of a video (or re-encode odd audio) to a
    16 kHz mono WAV using ffmpeg.  Returns the new temporary path.

    Falls back to the original path if ffmpeg is unavailable — Whisper
    and librosa can often decode the container directly.
    """
    import shutil
    import subprocess

    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return media_path

    with NamedTemporaryFile(delete=False, suffix=".wav") as temp_file:
        wav_path = temp_file.name

    command = [
        ffmpeg, "-y", "-loglevel", "error",
        "-i", media_path,
        "-vn", "-ac", "1", "-ar", "16000", "-f", "wav",
        wav_path,
    ]
    try:
        subprocess.run(command, check=True, timeout=120, capture_output=True)
        if os.path.getsize(wav_path) > 44:
            return wav_path
    except Exception:
        pass

    cleanup_audio(wav_path)
    return media_path


def _calculate_rms(samples) -> float:
    if len(samples) == 0:
        return 0.0

    squared = samples.astype("float64") ** 2
    return float(math.sqrt(squared.mean()))


def _calculate_zero_crossing_rate(samples) -> float:
    if len(samples) < 2:
        return 0.0

    zero_crossings = ((samples[:-1] * samples[1:]) < 0).sum()
    return float(zero_crossings / (len(samples) - 1))


def _calculate_pitch_variability(samples, sample_rate: int) -> float:
    try:
        import librosa
    except ImportError:
        return 0.0

    try:
        pitches, magnitudes = librosa.piptrack(
            y=samples.astype("float32"),
            sr=sample_rate,
        )

        pitch_values = []

        for frame in range(pitches.shape[1]):
            index = magnitudes[:, frame].argmax()
            pitch = pitches[index, frame]
            if pitch > 0:
                pitch_values.append(float(pitch))

        if len(pitch_values) < 2:
            return 0.0

        import numpy as np
        return float(np.std(pitch_values))

    except Exception:
        return 0.0


def extract_acoustic_features(audio_path: str) -> Dict[str, Any]:
    try:
        import librosa
    except ImportError:
        return {
            "available": False,
            "error": "librosa is not installed.",
        }

    try:
        samples, sample_rate = librosa.load(
            audio_path,
            sr=None,
            mono=True,
        )

        duration = (
            float(len(samples) / sample_rate)
            if sample_rate
            else 0.0
        )

        return {
            "available": True,
            "duration": round(duration, 2),
            "sample_rate": int(sample_rate),
            "rms": round(_calculate_rms(samples), 5),
            "zero_crossing_rate": round(
                _calculate_zero_crossing_rate(samples), 5
            ),
            "pitch_variability": round(
                _calculate_pitch_variability(samples, sample_rate), 2
            ),
        }

    except Exception as exc:
        return {
            "available": False,
            "error": str(exc),
        }



def save_uploaded_audio(
    file_bytes: bytes,
    filename: str,
) -> str:
    """Save uploaded audio to a temporary file safely."""

    if not filename:
        raise ValueError("Invalid audio filename.")

    original_name = Path(filename)

    if (
        original_name.name != filename
        or original_name.name in {".", ".."}
    ):
        raise ValueError("Invalid audio filename.")

    extension = original_name.suffix.lower()

    supported_extensions = set(SUPPORTED_AUDIO_TYPES.values())

    if extension not in supported_extensions:
        raise ValueError("Unsupported audio format.")

    if not file_bytes:
        raise ValueError("Audio file is empty.")

    with NamedTemporaryFile(
        delete=False,
        suffix=extension,
    ) as temp_file:
        temp_file.write(file_bytes)
        return temp_file.name

def cleanup_audio(audio_path: Optional[str]) -> None:
    if not audio_path:
        return

    try:
        if os.path.exists(audio_path):
            os.remove(audio_path)
    except OSError:
        pass
