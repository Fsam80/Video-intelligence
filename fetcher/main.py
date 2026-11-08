"""Fetcher service — downloads the audio of a public video with yt-dlp.

Runs as its own process (port 8001 by default). The analysis app only calls
its HTTP API, so the scraping part can be replaced, updated or hosted
elsewhere without touching the analysis code.

Endpoints:
    POST   /fetch            {"url": "..."} -> {"file_id", "ext", "title", ...}
    GET    /files/{file_id}  -> the audio file
    DELETE /files/{file_id}  -> remove it
"""

from __future__ import annotations

import os
import re
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, HttpUrl

from app.platforms import ENABLED, detect_platform

FETCH_DIR = Path(os.getenv("FETCHER_DIR", "data/fetcher"))
MAX_DURATION_S = int(os.getenv("FETCHER_MAX_DURATION_S", "7200"))
COOKIES_FILE = os.getenv("FETCHER_COOKIES_FILE")  # optional, Netscape format
_ID_RE = re.compile(r"^[a-f0-9]{16}$")

app = FastAPI(title="Video Intelligence — Fetcher", version="0.2.0")


class FetchRequest(BaseModel):
    url: HttpUrl


@app.get("/health")
def health() -> dict:
    try:
        import yt_dlp  # noqa: F401

        ytdlp = yt_dlp.version.__version__
    except ImportError:
        ytdlp = None
    return {"status": "ok", "yt_dlp": ytdlp, "platforms": sorted(ENABLED)}


@app.post("/fetch")
def fetch(req: FetchRequest) -> dict:
    url = str(req.url)
    platform = detect_platform(url)
    if platform not in ENABLED:
        raise HTTPException(status_code=422, detail=f"Plateforme non prise en charge : {platform}")
    try:
        import yt_dlp
    except ImportError as exc:
        raise HTTPException(status_code=500, detail="yt-dlp n'est pas installé.") from exc

    FETCH_DIR.mkdir(parents=True, exist_ok=True)
    file_id = uuid.uuid4().hex[:16]
    opts = {
        "format": "bestaudio/best",
        "outtmpl": str(FETCH_DIR / f"{file_id}.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "socket_timeout": 30,
        "retries": 3,
        "match_filter": yt_dlp.utils.match_filter_func(f"duration <=? {MAX_DURATION_S}"),
    }
    if COOKIES_FILE:
        opts["cookiefile"] = COOKIES_FILE
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
    except Exception as exc:  # yt-dlp raises many error types
        msg = str(exc).replace("\x1b", "")
        raise HTTPException(
            status_code=502,
            detail=f"Échec de récupération ({platform}) : {msg[:300]}. "
            "Solution de repli : télécharge la vidéo et importe le fichier.",
        ) from exc

    if info is None:
        raise HTTPException(status_code=422, detail="Vidéo trop longue ou indisponible.")
    files = list(FETCH_DIR.glob(f"{file_id}.*"))
    if not files:
        raise HTTPException(status_code=502, detail="Aucun fichier téléchargé.")
    path = files[0]
    return {
        "file_id": file_id,
        "ext": path.suffix,
        "platform": platform,
        "title": info.get("title") or info.get("description", "")[:120] or None,
        "author": info.get("uploader") or info.get("channel") or info.get("creator"),
        "duration": info.get("duration"),
        "webpage_url": info.get("webpage_url") or url,
        "upload_date": info.get("upload_date"),
    }


def _path(file_id: str) -> Path:
    if not _ID_RE.match(file_id):
        raise HTTPException(status_code=400, detail="Identifiant invalide.")
    files = list(FETCH_DIR.glob(f"{file_id}.*"))
    if not files:
        raise HTTPException(status_code=404, detail="Fichier introuvable.")
    return files[0]


@app.get("/files/{file_id}")
def get_file(file_id: str) -> FileResponse:
    return FileResponse(_path(file_id))


@app.delete("/files/{file_id}", status_code=204)
def delete_file(file_id: str) -> None:
    _path(file_id).unlink(missing_ok=True)
