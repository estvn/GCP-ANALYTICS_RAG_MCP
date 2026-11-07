"""Run the server over stdio: `python -m gcp_rag_mcp`."""

from gcp_rag_mcp.config import Settings
from gcp_rag_mcp.retriever import build_retriever
from gcp_rag_mcp.server import create_server


def main() -> None:
    create_server(build_retriever(Settings.from_env()).search).run()


if __name__ == "__main__":
    main()
