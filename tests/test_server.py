import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

from gcp_rag_mcp.server import create_server

pytestmark = pytest.mark.anyio

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
    async with Client(create_server(search)) as client:
        return await client.call_tool("gcp_course_search", arguments)


async def test_the_server_offers_one_read_only_search_tool():
    async with Client(create_server(RecordingSearch())) as client:
        tools = await client.list_tools()

    assert [t.name for t in tools] == ["gcp_course_search"]
    assert tools[0].annotations.read_only_hint is True
    assert tools[0].annotations.open_world_hint is False


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


async def test_an_empty_question_is_rejected_before_searching():
    search = RecordingSearch()

    with pytest.raises(ToolError):
        await call(search, question="", translation=TRANSLATION)

    assert search.calls == []


async def test_a_number_of_chunks_outside_1_to_100_is_rejected():
    for k in (0, 101):
        with pytest.raises(ToolError):
            await call(RecordingSearch(), question=QUESTION, translation=TRANSLATION, k=k)


async def test_a_failing_search_gives_an_error_that_says_what_to_check():
    search = RecordingSearch(error=RuntimeError("connection refused"))

    with pytest.raises(ToolError) as error:
        await call(search, question=QUESTION, translation=TRANSLATION)

    message = str(error.value)
    assert "RuntimeError" in message and "connection refused" in message
    assert "rag-db" in message and "model" in message


async def test_a_search_without_results_returns_an_empty_list():
    result = await call(RecordingSearch(hits=[]), question=QUESTION, translation=TRANSLATION)

    assert result.structured_content["result"] == []
