"""Transcript analysis with a local LLM through an OpenAI-compatible API.

Default target: Ollama (http://127.0.0.1:11434/v1). Any server exposing
/chat/completions works (LM Studio, vLLM, llama.cpp server, or a cloud API).
"""

from __future__ import annotations

import json
import re

import httpx

from app.config import settings


class AnalysisError(RuntimeError):
    pass


ANALYSIS_KEYS = (
    "summary", "key_ideas", "facts", "opinions",
    "claims_to_verify", "people_and_entities", "critical_analysis", "topics",
)

SYSTEM_PROMPT = """Tu es un analyste rigoureux. Tu reçois la transcription d'une vidéo.
Réponds UNIQUEMENT par un objet JSON valide, sans texte autour, en {lang}, avec ces clés :
- "summary": résumé fidèle en 5 à 8 phrases ;
- "key_ideas": liste des idées clés (phrases courtes) ;
- "facts": affirmations factuelles vérifiables présentées dans la vidéo ;
- "opinions": opinions, jugements ou interprétations de l'auteur ;
- "claims_to_verify": affirmations douteuses, chiffrées ou non sourcées à vérifier, chacune avec la raison ;
- "people_and_entities": personnes, organisations, marques, lieux cités ;
- "critical_analysis": évaluation critique (biais, sophismes, angles morts, qualité des preuves) ;
- "topics": 3 à 8 mots-clés thématiques.
Règles :
- chaque élément de liste est une phrase simple (chaîne de caractères), jamais un objet ;
- "critical_analysis" est un paragraphe de texte, pas une liste ;
- les avertissements de l'auteur (« fictif », « humour », « ce n'est pas un conseil »…) ne sont pas des faits :
  évalue s'ils servent de précaution rhétorique ;
- cite dans "people_and_entities" tous les noms propres entendus (personnes, outils, marques, plateformes).
N'invente rien qui ne soit pas dans la transcription. Si une liste est vide, renvoie []."""

COMPARE_PROMPT = """Tu compares plusieurs vidéos à partir de leurs analyses.
Réponds UNIQUEMENT par un objet JSON valide en {lang} avec les clés :
- "common_points": points communs ;
- "differences": divergences, avec la vidéo concernée ;
- "contradictions": contradictions factuelles entre vidéos ;
- "most_reliable": quelle vidéo semble la mieux étayée et pourquoi ;
- "synthesis": synthèse en 5 phrases maximum."""


def _chat(system: str, user: str) -> str:
    url = settings.llm_base_url.rstrip("/") + "/chat/completions"
    payload = {
        "model": settings.llm_model,
        "temperature": 0.2,
        # Force a JSON object (supported by Ollama, OpenAI and most compatible servers).
        "response_format": {"type": "json_object"},
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
    }
    headers = {"Authorization": f"Bearer {settings.llm_api_key}"}
    try:
        resp = httpx.post(url, json=payload, headers=headers, timeout=settings.llm_timeout_s)
    except httpx.HTTPError as exc:
        raise AnalysisError(
            f"LLM injoignable à {settings.llm_base_url} ({exc.__class__.__name__}). "
            "Vérifie que le serveur local (ex. Ollama) est lancé."
        ) from exc
    if resp.status_code == 400 and "response_format" in resp.text:
        # Some compatible servers reject the JSON mode: retry without it.
        payload.pop("response_format", None)
        try:
            resp = httpx.post(url, json=payload, headers=headers, timeout=settings.llm_timeout_s)
        except httpx.HTTPError as exc:
            raise AnalysisError(f"LLM injoignable ({exc.__class__.__name__}).") from exc
    if resp.status_code != 200:
        raise AnalysisError(f"Erreur LLM {resp.status_code} : {resp.text[:300]}")
    try:
        return resp.json()["choices"][0]["message"]["content"]
    except (KeyError, IndexError, ValueError) as exc:
        raise AnalysisError("Réponse LLM inattendue.") from exc


def parse_json(text: str) -> dict:
    """Extract the first JSON object from a model answer (tolerates ```json fences)."""
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.IGNORECASE)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise AnalysisError("Le LLM n'a pas renvoyé de JSON.")
    raw = text[start : end + 1]
    try:
        data = json.loads(raw, strict=False)
    except json.JSONDecodeError:
        # Common model mistake: stray backslashes (e.g. "\'" or transliterations).
        repaired = re.sub(r'\\(?!["\\/bfnrtu])', r"\\\\", raw)
        try:
            data = json.loads(repaired, strict=False)
        except json.JSONDecodeError as exc:
            raise AnalysisError(f"JSON invalide renvoyé par le LLM : {exc}") from exc
    if not isinstance(data, dict):
        raise AnalysisError("Le LLM n'a pas renvoyé un objet JSON.")
    return data


def _to_text(v) -> str:
    """Flatten whatever the model returned into readable text."""
    if v is None:
        return ""
    if isinstance(v, str):
        return v.strip()
    if isinstance(v, dict):
        vals = [_to_text(x) for x in v.values() if _to_text(x)]
        return " — ".join(vals)
    if isinstance(v, list):
        return " ".join(_to_text(x) for x in v if _to_text(x))
    return str(v)


def _normalise(data: dict) -> dict:
    out: dict = {}
    for key in ANALYSIS_KEYS:
        val = data.get(key)
        if key in ("summary", "critical_analysis"):
            out[key] = _to_text(val)
        else:
            if val is None:
                val = []
            if not isinstance(val, list):
                val = [val]
            out[key] = [t for t in (_to_text(v) for v in val) if t]
    return out


def analyze_transcript(transcript: str, title: str | None = None) -> dict:
    if not transcript.strip():
        raise AnalysisError("Transcription vide : rien à analyser.")
    truncated = len(transcript) > settings.llm_max_transcript_chars
    body = transcript[: settings.llm_max_transcript_chars]
    user = (f"Titre : {title}\n\n" if title else "") + f"Transcription :\n{body}"
    system = SYSTEM_PROMPT.format(lang=settings.analysis_language)
    try:
        result = _normalise(parse_json(_chat(system, user)))
    except AnalysisError as first:
        if "JSON" not in str(first):
            raise
        result = _normalise(parse_json(_chat(system, user)))  # one retry on malformed output
    result["truncated_input"] = truncated
    return result


def compare_analyses(items: list[dict]) -> dict:
    blocks = []
    for it in items:
        blocks.append(
            f"### Vidéo {it['job_id']} — {it.get('title') or ''}\n"
            + json.dumps(it["analysis"], ensure_ascii=False)
        )
    raw = _chat(COMPARE_PROMPT.format(lang=settings.analysis_language), "\n\n".join(blocks))
    return parse_json(raw)
