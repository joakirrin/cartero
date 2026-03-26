from __future__ import annotations

import argparse
from collections import defaultdict
from pathlib import Path
from typing import Iterable, Sequence

from rich.console import Console, Group
from rich.panel import Panel
from rich.text import Text

from cartero.executor import execute_actions
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
        description="Validate an actions YAML file and print a dry-run repo plan.",
    )
    mode_group = parser.add_mutually_exclusive_group()
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
    parser.add_argument("summary", help="Path to the YAML summary file.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    console = Console()
    error_console = Console(stderr=True)
    mode = "apply" if args.apply else "dry-run"
    # Explicitly ignore args.dry_run because default mode is already dry-run.

    try:
        raw_summary = load_summary(args.summary)
        summary = validate_summary(raw_summary)
    except (ParseError, ValidationError) as exc:
        error_console.print(Text.assemble(("error: ", "red"), (str(exc),)))
        return 2

    render_plan(Path(args.summary), summary.actions, mode, console=console)
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
