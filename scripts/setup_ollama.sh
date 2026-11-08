#!/usr/bin/env bash
# Installe Ollama (LLM local) et télécharge le modèle d'analyse.
# À lancer une fois dans le Codespace ou sur le serveur local (Linux).
set -euo pipefail
MODEL="${1:-qwen2.5:7b-instruct}"
if ! command -v ollama >/dev/null; then
  curl -fsSL https://ollama.com/install.sh | sh
fi
# Contexte élargi : par défaut Ollama tronque les longues transcriptions sans prévenir.
(OLLAMA_CONTEXT_LENGTH=16384 ollama serve > /tmp/ollama.log 2>&1 &) ; sleep 3
ollama pull "$MODEL"
echo "Ollama prêt avec $MODEL sur http://127.0.0.1:11434"
