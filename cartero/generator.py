from __future__ import annotations

from dataclasses import dataclass

from cartero.config import CarteroConfig
from cartero import llm


CHUNKED_DIFF_WARNING = (
    "Diff was too large and was split into multiple chunks. "
    "The generated summary may be incomplete."
)


@dataclass(frozen=True)
class SummaryGenerationResult:
    yaml_text: str
    warning_message: str | None = None


def generate_summary_from_diff(
    diff_text: str, config: CarteroConfig | None = None
) -> str:
    return generate_summary_result_from_diff(diff_text, config).yaml_text


def generate_summary_result_from_diff(
    diff_text: str, config: CarteroConfig | None = None
) -> SummaryGenerationResult:
    _validate_diff_text(diff_text)
    result = llm.generate_commit_summary_result(diff_text, config)
    warning_message = CHUNKED_DIFF_WARNING if result.was_chunked else None
    return SummaryGenerationResult(result.yaml_text, warning_message)


def _validate_diff_text(diff_text: str) -> None:
    if not isinstance(diff_text, str) or not diff_text.strip():
        raise ValueError("diff_text must be a non-empty string")
