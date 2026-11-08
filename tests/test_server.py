import logging

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

from gcp_rag_mcp.server import MAX_QUESTION_CHARS, create_server

pytestmark = pytest.mark.anyio

TOOL = "gcp_rag_search_course"
HELP_TOOL = "gcp_rag_check_setup"
REPORT = {"ready": False, "checks": [{"name": "database", "ok": False, "detail": "cannot read the index"}], "guide": "Start rag-db"}
QUESTION = "¿Cómo se particiona una base de datos por columnas?"
TRANSLATION = "How is a database partitioned by columns?"


def hit(position: int) -> dict:
    """A chunk as `HybridRetriever.search_many` returns it, with the extra fields the server must not expose."""
    return {
        "id": position,
        "source": f"02_COURSE/{position:03d}_FILE.md",
        "idx": 0,
        "headers": ["Partitioning", "Vertical"],
        "text": f"Chunk number {position}",
        "distance": 0.1,
        "kw_score": 1.0,
        "score": 0.03,
    }


class RecordingSearch:
    """A stand-in for the retriever that remembers how it was called."""

    def __init__(self, hits=None, error=None):
        self.hits = [hit(1), hit(2)] if hits is None else hits
        self.error = error
        self.calls = []

    def __call__(self, phrasings, k):
        self.calls.append((phrasings, k))
        if self.error:
            raise self.error
        return self.hits[:k]


async def call(search, **arguments):
    async with Client(create_server(search, lambda: REPORT)) as client:
        return await client.call_tool(TOOL, arguments)


async def test_the_server_offers_a_search_tool_and_a_setup_check_and_both_are_read_only():
    async with Client(create_server(RecordingSearch(), lambda: REPORT)) as client:
        tools = await client.list_tools()

    assert sorted(t.name for t in tools) == [HELP_TOOL, TOOL]
    for tool in tools:
        assert tool.annotations.read_only_hint is True
        assert tool.annotations.open_world_hint is False


async def test_the_setup_check_returns_the_report_with_what_is_missing_and_the_guide():
    async with Client(create_server(RecordingSearch(), lambda: REPORT)) as client:
        result = await client.call_tool(HELP_TOOL, {})

    assert result.structured_content == REPORT


async def test_each_chunk_comes_with_its_rank_source_headers_and_text_only():
    result = await call(RecordingSearch(), question=QUESTION, translation=TRANSLATION)

    assert result.structured_content["result"] == [
        {"rank": 1, "source": "02_COURSE/001_FILE.md", "headers": ["Partitioning", "Vertical"], "text": "Chunk number 1"},
        {"rank": 2, "source": "02_COURSE/002_FILE.md", "headers": ["Partitioning", "Vertical"], "text": "Chunk number 2"},
    ]


async def test_the_question_and_its_translation_are_searched_together():
    search = RecordingSearch()

    await call(search, question=QUESTION, translation=TRANSLATION, k=7)

    assert search.calls == [([QUESTION, TRANSLATION], 7)]


async def test_it_returns_30_chunks_unless_asked_for_another_number():
    search = RecordingSearch()

    await call(search, question=QUESTION, translation=TRANSLATION)

    assert search.calls[0][1] == 30


@pytest.mark.parametrize("k", [1, 100])
async def test_the_smallest_and_the_largest_number_of_chunks_are_accepted(k):
    search = RecordingSearch()

    await call(search, question=QUESTION, translation=TRANSLATION, k=k)

    assert search.calls[0][1] == k


@pytest.mark.parametrize("k", [0, 101])
async def test_a_number_of_chunks_outside_1_to_100_is_rejected(k):
    search = RecordingSearch()

    with pytest.raises(ToolError):
        await call(search, question=QUESTION, translation=TRANSLATION, k=k)

    assert search.calls == []


@pytest.mark.parametrize("field", ["question", "translation"])
async def test_an_empty_text_is_rejected_before_searching(field):
    search = RecordingSearch()
    arguments = {"question": QUESTION, "translation": TRANSLATION, field: ""}

    with pytest.raises(ToolError):
        await call(search, **arguments)

    assert search.calls == []


@pytest.mark.parametrize("field", ["question", "translation"])
async def test_a_text_longer_than_the_limit_is_rejected_before_searching(field):
    search = RecordingSearch()
    arguments = {"question": QUESTION, "translation": TRANSLATION, field: "a" * (MAX_QUESTION_CHARS + 1)}

    with pytest.raises(ToolError):
        await call(search, **arguments)

    assert search.calls == []


async def test_a_text_exactly_at_the_limit_is_accepted():
    search = RecordingSearch()

    await call(search, question="a" * MAX_QUESTION_CHARS, translation=TRANSLATION)

    assert len(search.calls) == 1


async def test_a_failing_search_tells_the_client_what_to_check_without_the_internal_detail():
    search = RecordingSearch(error=RuntimeError("password=sentinel-secret host=10.0.0.5"))

    with pytest.raises(ToolError) as error:
        await call(search, question=QUESTION, translation=TRANSLATION)

    message = str(error.value)
    assert "RuntimeError" in message
    assert "rag-db" in message and "model" in message
    assert "sentinel-secret" not in message and "10.0.0.5" not in message


async def test_the_internal_detail_of_a_failure_is_logged_on_the_server(caplog):
    search = RecordingSearch(error=RuntimeError("connection refused by 10.0.0.5"))

    with caplog.at_level(logging.ERROR, logger="gcp_rag_mcp"), pytest.raises(ToolError):
        await call(search, question=QUESTION, translation=TRANSLATION)

    assert "connection refused by 10.0.0.5" in caplog.text


async def test_a_search_without_results_returns_an_empty_list():
    result = await call(RecordingSearch(hits=[]), question=QUESTION, translation=TRANSLATION)

    assert result.structured_content["result"] == []


async def test_the_text_does_not_repeat_the_path_and_headers_that_the_chunk_already_carries():
    prefixed = {**hit(1), "text": "02_COURSE/001_FILE > Partitioning > Vertical\nThe body of the chunk"}

    result = await call(RecordingSearch(hits=[prefixed]), question=QUESTION, translation=TRANSLATION)

    chunk = result.structured_content["result"][0]
    assert chunk["text"] == "The body of the chunk"
    assert chunk["source"] == "02_COURSE/001_FILE.md" and chunk["headers"] == ["Partitioning", "Vertical"]
