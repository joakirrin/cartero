from __future__ import annotations

from dataclasses import dataclass

from cartero.canonical import CanonicalRecord
from cartero.config import CarteroConfig
from cartero import llm


CHUNKED_DIFF_WARNING = (
    "Diff was too large and was split into multiple chunks. "
    "The generated summary may be incomplete."
)


@dataclass(frozen=True)
class SummaryGenerationResult:
    # Canonical data is the primary internal output for generation.
    record: CanonicalRecord
    canonical_text: str
    # Legacy YAML remains as a temporary bridge for older callers.
    yaml_text: str
    warning_message: str | None = None
    commit_fields: dict[str, object] | None = None
    quality_metadata: dict[str, object] | None = None


def generate_summary_from_diff(
    diff_text: str,
    config: CarteroConfig | None = None,
    *,
    raw_context: str | None = None,
) -> str:
    return generate_summary_result_from_diff(
        diff_text,
        config,
        raw_context=raw_context,
    ).yaml_text


def generate_summary_result_from_diff(
    diff_text: str,
    config: CarteroConfig | None = None,
    *,
    raw_context: str | None = None,
) -> SummaryGenerationResult:
    _validate_diff_text(diff_text)
    active_config = config or llm.default_config
    context_recap = None
    if raw_context is not None and raw_context.strip():
        context_recap = llm.generate_context_recap(raw_context, active_config)

    last_error: llm.LLMCallError | None = None
    total_retry_count = 0
    for attempt in range(1, max(1, active_config.max_retries) + 1):
        extra_system_prompt = llm.COMMIT_BRIDGE_CANONICAL_GUIDANCE
        if attempt > 1:
            extra_system_prompt += llm.COMMIT_BRIDGE_QUALITY_RETRY_GUIDANCE
        canonical_result = llm.generate_canonical_record_result(
            diff_text,
            active_config,
            context_recap=context_recap,
            extra_system_prompt=extra_system_prompt,
        )
        total_retry_count += canonical_result.retry_count
        try:
            llm.validate_commit_bridge_source_record(canonical_result.record)
            warning_message = CHUNKED_DIFF_WARNING if canonical_result.was_chunked else None
            total_retry_count += attempt - 1
            bridge_result = llm.build_legacy_yaml_bridge_result(
                canonical_result.record,
                context_recap=context_recap,
                retry_count=total_retry_count,
            )
            return SummaryGenerationResult(
                record=canonical_result.record,
                canonical_text=canonical_result.canonical_text,
                yaml_text=bridge_result.yaml_text,
                warning_message=warning_message,
                commit_fields=bridge_result.commit_fields,
                quality_metadata=bridge_result.quality_metadata,
            )
        except llm.LLMCallError as exc:
            last_error = exc

    raise llm.LLMCallError(
        f"Failed after {max(1, active_config.max_retries)} attempts. Last error: {last_error}"
    )


def generate_context_recap(
    raw_context: str, config: CarteroConfig | None = None
) -> str:
    return llm.generate_context_recap(raw_context, config)


def _validate_diff_text(diff_text: str) -> None:
    if not isinstance(diff_text, str) or not diff_text.strip():
        raise ValueError("diff_text must be a non-empty string")
