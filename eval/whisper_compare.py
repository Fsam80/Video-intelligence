"""Comparaison de transcription : Whisper small (actuel) vs large-v3-turbo.

Télécharge l'audio des vidéos arabe classique et darija retenues à l'étape 1
et les transcrit avec chaque modèle (même audio, mêmes paramètres).
"""

import json
import os
import time
from pathlib import Path

import yt_dlp
from faster_whisper import WhisperModel

from app.transcriber import extract_audio, load_wav

OUT = Path("eval/out")
MODELS = ["small", "large-v3-turbo"]


def main() -> None:
    rob = json.loads((OUT / "robustness.json").read_text())
    media = OUT / "media"
    media.mkdir(exist_ok=True)
    audios = {}
    for cat in ("arabe_classique", "darija_algerienne"):
        url = rob.get(cat, {}).get("url")
        if not url:
            continue
        with yt_dlp.YoutubeDL({"quiet": True, "format": "bestaudio/best",
                               "outtmpl": str(media / f"{cat}.%(ext)s")}) as y:
            y.extract_info(url, download=True)
        f = next(media.glob(f"{cat}.*"))
        audios[cat] = load_wav(extract_audio(f))
    results = {}
    for m in MODELS:
        model = WhisperModel(m, device="cpu", compute_type="int8")
        for cat, audio in audios.items():
            t0 = time.time()
            segs, info = model.transcribe(audio, vad_filter=True)
            text = " ".join(s.text.strip() for s in segs)
            results.setdefault(cat, {})[m] = {
                "langue": info.language, "proba_langue": round(info.language_probability, 3),
                "secondes": round(time.time() - t0, 1), "texte": text}
            print(cat, m, results[cat][m]["langue"], results[cat][m]["secondes"], flush=True)
    (OUT / "whisper_compare.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    md = ["\n# Comparaison de transcription (même audio)\n"]
    for cat, by in results.items():
        md.append(f"## {cat}\n")
        for m, r in by.items():
            md.append(f"### {m} — langue {r['langue']} (p={r['proba_langue']}), {r['secondes']} s\n\n```\n{r['texte'][:4000]}\n```\n")
    s = os.environ.get("GITHUB_STEP_SUMMARY")
    if s:
        with open(s, "a", encoding="utf-8") as fh:
            fh.write("\n".join(md))


if __name__ == "__main__":
    main()
