import hashlib
import io
from dataclasses import replace

import pytest

from gcp_rag_mcp.catalog import MODELS
from gcp_rag_mcp.downloads import download_model

ONNX = b"fake model weights"


def option_for(content=ONNX):
    return replace(MODELS["e5-small"], onnx_sha256=hashlib.sha256(content).hexdigest())


class FakeHub:
    def __init__(self, onnx=ONNX):
        self.onnx, self.urls = onnx, []

    def __call__(self, url):
        self.urls.append(url)
        return io.BytesIO(self.onnx if url.endswith(".onnx") else b"{}")


def test_it_downloads_every_file_of_the_model_from_the_pinned_revision(tmp_path):
    option, hub = option_for(), FakeHub()

    folder = download_model(option, tmp_path, opener=hub, say=lambda *_: None)

    assert folder == tmp_path / option.folder
    for name in option.files:
        assert (folder / name).is_file()
    assert all(f"/resolve/{option.revision}/" in url for url in hub.urls)


def test_a_file_that_is_already_there_is_not_downloaded_again(tmp_path):
    option, hub = option_for(), FakeHub()
    download_model(option, tmp_path, opener=hub, say=lambda *_: None)
    hub.urls.clear()

    download_model(option, tmp_path, opener=hub, say=lambda *_: None)

    assert hub.urls == []


def test_a_model_file_with_the_wrong_hash_is_rejected_and_leaves_nothing_behind(tmp_path):
    option = option_for()

    with pytest.raises(ValueError, match="sha256"):
        download_model(option, tmp_path, opener=FakeHub(onnx=b"corrupted"), say=lambda *_: None)

    assert not (tmp_path / option.folder / option.onnx_file).exists()
    assert not list(tmp_path.rglob("*.part"))


def test_a_corrupted_file_already_on_disk_is_downloaded_again(tmp_path):
    option, hub = option_for(), FakeHub()
    broken = tmp_path / option.folder / option.onnx_file
    broken.parent.mkdir(parents=True)
    broken.write_bytes(b"half a file")

    download_model(option, tmp_path, opener=hub, say=lambda *_: None)

    assert broken.read_bytes() == ONNX
