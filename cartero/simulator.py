from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from cartero.validator import Change


MAX_PREVIEW_LINES = 3
MAX_PREVIEW_LINE_LENGTH = 80


@dataclass(frozen=True)
class SimulatedAction:
    repo: str
    summary: str
    details: tuple[str, ...] = ()


def simulate_actions(changes: Iterable[Change]) -> tuple[SimulatedAction, ...]:
    simulated: list[SimulatedAction] = []

    for change in changes:
        if change.change_type == "write":
            assert change.content is not None
            size = len(change.content.encode("utf-8"))
            simulated.append(
                SimulatedAction(
                    repo=change.repo,
                    summary=f"simulate write file: {change.path} ({size} bytes)",
                    details=("content preview:", *_indent_preview(_build_content_preview(change.content))),
                )
            )
            continue

        if change.change_type == "delete":
            simulated.append(
                SimulatedAction(
                    repo=change.repo,
                    summary=f"simulate delete file: {change.path}",
                )
            )
            continue

        simulated.append(
            SimulatedAction(
                repo=change.repo,
                summary=f"simulate mkdir dir: {change.path}",
            )
        )

    return tuple(simulated)


def _build_content_preview(content: str) -> tuple[str, ...]:
    lines = content.splitlines() or [content]
    preview_lines = [_truncate_line(line) for line in lines[:MAX_PREVIEW_LINES]]

    if len(lines) > MAX_PREVIEW_LINES:
        preview_lines.append("...")

    return tuple(preview_lines)


def _indent_preview(lines: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(f"  {line}" for line in lines)


def _truncate_line(line: str) -> str:
    if len(line) <= MAX_PREVIEW_LINE_LENGTH:
        return line
    return f"{line[: MAX_PREVIEW_LINE_LENGTH - 3]}..."
