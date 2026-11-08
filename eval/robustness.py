"""Étape 1 — robustesse : 3 vidéos (arabe classique, darija, > 5 min).

Pour chaque catégorie : sonde les candidats (yt-dlp, sans téléchargement),
retient le premier valide, le soumet à l'application (URL réelle) et mesure
chaque étape. Écrit eval/out/robustness.json + transcriptions, et un résumé
Markdown dans $GITHUB_STEP_SUMMARY.
"""

import json
import os
import time
from pathlib import Path

import httpx
import yt_dlp

BASE = "http://127.0.0.1:8000"
OUT = Path("eval/out")
OUT.mkdir(parents=True, exist_ok=True)
RULES = {
    "arabe_classique": (5, 900),
    "darija_algerienne": (5, 900),
    "longue_plus_5_min": (300, 1500),
}


def probe(url: str) -> dict | None:
    try:
        with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True, "skip_download": True}) as y:
            info = y.extract_info(url, download=False)
        return {"duration": info.get("duration"), "title": (info.get("title") or "")[:120]}
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)[:200]}


def run_job(url: str) -> dict:
    t0 = time.time()
    marks: dict[str, float] = {}
    with httpx.Client(base_url=BASE, timeout=120) as c:
        r = c.post("/v1/jobs", json={"url": url})
        if r.status_code != 202:
            return {"submit_error": r.text}
        jid = r.json()["id"]
        last = None
        while time.time() - t0 < 3600:
            job = c.get(f"/v1/jobs/{jid}").json()
            if job["status"] != last:
                marks[job["status"]] = round(time.time() - t0, 1)
                last = job["status"]
            if job["status"] in ("done", "error"):
                break
            time.sleep(2)
        tr = c.get(f"/v1/jobs/{jid}/transcript")
        an = c.get(f"/v1/jobs/{jid}/analysis")
    total = round(time.time() - t0, 1)
    t_fetch = marks.get("transcribing", total) - marks.get("fetching", 0)
    t_trans = marks.get("analyzing", marks.get("done", marks.get("error", total))) - marks.get("transcribing", 0) if "transcribing" in marks else None
    t_anal = (marks.get("done", total) - marks["analyzing"]) if "analyzing" in marks else None
    return {
        "job": job,
        "timings_s": {"recuperation": round(t_fetch, 1), "transcription": t_trans and round(t_trans, 1),
                      "analyse": t_anal and round(t_anal, 1), "total": total},
        "transcript": tr.json() if tr.status_code == 200 else None,
        "analysis": an.json() if an.status_code == 200 else None,
    }


def main() -> None:
    videos = json.loads(Path("eval/videos.json").read_text())
    results = {}
    for cat, urls in videos.items():
        lo, hi = RULES[cat]
        probes = []
        chosen = None
        for u in urls:
            p = probe(u)
            probes.append({"url": u, **(p or {})})
            d = (p or {}).get("duration")
            if d and lo <= d <= hi:
                chosen = u
                break
        res = {"probes": probes, "url": chosen}
        if chosen:
            res.update(run_job(chosen))
            if res.get("transcript"):
                (OUT / f"{cat}.txt").write_text(res["transcript"]["text"], encoding="utf-8")
        results[cat] = res
        print(cat, json.dumps({k: v for k, v in res.items() if k not in ("transcript", "analysis")},
                              ensure_ascii=False)[:1500], flush=True)
    (OUT / "robustness.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    md = ["# Étape 1 — Robustesse\n"]
    for cat, r in results.items():
        md.append(f"## {cat}\n")
        md.append("Candidats sondés : " + "; ".join(
            f"{p['url']} → {p.get('duration') or p.get('error')}" for p in r["probes"]) + "\n")
        if not r.get("url"):
            md.append("**Aucun candidat valide.**\n")
            continue
        j = r.get("job", {})
        md.append(f"- URL : {r['url']}\n- Titre : {j.get('title')}\n- Durée : {j.get('duration_s')} s"
                  f"\n- Statut : {j.get('status')} — erreur : {j.get('error')}\n- Langue détectée : {j.get('language')}"
                  f"\n- Temps (s) : {r.get('timings_s')}\n")
        if r.get("transcript"):
            md.append("### Transcription\n\n```\n" + r["transcript"]["text"][:6000] + "\n```\n")
        if r.get("analysis"):
            md.append("### Analyse\n\n```json\n" + json.dumps(r["analysis"], ensure_ascii=False, indent=1)[:6000] + "\n```\n")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write("\n".join(md))


if __name__ == "__main__":
    main()
