from __future__ import annotations

# TODO: replace _execute() with real filesystem + git operations
# When ready:
#   write  -> write content to repo path, then git add + git commit
#   delete -> delete file from repo path, then git add + git commit
#   mkdir  -> create directory in repo path (no commit needed)

from dataclasses import dataclass
from typing import Iterable

from rich.console import Console
from rich.text import Text

from cartero.validator import Change


ACTION_STYLES = {
    "write": "blue",
    "delete": "red",
    "mkdir": "yellow",
}


@dataclass(frozen=True)
class ExecutionResult:
    repo: str
    change_type: str
    path: str
    status: str


def execute_actions(
    changes: Iterable[Change],
    console: Console | None = None,
) -> list[ExecutionResult]:
    active_console = console or Console()
    results: list[ExecutionResult] = []

    for change in changes:
        results.append(_execute(change, console=active_console))

    active_console.print("[yellow]⚠ Execution is simulated — no files were written.[/yellow]")
    return results


def _execute(change: Change, console: Console) -> ExecutionResult:
    style = ACTION_STYLES.get(change.change_type, "white")

    line = Text("[executing] ")
    line.append(change.change_type, style=style)
    line.append(f" -> {change.path}")
    console.print(line)

    return ExecutionResult(
        repo=change.repo,
        change_type=change.change_type,
        path=change.path,
        status="simulated",
    )
