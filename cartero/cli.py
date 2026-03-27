from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path
from typing import Iterable, Sequence

import yaml
from rich.console import Console, Group
from rich.panel import Panel
from rich.text import Text

from cartero.executor import execute_actions
from cartero.generator import generate_context_recap, generate_summary_result_from_diff
from cartero.git import (
    GitError,
    commit as git_commit,
    get_changed_files,
    get_diff,
    stage_files,
)
from cartero.llm import LLMCallError, LLMConfigError
from cartero.parser import ParseError, load_summary
from cartero.simulator import SimulatedAction, simulate_actions
from cartero.validator import ALLOWED_REPOS, Change, ValidationError, validate_summary

VALID_MODES = {"dry-run", "apply"}
ACTION_STYLES = {
    "write": "blue",
    "delete": "red",
    "mkdir": "yellow",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cartero",
        description="Validate Cartero summaries or generate them from a diff.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser(
        "run",
        prog="cartero",
        help="Validate an actions YAML file and print a repo plan.",
    )
    mode_group = run_parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview the execution plan without making changes.",
    )
    mode_group.add_argument(
        "--apply",
        action="store_true",
        help="Apply the changes described in the summary file.",
    )
    run_parser.add_argument("summary", help="Path to the YAML summary file.")
    run_parser.set_defaults(handler=handle_run)

    generate_parser = subparsers.add_parser(
        "generate",
        prog="cartero generate",
        help="Generate a Cartero YAML summary from a diff.",
    )
    generate_diff_source = generate_parser.add_mutually_exclusive_group()
    generate_diff_source.add_argument(
        "--diff-file",
        metavar="PATH",
        help="Path to a file containing the diff.",
    )
    generate_diff_source.add_argument(
        "--stdin",
        action="store_true",
        help="Read the diff from stdin instead of detecting it from git.",
    )
    generate_parser.add_argument(
        "--context-file",
        metavar="PATH",
        help="Optional path to raw context. Cartero will compress it before generation.",
    )
    generate_parser.set_defaults(handler=handle_generate)

    context_parser = subparsers.add_parser(
        "context",
        prog="cartero context",
        help="Compress raw notes or conversation context into a structured recap.",
    )
    context_parser.add_argument(
        "--context-file",
        metavar="PATH",
        help="Path to a file containing raw context. Reads from stdin when omitted.",
    )
    context_parser.set_defaults(handler=handle_context)

    commit_parser = subparsers.add_parser(
        "commit",
        prog="cartero commit",
        help="Stage selected files, generate a summary, and create a git commit.",
    )
    commit_parser.add_argument(
        "--context-file",
        metavar="PATH",
        help="Optional path to raw context. Cartero will compress it before generation.",
    )
    commit_parser.set_defaults(handler=handle_commit)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(_normalize_argv(argv))
    console = Console()
    error_console = Console(stderr=True)
    return args.handler(args, console, error_console)


def handle_run(args: argparse.Namespace, console: Console, error_console: Console) -> int:
    mode = "apply" if args.apply else "dry-run"
    try:
        raw_summary = load_summary(args.summary)
        summary = validate_summary(raw_summary)
    except (ParseError, ValidationError) as exc:
        error_console.print(Text.assemble(("error: ", "red"), (str(exc),)))
        return 2
    render_plan(Path(args.summary), summary.actions, mode, console=console)
    return 0


def handle_generate(
    args: argparse.Namespace, console: Console, error_console: Console
) -> int:
    try:
        diff_text = _resolve_generate_diff(args)
        raw_context = _read_optional_text_input(_get_arg_value(args, "context_file"))
        result = generate_summary_result_from_diff(diff_text, raw_context=raw_context)
    except NoDiffError as exc:
        console.print(str(exc))
        return 0
    except GitError as exc:
        error_console.print(Text.assemble(("error: ", "red"), (str(exc),)))
        return 2
    except (LLMConfigError, LLMCallError, ValueError) as exc:
        error_console.print(Text.assemble(("error: ", "red"), (str(exc),)))
        return 2
    if result.warning_message:
        error_console.print(Text.assemble(("warning: ", "yellow"), (result.warning_message,)))
    console.print(result.yaml_text, markup=False, end="")
    return 0


def handle_context(
    args: argparse.Namespace, console: Console, error_console: Console
) -> int:
    try:
        raw_context = _read_text_input(_get_arg_value(args, "context_file"))
        recap = generate_context_recap(raw_context)
    except (LLMConfigError, LLMCallError, ValueError) as exc:
        error_console.print(Text.assemble(("error: ", "red"), (str(exc),)))
        return 2
    console.print(recap, markup=False, end="")
    return 0


