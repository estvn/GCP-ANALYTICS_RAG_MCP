"""The MCP server: one read-only tool that searches the course."""

import logging
from collections.abc import Callable
from typing import Annotated, TypedDict

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import Field
from rag.retrieval.search import DEFAULT_K

from gcp_rag_mcp.setup_check import SetupReport

logger = logging.getLogger(__name__)

SearchFn = Callable[[list[str], int], list[dict]]
MAX_CHUNKS = 100
MAX_QUESTION_CHARS = 2000  # about 500 tokens: far more than a question needs, and it bounds the work of one search

INSTRUCTIONS = (
    "Searches the material of the Google Cloud Data Analytics course. Use gcp_rag_search_course to find passages "
    "before answering a question about the course, and cite the source file and headers of the passages you use. "
    "If a search fails, or you are not sure the database and the model are ready, call gcp_rag_check_setup and tell "
    "the user what is missing and where to get it."
)
SEARCH_FAILED = (
    "The course search failed ({kind}). Check that the database container `rag-db` is running "
    "and that the bge-m3 model files are in place (see the README of this server)."
)


class Chunk(TypedDict):
    rank: int
    source: str
    headers: list[str]
    text: str


def _body(hit: dict) -> str:
    """The text of a chunk without its first line, which repeats the path and the headers that come in their own fields."""
    prefix = " > ".join([hit["source"].removesuffix(".md"), *hit["headers"]]) + "\n"
    return hit["text"].removeprefix(prefix)


def create_server(search: SearchFn, check_setup: Callable[[], SetupReport]) -> FastMCP:
    server = FastMCP("gcp_rag_mcp", instructions=INSTRUCTIONS)

    @server.tool(
        name="gcp_rag_search_course",
        annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False),
    )
    def gcp_rag_search_course(
        question: Annotated[str, Field(min_length=1, max_length=MAX_QUESTION_CHARS, description="The question, as the user asked it.")],
        translation: Annotated[
            str,
            Field(
                min_length=1,
                max_length=MAX_QUESTION_CHARS,
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
            logger.exception("The course search failed")  # the detail stays on the server (stderr), not in the answer
            raise ToolError(SEARCH_FAILED.format(kind=type(error).__name__)) from error
        return [Chunk(rank=rank, source=h["source"], headers=h["headers"], text=_body(h)) for rank, h in enumerate(hits, 1)]

    @server.tool(
        name="gcp_rag_check_setup",
        annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False),
    )
    def gcp_rag_check_setup() -> SetupReport:
        """Check that the model files and the database of the course search are ready, and say how to set up what is missing.

        Returns `ready`, one check per piece (model, database) with its detail, and a guide with where to get each piece:
        the database container image, the model files, and the repositories of the RAG and of this server. Call it when a
        search fails or before the first search of a session.
        """
        return check_setup()

    return server
