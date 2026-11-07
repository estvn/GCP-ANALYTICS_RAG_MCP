"""The retriever of the RAG, loaded on the first question and kept for the next ones."""

import contextlib
import threading
from collections.abc import Callable

from rag.embed import BGE_M3, Embedder
from rag.retrieval import HybridRetriever
from rag.store import connect

from gcp_rag_mcp.config import Settings


class LazyRetriever:
    """Opens the embedder and the database connection on the first search and reuses them afterwards.

    Loading bge-m3 takes seconds and about 1.1 GB, so it is not done until a question arrives. One search runs at a
    time: the connection is not meant to be shared by two searches at once.
    """

    def __init__(self, open_embedder: Callable, open_connection: Callable, make_retriever: Callable = HybridRetriever):
        self._open_embedder = open_embedder
        self._open_connection = open_connection
        self._make_retriever = make_retriever
        self._embedder = None
        self._connection = None
        self._lock = threading.Lock()

    def search(self, phrasings: list[str], k: int) -> list[dict]:
        with self._lock:
            try:
                return self._retriever().search_many(phrasings, k=k)
            except Exception:
                self._close_connection()  # it may have been lost: the next search opens a new one
                raise

    def _retriever(self):
        if self._embedder is None:
            self._embedder = self._open_embedder()
        if self._connection is None:
            self._connection = self._open_connection()
        return self._make_retriever(self._connection, self._embedder)

    def _close_connection(self) -> None:
        if self._connection is not None:
            with contextlib.suppress(Exception):  # a broken connection may not close cleanly; it is dropped anyway
                self._connection.close()
            self._connection = None


def build_retriever(settings: Settings) -> LazyRetriever:
    return LazyRetriever(
        open_embedder=lambda: Embedder(settings.model_dir, BGE_M3),
        open_connection=lambda: connect(settings.database_url),
    )
