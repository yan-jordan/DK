#!/usr/bin/env bash
# One-command startup: build the index on first run, then serve.
#
# The build is idempotent and guarded by meta.json, so `docker compose up`
# a second time skips straight to serving. Set IMDB_REBUILD=1 to force.
set -euo pipefail

INDEX_DIR="${IMDB_INDEX_DIR:-/data/index}"
WORKERS="${WORKERS:-4}"
PORT="${PORT:-8000}"

if [[ "${IMDB_REBUILD:-0}" == "1" || ! -f "${INDEX_DIR}/meta.json" ]]; then
  echo "--- no index found at ${INDEX_DIR}; downloading dataset and building ---"
  echo "--- one-off cost: ~1.4 GB download, ~7 GB uncompressed during the build ---"
  echo "--- subsequent starts skip straight to serving ---"
  python -m app.build_index --download
else
  echo "--- reusing existing index at ${INDEX_DIR} ---"
fi

echo "--- starting uvicorn with ${WORKERS} worker(s) on :${PORT} ---"
exec uvicorn app.main:app \
  --host 0.0.0.0 \
  --port "${PORT}" \
  --workers "${WORKERS}" \
  --no-access-log
