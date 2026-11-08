"""Where the server finds the database and the model, read from the environment."""

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import rag

# The index of the winning configuration (semantic + header cuts, bge-m3) with the GCP and Power BI courses, as in the
# published image ghcr.io/estvn/gcp-rag-db:bge-m3 (local development credentials).
# connect_timeout: with the database down the tool answers with an error in 5 seconds instead of waiting for the system.
DEFAULT_DATABASE_URL = "postgresql://rag:rag@127.0.0.1:5433/courses_bge?connect_timeout=5"
# The models folder of the rag repository, found from the (editable) install of the `rag` package.
DEFAULT_MODEL_DIR = Path(rag.__file__).resolve().parents[2] / "models" / "bge-m3"


@dataclass(frozen=True)
class Settings:
    database_url: str
    model_dir: Path

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> "Settings":
        env = os.environ if environ is None else environ
        return cls(
            database_url=env.get("RAG_DATABASE_URL", DEFAULT_DATABASE_URL),
            model_dir=Path(env.get("RAG_MODEL_DIR", DEFAULT_MODEL_DIR)),
        )
