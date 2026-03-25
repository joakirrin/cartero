from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path
from typing import Iterable, Sequence

from cartero.parser import ParseError, load_summary
from cartero.validator import ALLOWED_REPOS, Change, ValidationError, validate_summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cartero",
        description="Validate an actions YAML file and print a dry-run repo plan.",
    )
    parser.add_argument("summary", help="Path to the YAML summary file.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        raw_summary = load_summary(args.summary)
        summary = validate_summary(raw_summary)
    except (ParseError, ValidationError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(render_plan(Path(args.summary), summary.actions))
    return 0


def render_plan(summary_path: Path, changes: Iterable[Change]) -> str:
    grouped: dict[str, list[Change]] = defaultdict(list)
    total_changes = 0

    for change in changes:
        grouped[change.repo].append(change)
        total_changes += 1

    lines = [
        "Cartero dry-run plan",
        f"Summary file: {summary_path}",
        "Mode: dry-run only",
        "Repo routing: explicit repo field required for every action",
        f"Validated actions: {total_changes}",
        "",
    ]

    for repo in ALLOWED_REPOS:
        repo_changes = grouped.get(repo)
        if not repo_changes:
            continue
        lines.append(f"{repo} ({len(repo_changes)} action{'s' if len(repo_changes) != 1 else ''})")
        for change in repo_changes:
            lines.append(f"  - {_describe_change(change)}")
        lines.append("")

    lines.append("No file or git changes were made.")
    return "\n".join(lines)


def _describe_change(change: Change) -> str:
    if change.change_type == "write":
        assert change.content is not None
        size = len(change.content.encode("utf-8"))
        return f"write {change.path} ({size} bytes)"
    if change.change_type == "delete":
        return f"delete {change.path}"
    return f"mkdir {change.path}"
