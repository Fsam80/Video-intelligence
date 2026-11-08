# Video Intelligence

Transforme une vidéo (lien TikTok ou YouTube, ou fichier importé) en connaissances structurées : transcription horodatée, résumé, idées clés, **faits vs opinions**, affirmations à vérifier, analyse critique, bibliothèque consultable, comparaison de vidéos et export Markdown.

Statut : **v0.2 — MVP fonctionnel** (local, mono-utilisateur).

## Architecture

```
Navigateur (interface web, port 8000)
   │
   ▼
app/  ── API FastAPI ──────────────────────────────┐
   │   jobs, bibliothèque, recherche, export        │
   │                                                │
   ├─► fetcher/ (service séparé, port 8001)         │  scraping isolé :
   │      yt-dlp → fichier audio + métadonnées      │  remplaçable sans toucher à l'analyse
   │                                                │
   ├─► ffmpeg → audio 16 kHz                        │
   ├─► faster-whisper (local) → transcription       │
   ├─► LLM local via API compatible OpenAI          │  Ollama par défaut
   └─► SQLite + index plein texte (FTS5)            │
```

| Élément | Choix |
|---|---|
| API | Python + FastAPI |
| Récupération des vidéos | Service `fetcher/` séparé, yt-dlp |
| Transcription | faster-whisper (CPU, local) |
| Analyse | Tout LLM compatible OpenAI (Ollama, LM Studio, vLLM… ou API cloud) |
| Stockage | SQLite + FTS5 (recherche insensible aux accents) |
| Interface | Page web unique, `app/static/index.html` |

Plateformes : **TikTok** et **YouTube** activées. Instagram, Facebook et X sont détectées mais refusées proprement : utiliser l'import de fichier.

## Démarrage (Codespace)

Le dossier `.devcontainer/` installe automatiquement Python, ffmpeg et les dépendances.

1. Créer un nouveau Codespace sur la branche, machine **4 cœurs / 16 Go** recommandée.
2. Installer le LLM local (une seule fois, ~5 Go) :
   ```bash
   bash scripts/setup_ollama.sh         # modèle par défaut : qwen2.5:7b-instruct
   ```
3. Lancer l'application :
   ```bash
   bash scripts/start.sh
   ```
4. Ouvrir le port 8000 (onglet « Ports ») → interface web. Documentation de l'API : `/docs`.

Au premier traitement, le modèle Whisper est téléchargé depuis huggingface.co (~500 Mo pour `small`).

## Configuration

Copier `.env.example` en `.env`. Principaux réglages :

| Variable | Rôle | Défaut |
|---|---|---|
| `WHISPER_MODEL` | `tiny`, `base`, `small`, `medium`, `large-v3` (précision ↑, vitesse ↓) | `small` |
| `WHISPER_LANGUAGE` | Forcer la langue (`fr`, `ar`, `en`…) ; vide = détection | vide |
| `LLM_BASE_URL` / `LLM_MODEL` | Serveur et modèle d'analyse | Ollama / `qwen2.5:7b-instruct` |
| `LLM_MAX_TRANSCRIPT_CHARS` | Au-delà, la transcription est tronquée pour l'analyse (signalé dans le résultat) | 24 000 |
| `KEEP_MEDIA` | Conserver les fichiers audio/vidéo après traitement | `false` |
| `FETCHER_COOKIES_FILE` | Fichier cookies (format Netscape) si une plateforme exige une connexion | vide |

## API

| Méthode | Route | Rôle |
|---|---|---|
| POST | `/v1/jobs` | Soumettre un lien `{"url": "..."}` |
| POST | `/v1/jobs/upload` | Importer un fichier audio/vidéo |
| GET | `/v1/jobs`, `/v1/jobs/{id}` | Bibliothèque, statut |
| GET | `/v1/jobs/{id}/transcript` | Transcription horodatée |
| GET | `/v1/jobs/{id}/analysis` | Analyse structurée |
| POST | `/v1/jobs/{id}/analyze` | Relancer l'analyse (ex. après changement de modèle) |
| GET | `/v1/jobs/{id}/export` | Export Markdown |
| DELETE | `/v1/jobs/{id}` | Supprimer |
| GET | `/v1/search?q=` | Recherche plein texte dans les transcriptions |
| POST | `/v1/compare` | Comparer 2 à 5 vidéos analysées |

## Tests

```bash
pip install -r requirements-dev.txt
python -m pytest -q
```

Les tests simulent Whisper, le LLM et le fetcher : ils tournent sans réseau ni GPU.

## Limites connues

- **Récupération des vidéos** : dépend de yt-dlp et des protections des plateformes. TikTok change souvent ; mettre à jour avec `pip install -U yt-dlp` en cas d'échec. Repli : import manuel du fichier.
- **Droits** : ne traiter que des contenus auxquels on a légitimement accès ; respecter les conditions des plateformes et le droit d'auteur.
- **Qualité de l'analyse** : dépend du modèle local. Un 7B reste moyen sur l'analyse critique ; vérifier les résultats.
- **Vision** : seule la parole est analysée (pas l'image ni le texte à l'écran).
- **Mono-utilisateur** : pas d'authentification. Ne pas exposer publiquement le port 8000.

## Prochaines étapes

1. Serveur MCP (intégration ChatGPT / Claude) au-dessus de l'API existante.
2. Instagram via le fetcher (cookies requis).
3. OCR du texte à l'écran (optionnel).
4. Authentification + PostgreSQL pour un déploiement multi-utilisateur.
