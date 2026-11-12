import pytest

from gcp_rag_mcp import cli
from gcp_rag_mcp.catalog import MODELS
from gcp_rag_mcp.preferences import load_model


class Recorder:
    def __init__(self):
        self.downloaded, self.databases, self.said = [], [], []

    def download(self, option):
        self.downloaded.append(option.key)

    def database(self, option):
        self.databases.append(option.key)

    def say(self, *parts):
        self.said.append(" ".join(str(p) for p in parts))

    @property
    def text(self):
        return "\n".join(self.said)


def run(argv, tmp_path, answers=(), recorder=None):
    rec = recorder or Recorder()
    env = {"RAG_MCP_HOME": str(tmp_path)}
    replies = iter(answers)
    tools = cli.Tools(
        ask=lambda _prompt: next(replies),
        say=rec.say,
        download=rec.download,
        database=rec.database,
        status=lambda settings: rec.say("status for", settings.model.key),
    )
    code = cli.main(argv, env=env, tools=tools)
    return code, rec, env


def test_setup_explains_both_models_and_asks_which_one_to_install(tmp_path):
    code, rec, env = run(["setup"], tmp_path, answers=["2"])

    assert code == 0
    for option in MODELS.values():
        assert option.key in rec.text and option.title in rec.text and option.summary in rec.text
    assert (rec.downloaded, rec.databases, load_model(env)) == (["e5-small"], ["e5-small"], "e5-small")


def test_the_choice_can_be_typed_as_the_name_and_an_invalid_answer_asks_again(tmp_path):
    code, rec, env = run(["setup"], tmp_path, answers=["9", "gpt", "BGE-M3"])

    assert code == 0 and load_model(env) == "bge-m3"
    assert "not an option" in rec.text


def test_setup_does_not_install_anything_if_nobody_chooses(tmp_path):
    code, rec, env = run(["setup"], tmp_path, answers=[""] * 3)

    assert code == 1 and rec.downloaded == [] and load_model(env) is None


def test_setup_with_the_model_flag_does_not_ask(tmp_path):
    code, rec, _ = run(["setup", "--model", "e5-small"], tmp_path)

    assert code == 0 and rec.downloaded == ["e5-small"]


def test_switch_installs_the_other_model_and_remembers_it(tmp_path):
    _, _, env = run(["setup", "--model", "bge-m3"], tmp_path)

    code, rec, _ = run(["switch", "--model", "e5-small"], tmp_path)

    assert code == 0 and rec.downloaded == ["e5-small"] and rec.databases == ["e5-small"] and load_model(env) == "e5-small"
    assert "restart" in rec.text.lower()  # the client keeps the old model until the server restarts


def test_switch_to_the_model_already_in_use_does_nothing(tmp_path):
    run(["setup", "--model", "e5-small"], tmp_path)

    code, rec, _ = run(["switch", "--model", "e5-small"], tmp_path)

    assert code == 0 and rec.downloaded == [] and "already" in rec.text


def test_switch_without_a_flag_offers_only_the_model_not_in_use(tmp_path):
    run(["setup", "--model", "bge-m3"], tmp_path)

    code, _, env = run(["switch"], tmp_path, answers=["1"])

    assert code == 0 and load_model(env) == "e5-small"


def test_help_lists_the_commands_and_an_unknown_command_fails(tmp_path, capsys):
    code, rec, _ = run(["help"], tmp_path)
    assert code == 0
    for command in ("setup", "switch", "status", "help"):
        assert command in rec.text
    with pytest.raises(SystemExit):
        cli.main(["nope"], env={})
    assert "invalid choice" in capsys.readouterr().err


def test_status_reports_on_the_model_in_use(tmp_path):
    run(["setup", "--model", "e5-small"], tmp_path)

    code, rec, _ = run(["status"], tmp_path)

    assert code == 0 and "status for e5-small" in rec.text


def test_status_exits_with_1_when_something_is_missing(tmp_path):
    tools = cli.Tools(say=lambda *_: None, status=lambda settings: False)

    assert cli.main(["status"], env={"RAG_MCP_HOME": str(tmp_path)}, tools=tools) == 1


def test_a_failed_download_keeps_the_previous_choice_and_does_not_start_the_database(tmp_path):
    _, _, env = run(["setup", "--model", "bge-m3"], tmp_path)
    rec = Recorder()

    def broken(option):
        raise ValueError("sha256 mismatch")

    tools = cli.Tools(say=rec.say, download=broken, database=rec.database)
    code = cli.main(["switch", "--model", "e5-small"], env=env, tools=tools)

    assert code == 1 and load_model(env) == "bge-m3" and rec.databases == [] and "sha256 mismatch" in rec.text
