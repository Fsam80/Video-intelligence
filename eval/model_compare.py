"""Étape 2 — comparaison des modèles d'analyse sur la MÊME transcription.

Usage : python eval/model_compare.py <fichier_transcription.txt> <titre>
Modèles : qwen2.5:7b-instruct, qwen2.5:14b-instruct (Ollama local) et, si les
variables EXTERNAL_LLM_* sont définies, un modèle externe via API compatible OpenAI.
"""

import json
import os
import sys
import time
from pathlib import Path

from app import analyzer
from app.config import settings

OUT = Path("eval/out")


def configs() -> list[dict]:
    local = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434/v1")
    cfg = [
        {"nom": "Qwen 2.5 7B (local)", "base": local, "model": "qwen2.5:7b-instruct", "key": "local"},
        {"nom": "Qwen 2.5 14B (local)", "base": local, "model": "qwen2.5:14b-instruct", "key": "local"},
    ]
    if os.environ.get("EXTERNAL_LLM_API_KEY"):
        cfg.append({"nom": f"{os.environ.get('EXTERNAL_LLM_MODEL')} (API externe)",
                    "base": os.environ["EXTERNAL_LLM_BASE_URL"],
                    "model": os.environ["EXTERNAL_LLM_MODEL"],
                    "key": os.environ["EXTERNAL_LLM_API_KEY"]})
    return cfg


def main() -> None:
    text = Path(sys.argv[1]).read_text(encoding="utf-8")
    title = sys.argv[2] if len(sys.argv) > 2 else None
    label = Path(sys.argv[1]).stem
    results = []
    for c in configs():
        settings.llm_base_url, settings.llm_model, settings.llm_api_key = c["base"], c["model"], c["key"]
        t0 = time.time()
        try:
            res = analyzer.analyze_transcript(text, title)
            err = None
        except Exception as exc:  # noqa: BLE001
            res, err = None, str(exc)[:300]
        results.append({"modele": c["nom"], "secondes": round(time.time() - t0, 1), "erreur": err, "analyse": res})
        print(c["nom"], results[-1]["secondes"], err, flush=True)
    (OUT / f"models_{label}.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    md = [f"\n# Comparaison des modèles — transcription « {label} »\n",
          "Transcription commune :\n\n```\n" + text[:5000] + "\n```\n"]
    for r in results:
        md.append(f"## {r['modele']} — {r['secondes']} s" + (f" — ERREUR : {r['erreur']}" if r["erreur"] else "") + "\n")
        if r["analyse"]:
            md.append("```json\n" + json.dumps(r["analyse"], ensure_ascii=False, indent=1)[:7000] + "\n```\n")
    s = os.environ.get("GITHUB_STEP_SUMMARY")
    if s:
        with open(s, "a", encoding="utf-8") as fh:
            fh.write("\n".join(md))


if __name__ == "__main__":
    main()
