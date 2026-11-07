import pytest

from gcp_rag_mcp.retriever import LazyRetriever


class FakeConnection:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


class Loader:
    """Counts how many times the embedder and the connection are opened, and can make the search fail."""

    def __init__(self):
        self.embedders = 0
        self.connections = []
        self.searches = []
        self.fail_next = False

    def open_embedder(self):
        self.embedders += 1
        return object()

    def open_connection(self):
        self.connections.append(FakeConnection())
        return self.connections[-1]

    def make_retriever(self, connection, embedder):
        loader = self

        class FakeRetriever:
            def search_many(self, phrasings, k):
                if loader.fail_next:
                    loader.fail_next = False
                    raise RuntimeError("the connection was lost")
                loader.searches.append((connection, phrasings, k))
                return [{"text": "a chunk"}]

        return FakeRetriever()


@pytest.fixture
def loader():
    return Loader()


@pytest.fixture
def retriever(loader):
    return LazyRetriever(loader.open_embedder, loader.open_connection, loader.make_retriever)


def test_nothing_is_loaded_until_the_first_search(loader, retriever):
    assert loader.embedders == 0 and loader.connections == []


def test_the_embedder_and_the_connection_are_opened_once_and_reused(loader, retriever):
    retriever.search(["una pregunta", "a question"], 30)
    retriever.search(["otra pregunta", "another question"], 30)

    assert loader.embedders == 1
    assert len(loader.connections) == 1
    assert len(loader.searches) == 2


def test_the_search_receives_the_phrasings_and_the_number_of_chunks(loader, retriever):
    hits = retriever.search(["una pregunta", "a question"], 12)

    assert hits == [{"text": "a chunk"}]
    assert loader.searches[0][1:] == (["una pregunta", "a question"], 12)


def test_after_a_failure_the_connection_is_closed_and_reopened_but_the_embedder_is_kept(loader, retriever):
    retriever.search(["una pregunta", "a question"], 30)
    loader.fail_next = True

    with pytest.raises(RuntimeError):
        retriever.search(["otra pregunta", "another question"], 30)
    retriever.search(["una más", "one more"], 30)

    assert loader.connections[0].closed is True
    assert len(loader.connections) == 2
    assert loader.embedders == 1
