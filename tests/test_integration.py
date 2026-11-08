"""The whole path against the real index and the real model: slow, so it is skipped when they are not there."""

import psycopg
import pytest
from fastmcp import Client

from gcp_rag_mcp.config import Settings
from gcp_rag_mcp.retriever import build_retriever
from gcp_rag_mcp.server import create_server
from gcp_rag_mcp.setup_check import run_checks

pytestmark = [pytest.mark.integration, pytest.mark.anyio]


@pytest.fixture(scope="module")
def settings():
    settings = Settings.from_env()
    if not (settings.model_dir / "onnx" / "model_int8.onnx").exists():
        pytest.skip("the bge-m3 files are not there")
    try:
        retriever = build_retriever(settings)
        retriever.search(["prueba", "test"], 1)
    except psycopg.OperationalError:  # the database is down: this test needs it
        pytest.skip("the database is not reachable")
    return settings


async def test_a_real_question_returns_30_chunks_with_their_sources(settings):
    server = create_server(build_retriever(settings).search, lambda: run_checks(settings))

    async with Client(server) as client:
        result = await client.call_tool(
            "gcp_rag_search_course",
            {"question": "¿Cómo se particiona una base de datos por columnas?", "translation": "How is a database partitioned by columns?"},
        )

    chunks = result.structured_content["result"]
    assert len(chunks) == 30
    assert [c["rank"] for c in chunks] == list(range(1, 31))
    assert all(c["source"].endswith(".md") and c["text"] for c in chunks)


async def test_the_setup_check_finds_the_real_model_and_database_ready(settings):
    server = create_server(build_retriever(settings).search, lambda: run_checks(settings))

    async with Client(server) as client:
        result = await client.call_tool("gcp_rag_check_setup", {})

    report = result.structured_content
    assert report["ready"] is True
    assert [c["name"] for c in report["checks"]] == ["model", "database"]
    assert "ghcr.io/estvn/gcp-rag-db:bge-m3" in report["guide"]
