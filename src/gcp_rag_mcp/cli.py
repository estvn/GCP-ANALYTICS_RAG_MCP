"""Commands that install and change the model: `python -m gcp_rag_mcp setup | switch | status | help`."""

import argparse
import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from gcp_rag_mcp.catalog import MODELS, ModelOption, get_model
from gcp_rag_mcp.config import MODELS_DIR, Settings
from gcp_rag_mcp.database import ensure_database
from gcp_rag_mcp.downloads import download_model
from gcp_rag_mcp.preferences import save_model
from gcp_rag_mcp.setup_check import run_checks

HELP = """Commands (python -m gcp_rag_mcp <command>); with no command it runs the MCP server over stdio:

  setup [--model NAME]   First install. Explains the models and asks which one you want (or pass --model), then downloads
                         that model and the database image already loaded with the course indexed by it, and starts
                         the database.
  switch [--model NAME]  Change to the other model: downloads its files and its database image, stops the other database
                         (its data is kept) and remembers the choice. Restart the MCP server afterwards.
  status                 Shows the model in use and whether its files and its database are ready.
  help                   Shows this text.

Models: {models}.  RAG_MODEL=<name> in the environment overrides the saved choice.
"""
MAX_ATTEMPTS = 3


def _download(option: ModelOption) -> None:
    download_model(option, MODELS_DIR)


def _show_status(settings: Settings, say: Callable = print) -> bool:
    report = run_checks(settings)
    say(f"model in use: {settings.model.title}")
    for check in report["checks"]:
        say(f"  [{'ok' if check['ok'] else 'missing'}] {check['name']}: {check['detail']}")
    if not report["ready"]:
        say(f"\n{report['guide']}")
    return report["ready"]


@dataclass(frozen=True)
class Tools:
    """What the commands use from the outside world; the tests replace every one of them."""

    ask: Callable[[str], str] = input
    say: Callable[..., None] = print
    download: Callable[[ModelOption], None] = _download
    database: Callable[[ModelOption], None] = ensure_database
    status: Callable[[Settings], bool | None] = _show_status  # False when something is missing


def main(argv: list[str] | None = None, env: Mapping[str, str] | None = None, tools: Tools | None = None) -> int:
    env, tools = (os.environ if env is None else env), tools or Tools()
    args = _parser().parse_args(argv)
    if args.command == "help":
        tools.say(HELP.format(models=", ".join(MODELS)))
        return 0
    try:
        settings = Settings.from_env(env)
    except ValueError as error:
        tools.say(str(error))
        return 1
    if args.command == "status":
        return 0 if tools.status(settings) is not False else 1
    return _install(args, settings, env, tools)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m gcp_rag_mcp", description="Install and change the model of the server.")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("setup", "switch"):
        commands.add_parser(name).add_argument("--model", choices=list(MODELS), help="skip the question and use this model")
    commands.add_parser("status")
    commands.add_parser("help")
    return parser


def _install(args: argparse.Namespace, settings: Settings, env: Mapping[str, str], tools: Tools) -> int:
    if args.command == "switch" and args.model == settings.model.key:
        tools.say(f"already using {settings.model.key}: nothing to do.")
        return 0
    offered = [m for m in MODELS.values() if args.command == "setup" or m.key != settings.model.key]
    model = get_model(args.model) if args.model else _choose(offered, tools)
    if model is None:
        tools.say("No model chosen: nothing was installed.")
        return 1
    try:
        tools.say(f"Installing {model.key}: its model files, then the database image {model.image}.")
        tools.download(model)
        tools.database(model)
    except (RuntimeError, ValueError, OSError) as error:
        tools.say(f"failed, the previous choice is unchanged: {error}")
        return 1
    save_model(model.key, env)
    tools.say(f"Done: {model.key} is ready. Restart the MCP server to use it (in Claude Code: /mcp, or open a new session).")
    if env.get("RAG_MODEL") not in (None, "", model.key):
        tools.say(f"Note: RAG_MODEL={env['RAG_MODEL']} is set in your environment and wins over this choice: unset it.")
    return 0


def _choose(options: list[ModelOption], tools: Tools) -> ModelOption | None:
    tools.say("Which model do you want?\n")
    for number, option in enumerate(options, start=1):
        tools.say(f"  {number}. {option.key}: {option.title}\n     {option.summary}\n")
    for _ in range(MAX_ATTEMPTS):
        answer = tools.ask("Type the number or the name: ").strip().lower()
        by_number = options[int(answer) - 1] if answer.isdigit() and 1 <= int(answer) <= len(options) else None
        chosen = by_number or next((option for option in options if option.key == answer), None)
        if chosen:
            return chosen
        tools.say(f"{answer!r} is not an option.")
    return None
