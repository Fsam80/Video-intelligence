"""Client for the separate fetcher service (see fetcher/).

The analysis app never scrapes platforms itself: it asks the fetcher for the
media and receives a file plus metadata.
"""

from __future__ import annotations

from pathlib import Path

import httpx

from app.config import settings


class FetchError(RuntimeError):
    pass


def fetch_media(url: str, dest_dir: Path) -> tuple[Path, dict]:
    base = settings.fetcher_url.rstrip("/")
    try:
        resp = httpx.post(f"{base}/fetch", json={"url": url}, timeout=settings.fetcher_timeout_s)
    except httpx.HTTPError as exc:
        raise FetchError(
            f"Service de récupération injoignable ({base}). Lance-le avec scripts/start.sh."
        ) from exc
    if resp.status_code != 200:
        try:
            detail = resp.json().get("detail")
        except ValueError:
            detail = resp.text[:300]
        raise FetchError(f"Récupération impossible : {detail}")
    meta = resp.json()
    file_id = meta["file_id"]

    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{file_id}{meta.get('ext', '')}"
    try:
        with httpx.stream("GET", f"{base}/files/{file_id}", timeout=settings.fetcher_timeout_s) as r:
            if r.status_code != 200:
                raise FetchError(f"Téléchargement du fichier échoué ({r.status_code}).")
            with dest.open("wb") as fh:
                for chunk in r.iter_bytes():
                    fh.write(chunk)
        # Ask the fetcher to free its copy.
        httpx.delete(f"{base}/files/{file_id}", timeout=30)
    except httpx.HTTPError as exc:
        raise FetchError(f"Téléchargement interrompu : {exc}") from exc
    return dest, meta
