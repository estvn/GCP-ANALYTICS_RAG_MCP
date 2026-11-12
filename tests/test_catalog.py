import re

import pytest

from gcp_rag_mcp.catalog import DEFAULT_MODEL, MODELS, get_model


def test_both_models_say_where_to_download_them_and_how_to_verify_the_file():
    assert set(MODELS) == {"bge-m3", "e5-small"}
    for option in MODELS.values():
        assert option.source_url.startswith("https://huggingface.co/")
        assert re.fullmatch(r"[0-9a-f]{40}", option.revision)
        assert re.fullmatch(r"[0-9a-f]{64}", option.onnx_sha256)
        assert option.onnx_file in option.files and "tokenizer.json" in option.files


def test_each_model_has_its_own_database_image_and_vector_size():
    bge, e5 = MODELS["bge-m3"], MODELS["e5-small"]

    assert (bge.database, bge.image, bge.dim) == ("courses_bge", "ghcr.io/estvn/gcp-rag-db:bge-m3", 1024)
    assert (e5.database, e5.image, e5.dim) == ("courses_e5", "ghcr.io/estvn/gcp-rag-db:e5-small", 384)
    assert bge.container != e5.container and bge.volume != e5.volume  # switching never touches the other index


def test_the_default_is_bge_m3_and_an_unknown_model_lists_the_valid_ones():
    assert DEFAULT_MODEL == "bge-m3"
    assert get_model("e5-small").key == "e5-small"
    with pytest.raises(ValueError, match="bge-m3, e5-small"):
        get_model("gpt")
