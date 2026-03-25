from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any


ALLOWED_REPOS = (
    "casadora-core",
    "casadora-services",
    "casadora-experiments",
    "cartero",
)
ALLOWED_ACTION_TYPES = ("write", "delete", "mkdir")
TOP_LEVEL_KEYS = frozenset({"actions"})


class ValidationError(ValueError):
    """Raised when a parsed summary does not match the contract."""


@dataclass(frozen=True)
class Change:
    repo: str
    change_type: str
    path: str
    content: str | None = None


@dataclass(frozen=True)
class CommitSummary:
    actions: tuple[Change, ...]


def validate_summary(data: dict[str, Any]) -> CommitSummary:
    _validate_mapping_keys(data, TOP_LEVEL_KEYS, context="summary")

    actions_value = data.get("actions")
    if not isinstance(actions_value, list) or not actions_value:
        raise ValidationError("summary.actions must be a non-empty list.")

    changes: list[Change] = []
    seen_targets: set[tuple[str, str]] = set()

    for index, raw_change in enumerate(actions_value):
        change = _validate_change(raw_change, index)
        target = (change.repo, change.path)
        if target in seen_targets:
            raise ValidationError(
                f"actions[{index}] duplicates repo/path {change.repo!r} {change.path!r}."
            )
        seen_targets.add(target)
        changes.append(change)

    return CommitSummary(actions=tuple(changes))


def _validate_change(raw_change: Any, index: int) -> Change:
    if not isinstance(raw_change, dict):
        raise ValidationError(f"actions[{index}] must be a mapping.")

    _validate_mapping_keys(
        raw_change,
        frozenset({"repo", "type", "path", "content"}),
        context=f"actions[{index}]",
    )

    repo = raw_change.get("repo")
    if repo not in ALLOWED_REPOS:
        raise ValidationError(
            f"actions[{index}].repo must be one of {', '.join(ALLOWED_REPOS)}."
        )

    change_type = raw_change.get("type")
    if change_type not in ALLOWED_ACTION_TYPES:
        raise ValidationError(
            f"actions[{index}].type must be one of {', '.join(ALLOWED_ACTION_TYPES)}."
        )

    path = raw_change.get("path")
    validated_path = _validate_relative_path(path, index)

    content = raw_change.get("content")
    if change_type == "write":
        if not isinstance(content, str) or content == "":
            raise ValidationError(
                f"actions[{index}].content must be a non-empty string for write actions."
            )
    elif content is not None:
        raise ValidationError(
            f"actions[{index}].content is only allowed for write actions."
        )

    return Change(
        repo=repo,
        change_type=change_type,
        path=validated_path,
        content=content,
    )


def _validate_relative_path(value: Any, index: int) -> str:
    if not isinstance(value, str) or value.strip() == "":
        raise ValidationError(f"actions[{index}].path must be a non-empty string.")
    if "\\" in value:
        raise ValidationError(
            f"actions[{index}].path must use forward slashes, not backslashes."
        )

    path = PurePosixPath(value)
    if path.is_absolute() or value.startswith("/"):
        raise ValidationError(f"actions[{index}].path must be relative, not absolute.")
    if any(part == ".." for part in path.parts):
        raise ValidationError(f"actions[{index}].path must not contain '..'.")
    if path == PurePosixPath("."):
        raise ValidationError(f"actions[{index}].path must not be '.'.")

    return str(path)


def _validate_mapping_keys(
    mapping: dict[str, Any],
    allowed_keys: frozenset[str],
    *,
    context: str,
) -> None:
    unknown_keys = sorted(set(mapping) - allowed_keys)
    if unknown_keys:
        joined = ", ".join(repr(key) for key in unknown_keys)
        raise ValidationError(f"{context} contains unsupported keys: {joined}.")
