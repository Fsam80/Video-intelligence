from __future__ import annotations

import re
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse, PlainTextResponse

from app import db, pipeline
from app.analyzer import AnalysisError, compare_analyses
from app.config import settings
from app.platforms import ENABLED, detect_platform
from app.schemas import (
    CompareRequest,
    CreateJobRequest,
    HealthResponse,
    Job,
    SearchHit,
    Transcript,
)

STATIC_DIR = Path(__file__).parent / "static"
ALLOWED_EXT = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v",
               ".mp3", ".m4a", ".wav", ".ogg", ".opus", ".aac", ".flac"}


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings.media_dir.mkdir(parents=True, exist_ok=True)
    db.init(settings.db_path)
    yield


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Transforme des vidéos (TikTok, YouTube, fichiers) en connaissances structurées.",
    lifespan=lifespan,
)


def _job_or_404(job_id: str) -> dict:
    job = db.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Vidéo introuvable.")
    return job


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health", response_model=HealthResponse, tags=["system"])
def health() -> HealthResponse:
    return HealthResponse(status="ok", app=settings.app_name, version=settings.app_version)


@app.post("/v1/jobs", response_model=Job, status_code=status.HTTP_202_ACCEPTED, tags=["jobs"])
def create_job(request: CreateJobRequest) -> dict:
    url = str(request.url)
    platform = detect_platform(url)
    if platform is None:
        raise HTTPException(status_code=422, detail="Plateforme non reconnue.")
    if platform not in ENABLED:
        raise HTTPException(
            status_code=422,
            detail=f"{platform} n'est pas encore pris en charge. Utilise l'import de fichier.",
        )
    job_id = db.create_job("url", url, platform)
    pipeline.submit(job_id)
    return db.get_job(job_id)


@app.post("/v1/jobs/upload", response_model=Job, status_code=status.HTTP_202_ACCEPTED, tags=["jobs"])
async def upload_job(file: UploadFile = File(...)) -> dict:
    name = file.filename or "fichier"
    ext = Path(name).suffix.lower()
    if ext not in ALLOWED_EXT:
        raise HTTPException(status_code=415, detail=f"Format non pris en charge : {ext or '?'}")
    settings.media_dir.mkdir(parents=True, exist_ok=True)
    dest = settings.media_dir / f"upload-{uuid.uuid4().hex[:10]}{ext}"
    limit = settings.max_upload_mb * 1024 * 1024
    size = 0
    with dest.open("wb") as fh:
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            if size > limit:
                fh.close()
                dest.unlink(missing_ok=True)
                raise HTTPException(status_code=413, detail=f"Fichier > {settings.max_upload_mb} Mo.")
            fh.write(chunk)
    job_id = db.create_job("upload", name, "upload")
    db.update_job(job_id, title=Path(name).stem)
    pipeline.submit(job_id, dest)
    return db.get_job(job_id)


@app.get("/v1/jobs", response_model=list[Job], tags=["jobs"])
def list_jobs(limit: int = Query(100, ge=1, le=500)) -> list[dict]:
    return db.list_jobs(limit)


@app.get("/v1/jobs/{job_id}", response_model=Job, tags=["jobs"])
def get_job(job_id: str) -> dict:
    return _job_or_404(job_id)


@app.delete("/v1/jobs/{job_id}", status_code=204, tags=["jobs"])
def delete_job(job_id: str) -> None:
    if not db.delete_job(job_id):
        raise HTTPException(status_code=404, detail="Vidéo introuvable.")


@app.get("/v1/jobs/{job_id}/transcript", response_model=Transcript, tags=["results"])
def get_transcript(job_id: str) -> dict:
    _job_or_404(job_id)
    t = db.get_transcript(job_id)
    if t is None:
        raise HTTPException(status_code=409, detail="Transcription pas encore disponible.")
    return t


@app.get("/v1/jobs/{job_id}/analysis", tags=["results"])
def get_analysis(job_id: str) -> dict:
    _job_or_404(job_id)
    a = db.get_analysis(job_id)
    if a is None:
        raise HTTPException(status_code=409, detail="Analyse pas encore disponible.")
    return a


@app.post("/v1/jobs/{job_id}/analyze", response_model=Job, status_code=202, tags=["results"])
def reanalyze(job_id: str) -> dict:
    _job_or_404(job_id)
    if db.get_transcript(job_id) is None:
        raise HTTPException(status_code=409, detail="Pas de transcription à analyser.")
    db.update_job(job_id, status="queued", error=None)
    pipeline.submit_analysis(job_id)
    return db.get_job(job_id)


@app.get("/v1/search", response_model=list[SearchHit], tags=["library"])
def search(q: str = Query(..., min_length=2), limit: int = Query(50, ge=1, le=200)) -> list[dict]:
    return db.search(q, limit)


@app.post("/v1/compare", tags=["library"])
def compare(req: CompareRequest) -> dict:
    items = []
    for jid in req.job_ids:
        job = _job_or_404(jid)
        analysis = db.get_analysis(jid)
        if analysis is None:
            raise HTTPException(status_code=409, detail=f"Vidéo {jid} pas encore analysée.")
        items.append({"job_id": jid, "title": job.get("title"), "analysis": analysis})
    try:
        return compare_analyses(items)
    except AnalysisError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


def _ts(seconds: float) -> str:
    s = int(seconds)
    return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"


def _md_list(items: list[str]) -> str:
    return "\n".join(f"- {i}" for i in items) if items else "_(aucun)_"


@app.get("/v1/jobs/{job_id}/export", response_class=PlainTextResponse, tags=["results"])
def export_markdown(job_id: str) -> PlainTextResponse:
    job = _job_or_404(job_id)
    t = db.get_transcript(job_id)
    a = db.get_analysis(job_id)
    title = job.get("title") or job["source"]
    parts = [f"# {title}", "", f"- Source : {job['source']}", f"- Plateforme : {job.get('platform')}"]
    if job.get("author"):
        parts.append(f"- Auteur : {job['author']}")
    if a:
        parts += [
            "", "## Résumé", a.get("summary", ""),
            "", "## Idées clés", _md_list(a.get("key_ideas", [])),
            "", "## Faits", _md_list(a.get("facts", [])),
            "", "## Opinions", _md_list(a.get("opinions", [])),
            "", "## À vérifier", _md_list(a.get("claims_to_verify", [])),
            "", "## Personnes et entités", _md_list(a.get("people_and_entities", [])),
            "", "## Analyse critique", a.get("critical_analysis", ""),
            "", f"_Analyse générée par {a.get('model')} — à relire._",
        ]
    if t:
        parts += ["", "## Transcription"]
        parts += [f"[{_ts(s['start'])}] {s['text']}" for s in t["segments"]]
    slug = re.sub(r"[^A-Za-z0-9_-]+", "-", title)[:60].strip("-") or job_id
    return PlainTextResponse(
        "\n".join(parts) + "\n",
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{slug}.md"'},
    )
