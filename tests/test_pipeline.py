import pytest

from app.analyzer import AnalysisError, parse_json
from app.platforms import detect_platform
from tests.conftest import wait_done


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://www.tiktok.com/@user/video/123", "tiktok"),
        ("https://vm.tiktok.com/ZMabc/", "tiktok"),
        ("https://youtu.be/abc", "youtube"),
        ("https://www.instagram.com/reel/abc/", "instagram"),
        ("https://example.com/v", None),
        ("https://nottiktok.com/v", None),
    ],
)
def test_detect_platform(url, expected):
    assert detect_platform(url) == expected


def test_url_job_full_flow(client):
    r = client.post("/v1/jobs", json={"url": "https://www.tiktok.com/@u/video/1"})
    assert r.status_code == 202
    job = wait_done(client, r.json()["id"])
    assert job["status"] == "done", job["error"]
    assert job["title"] == "Béton fibré"
    t = client.get(f"/v1/jobs/{job['id']}/transcript").json()
    assert t["language"] == "fr" and len(t["segments"]) == 2
    a = client.get(f"/v1/jobs/{job['id']}/analysis").json()
    assert a["opinions"] == ["Meilleure solution du marché"]
    md = client.get(f"/v1/jobs/{job['id']}/export").text
    assert "## Résumé" in md and "[00:00:04]" in md


def test_unsupported_platform_rejected(client):
    r = client.post("/v1/jobs", json={"url": "https://www.instagram.com/reel/x/"})
    assert r.status_code == 422
    r = client.post("/v1/jobs", json={"url": "https://example.com/x"})
    assert r.status_code == 422


def test_upload_flow_and_search(client):
    r = client.post("/v1/jobs/upload", files={"file": ("cours.mp4", b"data", "video/mp4")})
    assert r.status_code == 202
    job = wait_done(client, r.json()["id"])
    assert job["status"] == "done"
    hits = client.get("/v1/search", params={"q": "fissuration"}).json()
    assert hits and hits[0]["job_id"] == job["id"] and "[" in hits[0]["snippet"]
    # accents ignored
    assert client.get("/v1/search", params={"q": "beton"}).json()
    # FTS syntax characters must not crash
    assert client.get("/v1/search", params={"q": 'béton" OR ('}).status_code == 200


def test_upload_rejects_bad_extension(client):
    r = client.post("/v1/jobs/upload", files={"file": ("x.exe", b"x", "application/octet-stream")})
    assert r.status_code == 415


def test_compare_and_delete(client, monkeypatch):
    ids = []
    for n in range(2):
        r = client.post("/v1/jobs/upload", files={"file": (f"v{n}.mp3", b"a", "audio/mpeg")})
        ids.append(wait_done(client, r.json()["id"])["id"])
    from app import analyzer
    monkeypatch.setattr(analyzer, "_chat", lambda s, u: '{"common_points": ["béton"], "synthesis": "ok"}')
    r = client.post("/v1/compare", json={"job_ids": ids})
    assert r.status_code == 200 and r.json()["common_points"] == ["béton"]
    assert client.delete(f"/v1/jobs/{ids[0]}").status_code == 204
    assert client.get(f"/v1/jobs/{ids[0]}").status_code == 404
    assert all(h["job_id"] != ids[0] for h in client.get("/v1/search", params={"q": "béton"}).json())


def test_analysis_failure_keeps_transcript(client, monkeypatch):
    from app import analyzer

    def boom(s, u):
        raise AnalysisError("LLM injoignable")

    monkeypatch.setattr(analyzer, "_chat", boom)
    r = client.post("/v1/jobs/upload", files={"file": ("a.wav", b"a", "audio/wav")})
    job = wait_done(client, r.json()["id"])
    assert job["status"] == "error" and "Ré-analyser" in job["error"]
    assert client.get(f"/v1/jobs/{job['id']}/transcript").status_code == 200
    monkeypatch.setattr(analyzer, "_chat", lambda s, u: '{"summary": "ok"}')
    client.post(f"/v1/jobs/{job['id']}/analyze")
    assert wait_done(client, job["id"])["status"] == "done"


def test_parse_json_variants():
    assert parse_json('Voici :\n```json\n{"a": 1}\n```') == {"a": 1}
    with pytest.raises(AnalysisError):
        parse_json("pas de json")


def test_video_without_speech_is_done_not_error(client, monkeypatch):
    from app import pipeline

    monkeypatch.setattr(pipeline, "transcribe", lambda p: ([], "en"))
    r = client.post("/v1/jobs/upload", files={"file": ("chien.mp4", b"x", "video/mp4")})
    job = wait_done(client, r.json()["id"])
    assert job["status"] == "done"
    assert "Aucune parole" in job["error"]
    assert job["has_analysis"] is False
