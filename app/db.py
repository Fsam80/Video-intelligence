"""SQLite persistence (standard library only).

Tables:
- jobs: one row per processed video (status, source, metadata)
- segments: transcript segments with timestamps
- analyses: structured LLM analysis stored as JSON
- segments_fts: full-text index used by the library search
"""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

_lock = threading.Lock()
_db_path: Path | None = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    source_type TEXT NOT NULL,          -- url | upload
    source TEXT NOT NULL,               -- URL or original filename
    platform TEXT,
    status TEXT NOT NULL,               -- queued | fetching | transcribing | analyzing | done | error
    error TEXT,
    title TEXT,
    author TEXT,
    duration_s REAL,
    language TEXT,
    transcript_text TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS segments (
    job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    idx INTEGER NOT NULL,
    start_s REAL NOT NULL,
    end_s REAL NOT NULL,
    text TEXT NOT NULL,
    PRIMARY KEY (job_id, idx)
);
CREATE TABLE IF NOT EXISTS analyses (
    job_id TEXT PRIMARY KEY REFERENCES jobs(id) ON DELETE CASCADE,
    model TEXT,
    data TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE VIRTUAL TABLE IF NOT EXISTS segments_fts USING fts5(
    job_id UNINDEXED, idx UNINDEXED, text, tokenize='unicode61 remove_diacritics 2'
);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def init(db_path: Path) -> None:
    global _db_path
    db_path.parent.mkdir(parents=True, exist_ok=True)
    _db_path = db_path
    with connect() as conn:
        conn.executescript(SCHEMA)


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    if _db_path is None:
        raise RuntimeError("Database not initialised")
    with _lock:
        conn = sqlite3.connect(_db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()


def create_job(source_type: str, source: str, platform: str | None) -> str:
    job_id = uuid.uuid4().hex[:12]
    ts = now()
    with connect() as conn:
        conn.execute(
            "INSERT INTO jobs (id, source_type, source, platform, status, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, 'queued', ?, ?)",
            (job_id, source_type, source, platform, ts, ts),
        )
    return job_id


def update_job(job_id: str, **fields: Any) -> None:
    if not fields:
        return
    fields["updated_at"] = now()
    cols = ", ".join(f"{k} = ?" for k in fields)
    with connect() as conn:
        conn.execute(f"UPDATE jobs SET {cols} WHERE id = ?", (*fields.values(), job_id))


def get_job(job_id: str) -> dict | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if row is None:
            return None
        job = dict(row)
        job["has_analysis"] = (
            conn.execute("SELECT 1 FROM analyses WHERE job_id = ?", (job_id,)).fetchone()
            is not None
        )
    job.pop("transcript_text", None)
    return job


def list_jobs(limit: int = 100) -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT j.*, (a.job_id IS NOT NULL) AS has_analysis FROM jobs j"
            " LEFT JOIN analyses a ON a.job_id = j.id ORDER BY j.created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d.pop("transcript_text", None)
        d["has_analysis"] = bool(d["has_analysis"])
        out.append(d)
    return out


def delete_job(job_id: str) -> bool:
    with connect() as conn:
        conn.execute("DELETE FROM segments_fts WHERE job_id = ?", (job_id,))
        cur = conn.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
        return cur.rowcount > 0


def save_transcript(job_id: str, segments: list[dict], language: str | None) -> None:
    text = " ".join(s["text"].strip() for s in segments).strip()
    with connect() as conn:
        conn.execute("DELETE FROM segments WHERE job_id = ?", (job_id,))
        conn.execute("DELETE FROM segments_fts WHERE job_id = ?", (job_id,))
        for i, s in enumerate(segments):
            conn.execute(
                "INSERT INTO segments (job_id, idx, start_s, end_s, text) VALUES (?, ?, ?, ?, ?)",
                (job_id, i, float(s["start"]), float(s["end"]), s["text"].strip()),
            )
            conn.execute(
                "INSERT INTO segments_fts (job_id, idx, text) VALUES (?, ?, ?)",
                (job_id, i, s["text"].strip()),
            )
        conn.execute(
            "UPDATE jobs SET transcript_text = ?, language = COALESCE(?, language), updated_at = ?"
            " WHERE id = ?",
            (text, language, now(), job_id),
        )


def get_transcript(job_id: str) -> dict | None:
    with connect() as conn:
        job = conn.execute(
            "SELECT transcript_text, language FROM jobs WHERE id = ?", (job_id,)
        ).fetchone()
        if job is None or job["transcript_text"] is None:
            return None
        segs = conn.execute(
            "SELECT start_s, end_s, text FROM segments WHERE job_id = ? ORDER BY idx", (job_id,)
        ).fetchall()
    return {
        "language": job["language"],
        "text": job["transcript_text"],
        "segments": [{"start": s["start_s"], "end": s["end_s"], "text": s["text"]} for s in segs],
    }


def save_analysis(job_id: str, model: str, data: dict) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO analyses (job_id, model, data, created_at) VALUES (?, ?, ?, ?)",
            (job_id, model, json.dumps(data, ensure_ascii=False), now()),
        )


def get_analysis(job_id: str) -> dict | None:
    with connect() as conn:
        row = conn.execute(
            "SELECT model, data, created_at FROM analyses WHERE job_id = ?", (job_id,)
        ).fetchone()
    if row is None:
        return None
    return {"model": row["model"], "created_at": row["created_at"], **json.loads(row["data"])}


def _fts_query(q: str) -> str:
    # Quote each word so user input cannot break FTS syntax; prefix match on each term.
    terms = [t.replace('"', "") for t in q.split() if t.strip()]
    return " ".join(f'"{t}"*' for t in terms if t)


def search(q: str, limit: int = 50) -> list[dict]:
    fts = _fts_query(q)
    if not fts:
        return []
    with connect() as conn:
        rows = conn.execute(
            "SELECT f.job_id, f.idx, snippet(segments_fts, 2, '[', ']', '…', 12) AS snippet,"
            " s.start_s, j.title, j.source FROM segments_fts f"
            " JOIN segments s ON s.job_id = f.job_id AND s.idx = f.idx"
            " JOIN jobs j ON j.id = f.job_id"
            " WHERE segments_fts MATCH ? ORDER BY rank LIMIT ?",
            (fts, limit),
        ).fetchall()
    return [
        {
            "job_id": r["job_id"],
            "start": r["start_s"],
            "snippet": r["snippet"],
            "title": r["title"] or r["source"],
        }
        for r in rows
    ]
