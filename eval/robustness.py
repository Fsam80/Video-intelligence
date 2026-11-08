"""Étape 1 — robustesse : 3 vidéos (arabe classique, darija, > 5 min).

Pour chaque catégorie, essaie les candidats dans l'ordre : sonde la durée
(yt-dlp, sans téléchargement), soumet le premier valide à l'application et
passe au suivant si la récupération échoue ou si aucune parole n'est détectée.
Un candidat « upload:<url> » est téléchargé puis importé comme fichier
(repli quand les plateformes bloquent les serveurs de GitHub).
"""

import json
import os
import time
from pathlib import Path

import httpx
import yt_dlp

BASE = "http://127.0.0.1:8000"
OUT = Path("eval/out")
MEDIA = OUT / "media"
MEDIA.mkdir(parents=True, exist_ok=True)
RULES = {
    "arabe_classique": (20, 900),
    "darija_algerienne": (20, 900),
    "longue_plus_5_min": (300, 1800),
}


def probe(url: str) -> dict:
    try:
        with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True, "skip_download": True}) as y:
            info = y.extract_info(url, download=False)
        return {"duration": info.get("duration")}
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc).split(";")[0][:160]}


def submit(c: httpx.Client, cand: str, cat: str) -> httpx.Response:
    if cand.startswith("upload:"):
        url = cand[len("upload:"):]
        dest = MEDIA / f"{cat}{Path(url).suffix or '.mp3'}"
        with httpx.stream("GET", url, follow_redirects=True, timeout=300) as r:
            r.raise_for_status()
            with dest.open("wb") as fh:
                for chunk in r.iter_bytes():
                    fh.write(chunk)
        with dest.open("rb") as fh:
            return c.post("/v1/jobs/upload", files={"file": (dest.name, fh)})
    return c.post("/v1/jobs", json={"url": cand})


def run_job(cand: str, cat: str) -> dict:
    t0 = time.time()
    marks: dict[str, float] = {}
    with httpx.Client(base_url=BASE, timeout=600) as c:
        r = submit(c, cand, cat)
        if r.status_code != 202:
            return {"submit_error": r.text[:300]}
        jid = r.json()["id"]
        marks["queued"] = 0.0
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
    end = marks.get("done", marks.get("error", total))
    t_tr_start = marks.get("transcribing")
    t_an_start = marks.get("analyzing")
    return {
        "job": job,
        "timings_s": {
            "recuperation_ou_import": round((t_tr_start or end) - marks.get("fetching", 0), 1),
            "transcription": round((t_an_start or end) - t_tr_start, 1) if t_tr_start is not None else None,
            "analyse": round(end - t_an_start, 1) if t_an_start is not None else None,
            "total": total,
        },
        "transcript": tr.json() if tr.status_code == 200 else None,
        "analysis": an.json() if an.status_code == 200 else None,
    }


def usable(res: dict) -> bool:
    t = res.get("transcript")
    return bool(t and t["text"].strip())


def main() -> None:
    videos = json.loads(Path("eval/videos.json").read_text())
    results = {}
    for cat, cands in videos.items():
        lo, hi = RULES[cat]
        attempts = []
        chosen = None
        for cand in cands:
            if not cand.startswith("upload:"):
                p = probe(cand)
                d = p.get("duration")
                if not d or not (lo <= d <= hi):
                    attempts.append({"candidat": cand, "sonde": p, "retenu": False})
                    continue
            try:
                res = run_job(cand, cat)
            except Exception as exc:  # noqa: BLE001
                res = {"submit_error": f"{exc.__class__.__name__}: {exc}"[:300]}
            ok = usable(res) and (not cand.startswith("upload:") or (res["job"].get("duration_s") or 0) >= lo)
            attempts.append({"candidat": cand, "statut": res.get("job", {}).get("status"),
                             "erreur": res.get("job", {}).get("error") or res.get("submit_error"),
                             "retenu": ok})
            if ok:
                chosen = {"candidat": cand, **res}
                break
        results[cat] = {"tentatives": attempts, "resultat": chosen}
        if chosen:
            (OUT / f"{cat}.txt").write_text(chosen["transcript"]["text"], encoding="utf-8")
            (OUT / f"{cat}.source").write_text(chosen["candidat"], encoding="utf-8")
        print(cat, json.dumps(attempts, ensure_ascii=False)[:2000], flush=True)
    (OUT / "robustness.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    md = ["# Étape 1 — Robustesse\n"]
    for cat, r in results.items():
        md.append(f"## {cat}\n")
        md.append("Tentatives :\n" + "\n".join(f"- {json.dumps(a, ensure_ascii=False)}" for a in r["tentatives"]) + "\n")
        ch = r["resultat"]
        if not ch:
            md.append("**Aucun candidat exploitable.**\n")
            continue
        j = ch["job"]
        md.append(f"- Source : {ch['candidat']}\n- Titre : {j.get('title')}\n- Durée : {j.get('duration_s')} s"
                  f"\n- Statut : {j.get('status')} — message : {j.get('error')}\n- Langue détectée : {j.get('language')}"
                  f"\n- Segments : {len(ch['transcript']['segments'])}\n- Temps (s) : {ch['timings_s']}\n")
        md.append("### Transcription (Whisper small)\n\n```\n" + ch["transcript"]["text"][:8000] + "\n```\n")
        if ch.get("analysis"):
            md.append("### Analyse (Qwen 2.5 7B)\n\n```json\n" + json.dumps(ch["analysis"], ensure_ascii=False, indent=1)[:8000] + "\n```\n")
    s = os.environ.get("GITHUB_STEP_SUMMARY")
    if s:
        with open(s, "a", encoding="utf-8") as fh:
            fh.write("\n".join(md))


if __name__ == "__main__":
    main()
