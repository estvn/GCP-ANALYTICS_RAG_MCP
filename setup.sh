#!/usr/bin/env bash
# Sets up everything a search needs: the RAG code next to this repository, the Python environment, the bge-m3 files and the
# database container with the index. Safe to run again: what is already there is left alone.
#
#   ./setup.sh           do it
#   ./setup.sh --check   only say what is missing, change nothing
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
RAG_DIR="${RAG_DIR:-$HERE/../rag}"
MODEL_DIR="${RAG_MODEL_DIR:-$RAG_DIR/models/bge-m3}"
IMAGE="ghcr.io/estvn/gcp-rag-db:bge-m3"
CONTAINER="rag-db"
MODEL_URL="https://huggingface.co/onnx-community/bge-m3-ONNX/resolve/main"
MODEL_SHA256="2237f770aad5c71bbc1fc2d361a57f9a37400574cc9eff32626f0cdb49234730"  # onnx/model_int8.onnx
CHECK_ONLY=0
[ "${1:-}" = "--check" ] && CHECK_ONLY=1

missing=0
say() { printf '%s\n' "$*"; }
need() { command -v "$1" > /dev/null 2>&1 || { say "missing tool: $1 ($2)"; exit 1; }; }
todo() { # todo "what is missing" command...
  say "missing: $1"
  missing=1
  shift
  [ "$CHECK_ONLY" -eq 1 ] || "$@"
}

need git "https://git-scm.com"
need uv "https://docs.astral.sh/uv/"
need podman "https://podman.io"
need curl "needed to download the model files"

[ -d "$RAG_DIR/.git" ] || todo "the RAG repository in $RAG_DIR" git clone https://github.com/estvn/GCP-ANALYTICS_RAG.git "$RAG_DIR"

[ -x "$HERE/.venv/Scripts/python.exe" ] || [ -x "$HERE/.venv/bin/python" ] || todo "the Python environment (uv sync)" bash -c "cd '$HERE' && uv sync"

download() { # download "relative path in the repository" "destination"
  mkdir -p "$(dirname "$2")"
  curl -L --fail --progress-bar -o "$2.part" "$MODEL_URL/$1" && mv "$2.part" "$2"
}
for file in tokenizer.json config.json onnx/model_int8.onnx; do
  [ -f "$MODEL_DIR/$file" ] || todo "model file $file" download "$file" "$MODEL_DIR/$file"
done
if [ -f "$MODEL_DIR/onnx/model_int8.onnx" ] && [ "$CHECK_ONLY" -eq 0 ]; then
  actual="$(sha256sum "$MODEL_DIR/onnx/model_int8.onnx" | cut -d' ' -f1)"
  [ "$actual" = "$MODEL_SHA256" ] || { say "the SHA-256 of model_int8.onnx is $actual, expected $MODEL_SHA256: delete the file and run again"; exit 1; }
fi

state="$(podman ps -a --filter "name=^${CONTAINER}$" --format '{{.Status}}' 2> /dev/null || true)"
case "$state" in
  Up*) ;;
  "") todo "the container $CONTAINER" podman run -d --name "$CONTAINER" -p 127.0.0.1:5433:5432 -v rag_pgdata:/var/lib/postgresql/data "$IMAGE" ;;
  *) todo "the container $CONTAINER is stopped" podman start "$CONTAINER" ;;
esac

if [ "$CHECK_ONLY" -eq 0 ]; then
  say "waiting for the database..."
  for _ in $(seq 1 60); do
    podman exec "$CONTAINER" pg_isready -h 127.0.0.1 -U rag > /dev/null 2>&1 && break
    sleep 2
  done
  chunks="$(podman exec "$CONTAINER" psql -U rag -d courses_bge -Atc 'select count(*) from chunks' 2> /dev/null || echo 0)"
  [ "${chunks:-0}" -gt 0 ] || { say "the database courses_bge is empty or missing: it is not the image $IMAGE?"; exit 1; }
  say "database ready: $chunks chunks"
fi

if [ "$missing" -eq 0 ]; then
  say "everything is in place."
elif [ "$CHECK_ONLY" -eq 1 ]; then
  say "run ./setup.sh to fix it."
else
  say "done. Register the server in your client: see the README, section 'Register it in a client'."
fi
[ "$CHECK_ONLY" -eq 0 ] || [ "$missing" -eq 0 ]
