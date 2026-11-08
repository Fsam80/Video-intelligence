"""Test de bout en bout contre une instance lancée (http://127.0.0.1:8000).

Usage :
    python scripts/e2e_check.py url <lien>
    python scripts/e2e_check.py file <chemin>
Affiche statut, durées, transcription et analyse. Code retour 0 si "done".
"""

import json
import sys
import time

import httpx

BASE = "http://127.0.0.1:8000"
TIMEOUT_S = 1500


def main() -> int:
    mode, target = sys.argv[1], sys.argv[2]
    t0 = time.time()
    with httpx.Client(base_url=BASE, timeout=120) as c:
        if mode == "url":
            r = c.post("/v1/jobs", json={"url": target})
        else:
            with open(target, "rb") as fh:
                r = c.post("/v1/jobs/upload", files={"file": (target.split("/")[-1], fh)})
        print("Soumission :", r.status_code, r.text[:300])
        if r.status_code != 202:
            return 1
        job_id = r.json()["id"]
        last = None
        while time.time() - t0 < TIMEOUT_S:
            job = c.get(f"/v1/jobs/{job_id}").json()
            if job["status"] != last:
                print(f"[{time.time() - t0:6.1f}s] statut = {job['status']}")
                last = job["status"]
            if job["status"] in ("done", "error"):
                break
            time.sleep(3)
        print("\n=== JOB ===\n" + json.dumps(job, ensure_ascii=False, indent=2))
        t = c.get(f"/v1/jobs/{job_id}/transcript")
        if t.status_code == 200:
            tr = t.json()
            print(f"\n=== TRANSCRIPTION ({tr['language']}, {len(tr['segments'])} segments) ===")
            print(tr["text"][:2000])
        a = c.get(f"/v1/jobs/{job_id}/analysis")
        if a.status_code == 200:
            print("\n=== ANALYSE ===\n" + json.dumps(a.json(), ensure_ascii=False, indent=2))
        md = c.get(f"/v1/jobs/{job_id}/export")
        with open(f"data/export-{mode}.md", "w", encoding="utf-8") as fh:
            fh.write(md.text)
        print(f"\nDurée totale : {time.time() - t0:.1f}s")
        return 0 if job["status"] == "done" else 1


if __name__ == "__main__":
    sys.exit(main())
