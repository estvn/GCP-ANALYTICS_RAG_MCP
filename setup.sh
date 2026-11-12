#!/usr/bin/env bash
# Prepares what the model commands need (the RAG code next to this repository and the Python environment) and then runs
# `python -m gcp_rag_mcp setup`, which explains the models, asks which one to install, downloads its files and its
# database image and starts the database. Safe to run again: what is already there is left alone.
#
#   ./setup.sh                      install (asks which model)
#   ./setup.sh --model e5-small     install without asking (bge-m3 or e5-small)
#   ./setup.sh --check              only say what is missing, change nothing (exit 1 if something is missing)
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
RAG_DIR="${RAG_DIR:-$HERE/../rag}"

need() { command -v "$1" > /dev/null 2>&1 || { printf 'missing tool: %s (%s)\n' "$1" "$2"; exit 1; }; }
need git "https://git-scm.com"
need uv "https://docs.astral.sh/uv/"
need podman "https://podman.io"

if [ "${1:-}" = "--check" ]; then
  [ -d "$RAG_DIR/.git" ] || { printf 'missing: the RAG repository in %s (run ./setup.sh)\n' "$RAG_DIR"; exit 1; }
  exec uv run --project "$HERE" python -m gcp_rag_mcp status
fi

[ -d "$RAG_DIR/.git" ] || git clone https://github.com/estvn/GCP-ANALYTICS_RAG.git "$RAG_DIR"
uv sync --project "$HERE"
exec uv run --project "$HERE" python -m gcp_rag_mcp setup "$@"