def handle_commit(
    args: argparse.Namespace, console: Console, error_console: Console
) -> int:
    try:
        changed_files = get_changed_files()
    except GitError as exc:
        error_console.print(Text.assemble(("error: ", "red"), (str(exc),)))
        return 2

    if not changed_files:
        console.print("Nothing to commit. Working tree clean.")
        return 0

    console.print("Changed files:")
    for index, path in enumerate(changed_files, start=1):
        console.print(f"{index}. {path}")

    console.print('Stage files (numbers separated by spaces, or "a" for all): ', end="")
    selection = input().strip()

    if not selection:
        error_console.print(Text.assemble(("error: ", "red"), ("Invalid file selection",)))
        return 2

    if selection.lower() in {"a", "all"}:
        selected_paths = changed_files
    else:
        selected_paths: list[str] = []
        seen_indexes: set[int] = set()
        try:
            for token in selection.split():
                selected_index = int(token)
                if selected_index < 1 or selected_index > len(changed_files):
                    raise ValueError
                if selected_index in seen_indexes:
                    continue
                seen_indexes.add(selected_index)
                selected_paths.append(changed_files[selected_index - 1])
        except ValueError:
            error_console.print(Text.assemble(("error: ", "red"), ("Invalid file selection",)))
            return 2

        if not selected_paths:
            error_console.print(Text.assemble(("error: ", "red"), ("Invalid file selection",)))
            return 2

    try:
        stage_files(selected_paths)
    except GitError as exc:
        error_console.print(Text.assemble(("error: ", "red"), (str(exc),)))
        return 2

    try:
        diff_text = get_diff()
    except GitError as exc:
        error_console.print(Text.assemble(("error: ", "red"), (str(exc),)))
        return 2

    try:
        raw_context = _read_optional_text_input(_get_arg_value(args, "context_file"))
        with console.status("Generating commit summary…"):
            result = generate_summary_result_from_diff(diff_text, raw_context=raw_context)
    except (LLMConfigError, LLMCallError, ValueError) as exc:
        error_console.print(Text.assemble(("error: ", "red"), (str(exc),)))
        return 2

    if result.warning_message:
        error_console.print(Text.assemble(("warning: ", "yellow"), (result.warning_message,)))

    console.print(result.yaml_text, markup=False)
    console.print("Commit with this summary? [y/N]: ", end="")
    confirmation = input().strip()

    if confirmation.lower() not in {"y", "yes"}:
        console.print("Aborted.")
        return 0

    try:
        data = yaml.safe_load(result.yaml_text)
    except yaml.YAMLError as exc:
        error_console.print(Text.assemble(("error: ", "red"), (str(exc),)))
        return 2

    subject = ""
    body = None
    if isinstance(data, dict):
        subject = str(data.get("summary", "")).strip()
        body_text = str(data.get("reason", "")).strip()
        body = body_text or None

    if not subject:
        subject = "chore: update files"

    try:
        commit_hash = git_commit(subject, body)
    except GitError as exc:
        error_console.print(Text.assemble(("error: ", "red"), (str(exc),)))
        return 2

    console.print(f"✓ Committed: {commit_hash}")
    return 0


def render_plan(
    summary_path: Path,
    changes: Iterable[Change],
    mode: str,
    *,
    console: Console | None = None,
) -> Group:
    if mode not in VALID_MODES:
        raise ValueError(f"Unsupported mode: {mode}")

    if console is None:
        console = Console()

    change_list = tuple(changes)
    grouped: dict[str, list[SimulatedAction]] = defaultdict(list)
    total_changes = 0

    for simulated_action in simulate_actions(change_list):
        grouped[simulated_action.repo].append(simulated_action)
        total_changes += 1

    renderables = [
        Panel.fit(
            Group(
                Text(f"Cartero {mode} plan"),
                Text(f"Summary file: {summary_path}"),
                Text(f"Mode: {_describe_mode(mode)}"),
                Text(f"Validated actions: {total_changes}"),
            ),
            title="Cartero",
        )
    ]

    for repo in ALLOWED_REPOS:
        repo_changes = grouped.get(repo)
        if not repo_changes:
            continue
        action_label = f"{repo} ({len(repo_changes)} action{'s' if len(repo_changes) != 1 else ''})"
        repo_lines: list[Text] = [Text(action_label)]
        for simulated_action in repo_changes:
            repo_lines.extend(_render_simulated_action(simulated_action))
        renderables.append(Panel(Group(*repo_lines), title=repo))

    plan = Group(*renderables)
    console.print(plan)

    if mode == "dry-run":
        console.print(_build_status_line())
        return plan

    console.rule("Simulated execution")
    execute_actions(change_list, console=console)
    return plan


def _describe_mode(mode: str) -> str:
    if mode == "apply":
        return "apply"
    return "dry-run"


def _normalize_argv(argv: Sequence[str] | None) -> list[str]:
    args = list(sys.argv[1:] if argv is None else argv)
    SUBCOMMANDS = {"run", "generate", "context", "commit"}
    if args and args[0] in SUBCOMMANDS:
        return args
    return ["run", *args]


def _read_diff_text(diff_file: str | None) -> str:
    return _read_text_input(diff_file)


def _resolve_generate_diff(args: argparse.Namespace) -> str:
    diff_file = args.diff_file
    if diff_file is not None:
        return _read_diff_text(diff_file)
    if bool(_get_arg_value(args, "stdin")):
        return _read_text_input(None)

    diff_text = get_diff()
    if diff_text.strip():
        return diff_text
    raise NoDiffError("No changes detected. You can paste a diff or make changes first.")


def _read_text_input(path: str | None) -> str:
    if path is None:
        return sys.stdin.read()
    try:
        return Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"Unable to read input file {path}: {exc}") from exc


def _read_optional_text_input(path: str | None) -> str | None:
    if path is None:
        return None
    return _read_text_input(path)


def _get_arg_value(args: argparse.Namespace, name: str) -> object | None:
    return vars(args).get(name)


class NoDiffError(ValueError):
    pass


def _build_status_line() -> Text:
    return Text("No file or git changes were made.", style="green")


def _render_simulated_action(simulated_action: SimulatedAction) -> list[Text]:
    style = ACTION_STYLES[_get_action_type(simulated_action)]
    lines = [Text(f"- {simulated_action.summary}", style=style)]

    for detail in simulated_action.details:
        lines.append(Text(f"  {detail}", style="dim"))

    return lines


def _get_action_type(simulated_action: SimulatedAction) -> str:
    if simulated_action.summary.startswith("simulate write "):
        return "write"
    if simulated_action.summary.startswith("simulate delete "):
        return "delete"
    if simulated_action.summary.startswith("simulate mkdir "):
        return "mkdir"
    raise ValueError(f"Unsupported simulated action summary: {simulated_action.summary}")
