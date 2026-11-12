"""Download the files of a model into the models folder of the rag repository, checking the weights."""

import hashlib
from collections.abc import Callable
from pathlib import Path
from urllib.request import urlopen

from gcp_rag_mcp.catalog import ModelOption

CHUNK_BYTES = 1 << 20
PROGRESS_EVERY_BYTES = 50 << 20


def download_model(option: ModelOption, models_dir: Path, opener: Callable = urlopen, say: Callable = print) -> Path:
    """Fetch the files that are missing or damaged and return the model folder. A file that is complete is left alone."""
    folder = Path(models_dir) / option.folder
    for name in option.files:
        target = folder / name
        if _is_complete(option, name, target):
            continue
        say(f"downloading {name} from {option.source_url} ...")
        _fetch(option, name, target, opener, say)
    return folder


def _is_complete(option: ModelOption, name: str, target: Path) -> bool:
    if not target.is_file():
        return False
    return name != option.onnx_file or _sha256_of(target) == option.onnx_sha256


def _sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(CHUNK_BYTES):
            digest.update(chunk)
    return digest.hexdigest()


def _fetch(option: ModelOption, name: str, target: Path, opener: Callable, say: Callable) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(target.name + ".part")
    digest, received, announced = hashlib.sha256(), 0, 0
    try:
        with opener(f"{option.source_url}/resolve/{option.revision}/{name}") as response, partial.open("wb") as out:
            while chunk := response.read(CHUNK_BYTES):
                out.write(chunk)
                digest.update(chunk)
                received += len(chunk)
                if received - announced >= PROGRESS_EVERY_BYTES:
                    announced = received
                    say(f"  {received >> 20} MB")
        if name == option.onnx_file and digest.hexdigest() != option.onnx_sha256:
            raise ValueError(f"sha256 of {name} is {digest.hexdigest()}, expected {option.onnx_sha256}")
        partial.replace(target)
    finally:
        partial.unlink(missing_ok=True)  # nothing half downloaded stays behind, whatever went wrong
