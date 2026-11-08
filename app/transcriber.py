"""Audio extraction (ffmpeg) and speech-to-text (faster-whisper, local)."""

from __future__ import annotations

import shutil
import subprocess
import threading
from pathlib import Path

from app.config import settings

_model = None
_model_lock = threading.Lock()


class TranscriptionError(RuntimeError):
    pass


def extract_audio(media_path: Path) -> Path:
    """Convert any audio/video file to 16 kHz mono WAV for Whisper."""
    if shutil.which("ffmpeg") is None:
        raise TranscriptionError("ffmpeg est introuvable sur le serveur.")
    out = media_path.with_suffix(".16k.wav")
    proc = subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", str(media_path),
         "-vn", "-ac", "1", "-ar", "16000", str(out)],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0 or not out.exists():
        raise TranscriptionError(f"Extraction audio impossible : {proc.stderr.strip()[:300]}")
    return out


def probe_duration(media_path: Path) -> float | None:
    if shutil.which("ffprobe") is None:
        return None
    proc = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(media_path)],
        capture_output=True,
        text=True,
    )
    try:
        return round(float(proc.stdout.strip()), 2)
    except ValueError:
        return None


def _get_model():
    global _model
    with _model_lock:
        if _model is None:
            try:
                from faster_whisper import WhisperModel
            except ImportError as exc:  # pragma: no cover - depends on environment
                raise TranscriptionError(
                    "faster-whisper n'est pas installé (pip install -r requirements.txt)."
                ) from exc
            try:
                _model = WhisperModel(
                    settings.whisper_model,
                    device=settings.whisper_device,
                    compute_type=settings.whisper_compute_type,
                )
            except Exception as exc:  # download or load failure
                raise TranscriptionError(
                    f"Chargement du modèle Whisper « {settings.whisper_model} » impossible "
                    f"(premier lancement : téléchargement depuis huggingface.co) : {exc}"
                ) from exc
    return _model


def transcribe(audio_path: Path) -> tuple[list[dict], str | None]:
    """Return (segments, detected_language). Each segment: start, end, text."""
    model = _get_model()
    segments, info = model.transcribe(
        str(audio_path),
        language=settings.whisper_language,
        vad_filter=True,
    )
    result = [
        {"start": round(s.start, 2), "end": round(s.end, 2), "text": s.text.strip()}
        for s in segments
        if s.text.strip()
    ]
    return result, getattr(info, "language", None)
