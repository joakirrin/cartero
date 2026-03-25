from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


class ParseError(ValueError):
    """Raised when a summary file cannot be parsed as valid YAML."""


class StrictLoader(yaml.SafeLoader):
    """PyYAML loader that rejects duplicate mapping keys."""


def _construct_unique_mapping(
    loader: StrictLoader,
    node: yaml.nodes.MappingNode,
    deep: bool = False,
) -> dict[Any, Any]:
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise ParseError(f"Duplicate YAML key: {key!r}")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


StrictLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


def load_summary(path: str | Path) -> dict[str, Any]:
    """Load a YAML summary file into a top-level mapping."""

    summary_path = Path(path)

    try:
        raw_text = summary_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ParseError(f"Unable to read summary file {summary_path}: {exc}") from exc

    try:
        loaded = yaml.load(raw_text, Loader=StrictLoader)
    except yaml.YAMLError as exc:
        raise ParseError(f"Invalid YAML in {summary_path}: {exc}") from exc

    if not isinstance(loaded, dict):
        raise ParseError("Summary root must be a YAML mapping.")

    return loaded
