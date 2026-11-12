"""What a search needs to work (the model files and the database) and where to get each piece."""

import logging
from collections.abc import Callable
from typing import TypedDict

from rag.store import connect

from gcp_rag_mcp.config import Settings

logger = logging.getLogger(__name__)

GUIDE = """What a search needs, and where to get each piece (model in use: {key}):

1. The database with the index (container `{container}`, database `{database}`, port 5433). Image:
   {image} (public). First time:
     podman run -d --name {container} -p 127.0.0.1:5433:5432 -v {volume}:/var/lib/postgresql/data {image}
   If the container already exists but is stopped: `podman start {container}` (and `podman machine start` first if Podman is
   stopped). The first start restores the index and takes a few seconds.
2. The {key} model, three files in {model_dir}: {files}, from {source_url}
   (set RAG_MODEL_DIR to use another folder). The server loads it by itself on the first search.
3. The RAG code, installed next to this repository: https://github.com/estvn/GCP-ANALYTICS_RAG (`uv sync` here).
4. This server: https://github.com/estvn/GCP-ANALYTICS_RAG_MCP (its README has the registration command for Claude Code
   and OpenCode).

Only the database has to be started by hand; the server and the model start by themselves.
All of the above in one go: `./setup.sh` in this repository (it installs the RAG code and the environment, then asks
which model to install; `./setup.sh --check` only reports what is missing). To change the model later:
`python -m gcp_rag_mcp switch`. `python -m gcp_rag_mcp help` lists every command.
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
    return SetupReport(ready=all(c["ok"] for c in checks), checks=checks, guide=_guide(settings))


def _guide(settings: Settings) -> str:
    model = settings.model
    return GUIDE.format(
        key=model.key,
        container=model.container,
        database=model.database,
        image=model.image,
        volume=model.volume,
        model_dir=settings.model_dir,
        files=", ".join(model.files),
        source_url=model.source_url,
    )


def _model_check(settings: Settings) -> Check:
    missing = [name for name in settings.model.files if not (settings.model_dir / name).is_file()]
    if missing:
        return Check(name="model", ok=False, detail=f"missing in {settings.model_dir}: {', '.join(missing)}")
    return Check(name="model", ok=True, detail=f"{settings.model.key} files found in {settings.model_dir}")


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
