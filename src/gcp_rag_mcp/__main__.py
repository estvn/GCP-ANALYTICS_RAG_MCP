"""Run the server over stdio (`python -m gcp_rag_mcp`) or a command (`python -m gcp_rag_mcp setup`, see `help`)."""

import sys

from gcp_rag_mcp.cli import main as run_command
from gcp_rag_mcp.config import Settings
from gcp_rag_mcp.retriever import build_retriever
from gcp_rag_mcp.server import create_server
from gcp_rag_mcp.setup_check import run_checks


def main() -> None:
    if len(sys.argv) > 1:  # clients start the server without arguments
        raise SystemExit(run_command())
    settings = Settings.from_env()
    create_server(build_retriever(settings).search, lambda: run_checks(settings)).run()


if __name__ == "__main__":
    main()
