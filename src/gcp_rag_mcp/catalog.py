"""The models the server can run with: where each one is downloaded from and which database image holds its index."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelOption:
    key: str  # the name used in RAG_MODEL and in the commands; also the key of `rag.embed.MODELS`
    title: str
    summary: str
    source_url: str  # Hugging Face repository the files come from
    revision: str  # commit of that repository: the files cannot change under the index
    files: tuple[str, ...]  # paths inside the repository, kept with the same paths inside `folder`
    onnx_file: str
    onnx_sha256: str  # of `onnx_file`; the index is only valid for the exact weights it was built with
    folder: str  # inside the models folder of the rag repository
    database: str  # inside the image
    image: str
    container: str
    volume: str
    dim: int


MODELS: dict[str, ModelOption] = {
    "bge-m3": ModelOption(
        key="bge-m3",
        title="bge-m3 (default)",
        summary="Best ranking of the two (experiment E33): it puts the correct passage higher. Model file 559 MB, "
        "about 1.1 GB of RAM while loaded, vectors of 1024 numbers.",
        source_url="https://huggingface.co/onnx-community/bge-m3-ONNX",
        revision="25b9af8e87a38eb120cfe87125383677b9cd309e",
        files=("onnx/model_int8.onnx", "tokenizer.json", "config.json"),
        onnx_file="onnx/model_int8.onnx",
        onnx_sha256="2237f770aad5c71bbc1fc2d361a57f9a37400574cc9eff32626f0cdb49234730",
        folder="bge-m3",
        database="courses_bge",
        image="ghcr.io/estvn/gcp-rag-db:bge-m3",
        container="rag-db-bge",
        volume="rag_pgdata_bge",
        dim=1024,
    ),
    "e5-small": ModelOption(
        key="e5-small",
        title="multilingual-e5-small (light)",
        summary="The light option: model file 130 MB, vectors of 384 numbers. It ranks the correct passage lower than "
        "bge-m3 (experiment E33); use it on a machine with little memory.",
        source_url="https://huggingface.co/Xenova/multilingual-e5-small",
        revision="761b726dd34fb83930e26aab4e9ac3899aa1fa78",
        files=("onnx/model_quantized.onnx", "tokenizer.json", "config.json"),
        onnx_file="onnx/model_quantized.onnx",
        onnx_sha256="f80102d3f2a1229f387d3c81909990d8945513e347b0eab049f7de3c6f98c193",
        folder="multilingual-e5-small",
        database="courses_e5",
        image="ghcr.io/estvn/gcp-rag-db:e5-small",
        container="rag-db-e5",
        volume="rag_pgdata_e5",
        dim=384,
    ),
}
DEFAULT_MODEL = "bge-m3"


def get_model(key: str) -> ModelOption:
    try:
        return MODELS[key.strip().lower()]
    except KeyError:
        raise ValueError(f"unknown model {key!r}; valid models: {', '.join(MODELS)}") from None
