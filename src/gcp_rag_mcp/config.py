"""Where the server finds the database and the model, read from the environment and from the model chosen with `setup`."""

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import rag

from gcp_rag_mcp.catalog import DEFAULT_MODEL, MODELS, ModelOption, get_model
from gcp_rag_mcp.preferences import load_model

# The models folder of the rag repository, found from the (editable) install of the `rag` package.
MODELS_DIR = Path(rag.__file__).resolve().parents[2] / "models"
# Local development credentials of the published images ghcr.io/estvn/gcp-rag-db:<model>.
# connect_timeout: with the database down the tool answers with an error in 5 seconds instead of waiting for the system.
DATABASE_URL = "postgresql://rag:rag@127.0.0.1:5433/{database}?connect_timeout=5"


@dataclass(frozen=True)
class Settings:
    database_url: str
    model_dir: Path
    model: ModelOption = MODELS[DEFAULT_MODEL]

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> "Settings":
        """RAG_MODEL wins, then the model saved by `setup` or `switch`, then the default. The two other variables
        (RAG_DATABASE_URL, RAG_MODEL_DIR) still override the place where the database and the files are."""
        env = os.environ if environ is None else environ
        model = get_model(env.get("RAG_MODEL") or load_model(env) or DEFAULT_MODEL)
        return cls(
            database_url=env.get("RAG_DATABASE_URL", DATABASE_URL.format(database=model.database)),
            model_dir=Path(env.get("RAG_MODEL_DIR", MODELS_DIR / model.folder)),
            model=model,
        )
