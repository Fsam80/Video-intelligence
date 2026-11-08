"""Job pipeline: fetch -> extract audio -> transcribe -> analyze -> store.

Jobs run one at a time in a background worker thread (Whisper and a local LLM
are both CPU/RAM heavy, so parallelism would only slow things down).
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from app import db
from app.analyzer import AnalysisError, analyze_transcript
from app.config import settings
from app.fetch_client import FetchError, fetch_media
from app.transcriber import TranscriptionError, extract_audio, probe_duration, transcribe

log = logging.getLogger("video_intelligence.pipeline")
_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="vi-worker")


def submit(job_id: str, media_path: Path | None = None) -> None:
    _executor.submit(run_job, job_id, media_path)


def submit_analysis(job_id: str) -> None:
    _executor.submit(run_analysis, job_id)


def _cleanup(*paths: Path | None) -> None:
    if settings.keep_media:
        return
    for p in paths:
        if p is not None:
            p.unlink(missing_ok=True)


def run_job(job_id: str, media_path: Path | None = None) -> None:
    job = db.get_job(job_id)
    if job is None:
        return
    audio: Path | None = None
    try:
        if media_path is None:
            db.update_job(job_id, status="fetching")
            media_path, meta = fetch_media(job["source"], settings.media_dir)
            db.update_job(
                job_id,
                title=meta.get("title"),
                author=meta.get("author"),
                duration_s=meta.get("duration"),
            )
        else:
            duration = probe_duration(media_path)
            if duration:
                db.update_job(job_id, duration_s=duration)

        db.update_job(job_id, status="transcribing")
        audio = extract_audio(media_path)
        segments, language = transcribe(audio)
        db.save_transcript(job_id, segments, language)
    except (FetchError, TranscriptionError) as exc:
        db.update_job(job_id, status="error", error=str(exc))
        _cleanup(media_path, audio)
        return
    except Exception as exc:  # noqa: BLE001 - surface any unexpected failure to the user
        log.exception("Job %s failed", job_id)
        db.update_job(job_id, status="error", error=f"Erreur inattendue : {exc}")
        _cleanup(media_path, audio)
        return

    _cleanup(media_path, audio)
    run_analysis(job_id)


def run_analysis(job_id: str) -> None:
    """Analyze an existing transcript. A failure here keeps the transcript."""
    job = db.get_job(job_id)
    transcript = db.get_transcript(job_id)
    if job is None or transcript is None:
        return
    if not transcript["text"].strip():
        db.update_job(
            job_id,
            status="done",
            error="Aucune parole détectée dans cette vidéo : rien à analyser.",
        )
        return
    db.update_job(job_id, status="analyzing", error=None)
    try:
        result = analyze_transcript(transcript["text"], job.get("title"))
        db.save_analysis(job_id, settings.llm_model, result)
        db.update_job(job_id, status="done")
    except AnalysisError as exc:
        db.update_job(
            job_id,
            status="error",
            error=f"Transcription OK, analyse échouée : {exc} (relance via « Ré-analyser »).",
        )
    except Exception as exc:  # noqa: BLE001
        log.exception("Analysis %s failed", job_id)
        db.update_job(job_id, status="error", error=f"Analyse : erreur inattendue : {exc}")
