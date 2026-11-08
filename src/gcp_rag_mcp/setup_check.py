"""What a search needs to work (the model files and the database) and where to get each piece."""

import logging
from collections.abc import Callable
from typing import TypedDict

from rag.store import connect

from gcp_rag_mcp.config import Settings

logger = logging.getLogger(__name__)

MODEL_FILES = ("onnx/model_int8.onnx", "tokenizer.json", "config.json")

GUIDE = """What a search needs, and where to get each piece:

1. The database with the index (container `rag-db`, database `courses_bge`, port 5433). Image:
   ghcr.io/estvn/gcp-rag-db:bge-m3 (public). First time:
     podman run -d --name rag-db -p 127.0.0.1:5433:5432 -v rag_pgdata:/var/lib/postgresql/data ghcr.io/estvn/gcp-rag-db:bge-m3
   If the container already exists but is stopped: `podman start rag-db` (and `podman machine start` first if Podman is
   stopped). The first start restores the index and takes a few seconds.
2. The bge-m3 model (int8 ONNX), three files in {model_dir}:
   onnx/model_int8.onnx, tokenizer.json and config.json, from https://huggingface.co/onnx-community/bge-m3-ONNX
   (set RAG_MODEL_DIR to use another folder). The server loads it by itself on the first search.
3. The RAG code, installed next to this repository: https://github.com/estvn/GCP-ANALYTICS_RAG (`uv sync` here).
4. This server: https://github.com/estvn/GCP-ANALYTICS_RAG_MCP (its README has the registration command for Claude Code
   and OpenCode).

Only the database has to be started by hand; the server and the model start by themselves.
"""


class Check(TypedDict):
    name: str
    ok: bool
    detail: str


class SetupReport(TypedDict):
    ready: bool
    checks: list[Check]
    guide: str


def run_checks(settings: Settings, open_connection: Callable = connect) -> SetupReport:
    checks = [_model_check(settings), _database_check(settings, open_connection)]
    return SetupReport(ready=all(c["ok"] for c in checks), checks=checks, guide=GUIDE.format(model_dir=settings.model_dir))


def _model_check(settings: Settings) -> Check:
    missing = [name for name in MODEL_FILES if not (settings.model_dir / name).is_file()]
    if missing:
        return Check(name="model", ok=False, detail=f"missing in {settings.model_dir}: {', '.join(missing)}")
    return Check(name="model", ok=True, detail=f"bge-m3 files found in {settings.model_dir}")


def _database_check(settings: Settings, open_connection: Callable) -> Check:
    try:
        connection = open_connection(settings.database_url)
        try:
            chunks = connection.execute("select count(*) from chunks").fetchone()[0]
        finally:
            connection.close()
    except Exception as error:
        logger.warning("The database check failed", exc_info=True)  # the detail stays on the server
        return Check(name="database", ok=False, detail=f"cannot read the index ({type(error).__name__}): is the container running?")
    if chunks == 0:
        return Check(name="database", ok=False, detail="the index is empty: restore it from the image")
    return Check(name="database", ok=True, detail=f"{chunks} chunks")
