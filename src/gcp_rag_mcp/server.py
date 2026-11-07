"""The MCP server: one read-only tool that searches the course."""

from collections.abc import Callable
from typing import Annotated, TypedDict

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import Field
from rag.retrieval.search import DEFAULT_K

SearchFn = Callable[[list[str], int], list[dict]]
MAX_CHUNKS = 100

INSTRUCTIONS = (
    "Searches the material of the Google Cloud Data Analytics course. Use gcp_course_search to find passages "
    "before answering a question about the course, and cite the source file and headers of the passages you use."
)
SEARCH_FAILED = (
    "The course search failed ({kind}: {detail}). Check that the database container `rag-db` is running "
    "and that the bge-m3 model files are in place (see the README of this server)."
)


class Chunk(TypedDict):
    rank: int
    source: str
    headers: list[str]
    text: str


def create_server(search: SearchFn) -> FastMCP:
    server = FastMCP("gcp_rag_mcp", instructions=INSTRUCTIONS)

    @server.tool(
        name="gcp_course_search",
        annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False),
    )
    def gcp_course_search(
        question: Annotated[str, Field(min_length=1, description="The question, as the user asked it.")],
        translation: Annotated[
            str,
            Field(
                min_length=1,
                description="The same question translated into the other language: English if it is in Spanish, "
                "Spanish if it is in English. The course has passages in both languages.",
            ),
        ],
        k: Annotated[int, Field(ge=1, le=MAX_CHUNKS, description="How many chunks to return, best first.")] = DEFAULT_K,
    ) -> list[Chunk]:
        """Search the Google Cloud Data Analytics course (passages in English and Spanish).

        Returns the most relevant chunks, best first, each with its rank, its source file, its header path and its
        text. Always give the question and its translation: both are searched and the rankings are fused, which
        finds the passages written in the other language.
        """
        try:
            hits = search([question, translation], k)
        except Exception as error:
            raise ToolError(SEARCH_FAILED.format(kind=type(error).__name__, detail=error)) from error
        return [Chunk(rank=rank, source=h["source"], headers=h["headers"], text=h["text"]) for rank, h in enumerate(hits, 1)]

    return server
