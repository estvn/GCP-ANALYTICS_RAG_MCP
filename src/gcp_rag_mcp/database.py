"""Start the Podman container that holds the index of a model. Containers and volumes are never removed."""

import subprocess
import time
from collections.abc import Callable

from gcp_rag_mcp.catalog import MODELS, ModelOption

PORT = "127.0.0.1:5433:5432"  # both indexes use the same port, so only one container runs at a time
LEGACY_CONTAINER = "rag-db"  # the name `setup.sh` and the README used before there were two models
KNOWN_CONTAINERS = (LEGACY_CONTAINER, *(option.container for option in MODELS.values()))
POLL_SECONDS = 2


def podman(args: list[str]) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(["podman", *args], capture_output=True, text=True, check=False)
    except FileNotFoundError:
        raise RuntimeError("podman is not installed (https://podman.io)") from None


def ensure_database(
    option: ModelOption, run: Callable = podman, say: Callable = print, sleep: Callable = time.sleep, tries: int = 60
) -> None:
    """Leave the container of `option` running and answering, stopping the other one if it holds the port."""
    for name in KNOWN_CONTAINERS:
        if name != option.container and _status(name, run).startswith("Up"):
            say(f"stopping {name}: it uses the same port (its data is kept)")
            _checked(["stop", name], run)
    status = _status(option.container, run)
    if not status:
        say(f"creating {option.container} from {option.image} (the first start restores the index, a few seconds) ...")
        _checked(
            [
                "run", "-d", "--pull=newer", "--name", option.container, "-p", PORT,
                "-v", f"{option.volume}:/var/lib/postgresql/data", option.image,
            ],
            run,
        )
    elif not status.startswith("Up"):
        say(f"starting {option.container} ...")
        _checked(["start", option.container], run)
    _wait_until_ready(option, run, sleep, tries)


def _status(name: str, run: Callable) -> str:
    return run(["ps", "-a", "--filter", f"name=^{name}$", "--format", "{{.Status}}"]).stdout.strip()


def _checked(args: list[str], run: Callable) -> None:
    result = run(args)
    if result.returncode != 0:
        raise RuntimeError(f"podman {' '.join(args[:2])} failed: {result.stderr.strip()}")


def _wait_until_ready(option: ModelOption, run: Callable, sleep: Callable, tries: int) -> None:
    for _ in range(tries):
        if run(["exec", option.container, "pg_isready", "-h", "127.0.0.1", "-U", "rag"]).returncode == 0:
            return
        sleep(POLL_SECONDS)
    raise RuntimeError(f"{option.container} did not answer after {tries * POLL_SECONDS} seconds: see `podman logs {option.container}`")
