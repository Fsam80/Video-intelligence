import time

import pytest
from fastapi.testclient import TestClient

from app import analyzer, pipeline, transcriber
from app.config import settings
from app.main import app

FAKE_SEGMENTS = [
    {"start": 0.0, "end": 4.2, "text": "Le béton fibré réduit la fissuration."},
    {"start": 4.2, "end": 9.0, "text": "Selon moi c'est la meilleure solution du marché."},
]
FAKE_ANALYSIS = {
    "summary": "Vidéo sur le béton fibré.",
    "key_ideas": ["Le béton fibré limite les fissures"],
    "facts": ["Le béton fibré réduit la fissuration"],
    "opinions": ["Meilleure solution du marché"],
    "claims_to_verify": ["« meilleure solution » non sourcé"],
    "people_and_entities": [],
    "critical_analysis": "Affirmation commerciale non étayée.",
    "topics": ["béton", "fissuration"],
}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    monkeypatch.setattr(transcriber, "_get_model", lambda: None)
    monkeypatch.setattr(pipeline, "extract_audio", lambda p: p)
    monkeypatch.setattr(pipeline, "probe_duration", lambda p: 9.0)
    monkeypatch.setattr(pipeline, "transcribe", lambda p: (FAKE_SEGMENTS, "fr"))
    monkeypatch.setattr(analyzer, "_chat", lambda s, u: "```json\n" + __import__("json").dumps(FAKE_ANALYSIS) + "\n```")

    def fake_fetch(url, dest_dir):
        dest_dir.mkdir(parents=True, exist_ok=True)
        f = dest_dir / "x.m4a"
        f.write_bytes(b"audio")
        return f, {"title": "Béton fibré", "author": "@chantier", "duration": 9}

    monkeypatch.setattr(pipeline, "fetch_media", fake_fetch)
    with TestClient(app) as c:
        yield c


def wait_done(client, job_id, timeout=5.0):
    end = time.time() + timeout
    while time.time() < end:
        job = client.get(f"/v1/jobs/{job_id}").json()
        if job["status"] in ("done", "error"):
            return job
        time.sleep(0.05)
    raise AssertionError("job did not finish")
