"""MCP server that exposes the retrieval of the GCP Analytics RAG."""

from gcp_rag_mcp.config import Settings
from gcp_rag_mcp.retriever import LazyRetriever, build_retriever
from gcp_rag_mcp.server import create_server
from gcp_rag_mcp.setup_check import run_checks

__all__ = ["LazyRetriever", "Settings", "build_retriever", "create_server", "run_checks"]
