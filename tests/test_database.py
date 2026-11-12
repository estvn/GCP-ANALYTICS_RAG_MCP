import subprocess

import pytest

from gcp_rag_mcp.catalog import MODELS
from gcp_rag_mcp.database import ensure_database

E5, BGE = MODELS["e5-small"], MODELS["bge-m3"]


class FakePodman:
    """Answers `podman ps` from a table of container states and records every other command."""

    def __init__(self, states=None, fail_on=None):
        self.states, self.commands, self.fail_on = states or {}, [], fail_on

    def __call__(self, args):
        if args[0] == "ps":
            name = next(a for a in args if a.startswith("name=^")).removeprefix("name=^").removesuffix("$")
            return subprocess.CompletedProcess(args, 0, self.states.get(name, ""), "")
        self.commands.append(args)
        failed = self.fail_on == args[0]
        return subprocess.CompletedProcess(args, 1 if failed else 0, "", "boom" if failed else "")


def ensure(fake, option=E5):
    ensure_database(option, run=fake, say=lambda *_: None, sleep=lambda _: None, tries=1)


def test_a_missing_container_is_created_from_the_image_of_the_model():
    fake = FakePodman()

    ensure(fake)

    created = next(c for c in fake.commands if c[0] == "run")
    assert E5.image in created and E5.container in created and E5.volume + ":/var/lib/postgresql/data" in created
    assert "127.0.0.1:5433:5432" in created
    assert "--pull=newer" in created  # a copy of the image already on the machine may hold an older index


def test_a_stopped_container_is_started_and_a_running_one_is_left_alone():
    stopped, running = FakePodman({E5.container: "Exited (0) 2 hours ago"}), FakePodman({E5.container: "Up 3 minutes"})

    ensure(stopped)
    ensure(running)

    assert ["start", E5.container] in stopped.commands
    assert not any(c[0] in {"start", "run"} for c in running.commands)


def test_the_container_of_the_other_model_is_stopped_because_both_use_the_same_port_but_never_removed():
    fake = FakePodman({BGE.container: "Up 1 hour", "rag-db": "Up 2 days", E5.container: "Up 1 minute"})

    ensure(fake)

    assert ["stop", BGE.container] in fake.commands and ["stop", "rag-db"] in fake.commands  # "rag-db" is the old name
    assert ["stop", E5.container] not in fake.commands
    assert not any(c[0] in {"rm", "volume"} for c in fake.commands)


def test_a_failing_podman_command_stops_with_its_message():
    with pytest.raises(RuntimeError, match="boom"):
        ensure(FakePodman(fail_on="run"))
