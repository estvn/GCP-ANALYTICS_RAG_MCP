"""The model chosen with `setup` or `switch`, kept in a small file so the server can start with it."""

import json
import os
from collections.abc import Mapping
from pathlib import Path


def _preferences_file(env: Mapping[str, str]) -> Path:
    home = env.get("RAG_MCP_HOME")
    return (Path(home) if home else Path.home() / ".gcp-rag-mcp") / "preferences.json"


def load_model(env: Mapping[str, str] | None = None) -> str | None:
    """The saved model name, or None if nothing was chosen yet or the file cannot be read."""
    env = os.environ if env is None else env
    try:
        return json.loads(_preferences_file(env).read_text(encoding="utf-8")).get("model")
    except (OSError, ValueError, AttributeError):  # a damaged file must not stop the server from starting
        return None


def save_model(key: str, env: Mapping[str, str] | None = None) -> None:
    env = os.environ if env is None else env
    path = _preferences_file(env)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"model": key}), encoding="utf-8")
