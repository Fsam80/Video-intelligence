#!/usr/bin/env bash
# Lance le service de récupération (8001) puis l'application (8000).
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p data
uvicorn fetcher.main:app --host 0.0.0.0 --port 8001 > data/fetcher.log 2>&1 &
FETCHER_PID=$!
trap 'kill $FETCHER_PID 2>/dev/null || true' EXIT
echo "Fetcher lancé (PID $FETCHER_PID, logs : data/fetcher.log)"
echo "Application : http://localhost:8000  —  API : http://localhost:8000/docs"
uvicorn app.main:app --host 0.0.0.0 --port 8000
