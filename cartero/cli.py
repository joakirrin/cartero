from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path
from typing import Iterable, Sequence

from rich.console import Console, Group
from rich.panel import Panel
from rich.text import Text

from cartero.executor import execute_actions
from cartero.generator import generate_summary_result_from_diff
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
    generate_parser.add_argument(
        "--diff-file",
        metavar="PATH",
        help="Path to a file containing the diff. Reads from stdin when omitted.",
    )
    generate_parser.set_defaults(handler=handle_generate)
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
        diff_text = _read_diff_text(args.diff_file)
        result = generate_summary_result_from_diff(diff_text)
    except (LLMConfigError, LLMCallError, ValueError) as exc:
        error_console.print(Text.assemble(("error: ", "red"), (str(exc),)))
        return 2
    if result.warning_message:
        error_console.print(Text.assemble(("warning: ", "yellow"), (result.warning_message,)))
    console.print(result.yaml_text, markup=False, end="")
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
    if args and args[0] in {"run", "generate"}:
        return args
    return ["run", *args]


def _read_diff_text(diff_file: str | None) -> str:
    if diff_file is None:
        return sys.stdin.read()
    return Path(diff_file).read_text(encoding="utf-8")


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
