from pathlib import Path

import pytest

from gcp_rag_mcp.catalog import MODELS
from gcp_rag_mcp.config import Settings
from gcp_rag_mcp.setup_check import run_checks

MODEL_FILES = MODELS["bge-m3"].files


class FakeConnection:
    def __init__(self, chunks=5):
        self.chunks = chunks
        self.closed = False

    def execute(self, sql):
        assert "chunks" in sql
        return self

    def fetchone(self):
        return (self.chunks,)

    def close(self):
        self.closed = True


@pytest.fixture
def model_dir(tmp_path) -> Path:
    for name in MODEL_FILES:
        file = tmp_path / name
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_bytes(b"x")
    return tmp_path


def settings(model_dir: Path) -> Settings:
    return Settings(database_url="postgresql://rag:secret-password@10.0.0.5:5433/courses_bge", model_dir=model_dir)


def by_name(report) -> dict:
    return {check["name"]: check for check in report["checks"]}


def test_everything_in_place_is_ready_and_the_connection_is_closed(model_dir):
    connection = FakeConnection(chunks=1728)

    report = run_checks(settings(model_dir), lambda url: connection)

    assert report["ready"] is True
    assert [c["ok"] for c in report["checks"]] == [True, True]
    assert "1728" in by_name(report)["database"]["detail"]
    assert connection.closed


def test_missing_model_files_are_named_and_the_server_is_not_ready(tmp_path):
    (tmp_path / "tokenizer.json").write_bytes(b"x")

    report = run_checks(settings(tmp_path), lambda url: FakeConnection())

    model = by_name(report)["model"]
    assert report["ready"] is False and model["ok"] is False
    assert "onnx/model_int8.onnx" in model["detail"] and "config.json" in model["detail"]
    assert "tokenizer.json" not in model["detail"]
    assert by_name(report)["database"]["ok"] is True


def test_an_unreachable_database_is_reported_without_its_internal_detail(model_dir):
    def broken(url):
        raise ConnectionRefusedError("password=secret-password host=10.0.0.5")

    report = run_checks(settings(model_dir), broken)

    database = by_name(report)["database"]
    assert report["ready"] is False and database["ok"] is False
    assert "ConnectionRefusedError" in database["detail"]
    assert "secret-password" not in database["detail"] and "10.0.0.5" not in database["detail"]
    assert by_name(report)["model"]["ok"] is True


def test_an_empty_index_is_not_ready(model_dir):
    report = run_checks(settings(model_dir), lambda url: FakeConnection(chunks=0))

    assert report["ready"] is False
    assert "empty" in by_name(report)["database"]["detail"]


def test_the_guide_says_where_to_get_each_piece_and_where_the_model_goes(model_dir):
    guide = run_checks(settings(model_dir), lambda url: FakeConnection())["guide"]

    for piece in (
        "ghcr.io/estvn/gcp-rag-db:bge-m3",
        "https://github.com/estvn/GCP-ANALYTICS_RAG",
        "https://github.com/estvn/GCP-ANALYTICS_RAG_MCP",
        "https://huggingface.co/onnx-community/bge-m3-ONNX",
        "podman start rag-db-bge",
        "./setup.sh",
        "python -m gcp_rag_mcp switch",
        str(model_dir),
    ):
        assert piece in guide
    assert "secret-password" not in guide


def test_with_the_light_model_the_checks_and_the_guide_talk_about_its_files_image_and_container(tmp_path):
    e5 = MODELS["e5-small"]
    for name in e5.files:
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_bytes(b"x")

    report = run_checks(Settings(database_url="postgresql://rag@h/courses_e5", model_dir=tmp_path, model=e5), lambda url: FakeConnection())

    assert report["ready"] is True and "e5-small" in by_name(report)["model"]["detail"]
    for piece in (e5.image, "podman start rag-db-e5", "https://huggingface.co/Xenova/multilingual-e5-small", "model_quantized.onnx"):
        assert piece in report["guide"]
    assert "ghcr.io/estvn/gcp-rag-db:bge-m3" not in report["guide"]
