from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import yaml

from cartero.config import CarteroConfig
from cartero.generator import SummaryGenerationResult, generate_summary_result_from_diff


_DEFAULT_MANIFEST_PATH = (
    Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "readiness_cases" / "manifest.yaml"
)

GenerateResultFn = Callable[
    [str, CarteroConfig | None],
    SummaryGenerationResult,
]


@dataclass(frozen=True)
class ReadinessCase:
    case_name: str
    case_type: str
    diff_text: str
    context_text: str | None = None
    config: CarteroConfig | None = None
    clear_intent: bool = False
    ambiguous_expected: bool = False

    @property
    def has_context(self) -> bool:
        return bool(self.context_text and self.context_text.strip())


@dataclass(frozen=True)
class ReadinessCaseResult:
    case_name: str
    case_type: str
    has_context: bool
    summary: str
    reason: str
    impact: str
    semantic_status: str
    semantic_warnings: list[dict[str, Any]]
    retry_count: int
    used_normalization: bool
    normalization_rules: list[str]
    used_fallback_reason: bool
    used_fallback_impact: bool
    parity_checks: dict[str, bool]
    was_chunked: bool = False
    generation_error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ReadinessReport:
    generated_at: str
    cases: list[ReadinessCaseResult]
    summary: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at,
            "cases": [case.to_dict() for case in self.cases],
            "summary": self.summary,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=False)


def load_default_readiness_corpus(
    manifest_path: Path | None = None,
) -> list[ReadinessCase]:
    resolved_manifest_path = manifest_path or _DEFAULT_MANIFEST_PATH
    raw_manifest = yaml.safe_load(resolved_manifest_path.read_text(encoding="utf-8"))
    if not isinstance(raw_manifest, dict):
        raise ValueError("Readiness corpus manifest must be a YAML mapping.")

    raw_cases = raw_manifest.get("cases")
    if not isinstance(raw_cases, list):
        raise ValueError("Readiness corpus manifest must define a 'cases' list.")

    base_dir = resolved_manifest_path.parent
    cases: list[ReadinessCase] = []
    for entry in raw_cases:
        if not isinstance(entry, dict):
            raise ValueError("Each readiness corpus entry must be a mapping.")

        diff_path = entry.get("diff_path")
        if not isinstance(diff_path, str) or not diff_path.strip():
            raise ValueError("Each readiness corpus entry must define a diff_path.")

        context_path = entry.get("context_path")
        context_text = None
        if isinstance(context_path, str) and context_path.strip():
            context_text = (base_dir / context_path).read_text(encoding="utf-8")

        cases.append(
            ReadinessCase(
                case_name=str(entry.get("name", "")).strip(),
                case_type=str(entry.get("case_type", "")).strip(),
                diff_text=(base_dir / diff_path).read_text(encoding="utf-8"),
                context_text=context_text,
                config=_build_case_config(entry.get("config")),
                clear_intent=bool(entry.get("clear_intent", False)),
                ambiguous_expected=bool(entry.get("ambiguous_expected", False)),
            )
        )

    return cases


def run_readiness_harness(
    *,
    cases: list[ReadinessCase] | None = None,
    generate_result_fn: Callable[..., SummaryGenerationResult] = generate_summary_result_from_diff,
) -> ReadinessReport:
    active_cases = list(cases or load_default_readiness_corpus())
    case_results: list[ReadinessCaseResult] = []
    clear_intent_cases = 0
    clear_intent_passes = 0
    ambiguous_cases = 0
    ambiguous_non_fail_cases = 0
    ambiguous_reason_fallbacks = 0
    ambiguous_impact_fallbacks = 0

    for case in active_cases:
        result = _run_case(case, generate_result_fn=generate_result_fn)
        case_results.append(result)

        if case.clear_intent:
            clear_intent_cases += 1
            if result.semantic_status == "pass":
                clear_intent_passes += 1

        if case.ambiguous_expected:
            ambiguous_cases += 1
            if result.semantic_status != "fail":
                ambiguous_non_fail_cases += 1
            if result.used_fallback_reason:
                ambiguous_reason_fallbacks += 1
            if result.used_fallback_impact:
                ambiguous_impact_fallbacks += 1

    summary = _build_summary(
        active_cases,
        case_results,
        clear_intent_cases=clear_intent_cases,
        clear_intent_passes=clear_intent_passes,
        ambiguous_cases=ambiguous_cases,
        ambiguous_non_fail_cases=ambiguous_non_fail_cases,
        ambiguous_reason_fallbacks=ambiguous_reason_fallbacks,
        ambiguous_impact_fallbacks=ambiguous_impact_fallbacks,
    )
    return ReadinessReport(
        generated_at=datetime.now(timezone.utc).isoformat(),
        cases=case_results,
        summary=summary,
    )


def _build_case_config(raw_config: object) -> CarteroConfig | None:
    if raw_config is None:
        return None
    if not isinstance(raw_config, dict):
        raise ValueError("Readiness case config must be a mapping when provided.")
    return CarteroConfig(**raw_config)


def _run_case(
    case: ReadinessCase,
    *,
    generate_result_fn: Callable[..., SummaryGenerationResult],
) -> ReadinessCaseResult:
    from cartero.cli import (
        _load_commit_fields_for_commit,
        _load_commit_fields_for_explanation,
    )
    from cartero.web import build_generate_payload

    try:
        result = generate_result_fn(
            case.diff_text,
            config=case.config,
            raw_context=case.context_text,
        )
    except Exception as exc:
        return ReadinessCaseResult(
            case_name=case.case_name,
            case_type=case.case_type,
            has_context=case.has_context,
            summary="",
            reason="",
            impact="",
            semantic_status="fail",
            semantic_warnings=[],
            retry_count=0,
            used_normalization=False,
            normalization_rules=[],
            used_fallback_reason=False,
            used_fallback_impact=False,
            parity_checks={
                "yaml_parseable": False,
                "yaml_matches_commit_fields": False,
                "cli_commit_fields_align_with_yaml": False,
                "cli_explanation_fields_align_with_yaml": False,
                "web_payload_commit_fields_align": False,
                "web_payload_quality_align": False,
                "web_payload_yaml_align": False,
            },
            was_chunked=False,
            generation_error=str(exc),
        )

    yaml_fields = _safe_load_yaml_commit_fields(result.yaml_text)
    structured_fields = _coerce_commit_fields(result.commit_fields)
    extracted_fields = structured_fields or yaml_fields or {}
    quality = result.quality_metadata if isinstance(result.quality_metadata, dict) else {}
    web_payload = build_generate_payload(result)
    cli_commit_fields = _load_commit_fields_for_commit(result)
    cli_explanation_fields = _load_commit_fields_for_explanation(result)

    return ReadinessCaseResult(
        case_name=case.case_name,
        case_type=case.case_type,
        has_context=case.has_context,
        summary=str(extracted_fields.get("summary", "")).strip(),
        reason=str(extracted_fields.get("reason", "")).strip(),
        impact=str(extracted_fields.get("impact", "")).strip(),
        semantic_status=str(quality.get("semantic_status", "fail")),
        semantic_warnings=_coerce_semantic_warnings(quality.get("semantic_warnings")),
        retry_count=_coerce_int(quality.get("retry_count")),
        used_normalization=bool(quality.get("used_normalization", False)),
        normalization_rules=_coerce_str_list(quality.get("normalization_rules")),
        used_fallback_reason=bool(quality.get("used_fallback_reason", False)),
        used_fallback_impact=bool(quality.get("used_fallback_impact", False)),
        parity_checks={
            "yaml_parseable": yaml_fields is not None,
            "yaml_matches_commit_fields": yaml_fields is not None and structured_fields == yaml_fields,
            "cli_commit_fields_align_with_yaml": yaml_fields is not None and cli_commit_fields == yaml_fields,
            "cli_explanation_fields_align_with_yaml": yaml_fields is not None
            and cli_explanation_fields == yaml_fields,
            "web_payload_commit_fields_align": web_payload.get("commit_fields") == result.commit_fields,
            "web_payload_quality_align": web_payload.get("quality") == result.quality_metadata,
            "web_payload_yaml_align": web_payload.get("yaml") == result.yaml_text,
        },
        was_chunked=bool(result.warning_message),
    )


def _build_summary(
    cases: list[ReadinessCase],
    results: list[ReadinessCaseResult],
    *,
    clear_intent_cases: int,
    clear_intent_passes: int,
    ambiguous_cases: int,
    ambiguous_non_fail_cases: int,
    ambiguous_reason_fallbacks: int,
    ambiguous_impact_fallbacks: int,
) -> dict[str, Any]:
    total_cases = len(results)
    fail_level_count = sum(1 for result in results if result.semantic_status == "fail")
    warn_level_count = sum(1 for result in results if result.semantic_status == "warn")
    fallback_reason_count = sum(1 for result in results if result.used_fallback_reason)
    fallback_impact_count = sum(1 for result in results if result.used_fallback_impact)
    fallback_either_count = sum(
        1 for result in results if result.used_fallback_reason or result.used_fallback_impact
    )
    retry_count = sum(1 for result in results if result.retry_count > 0)
    normalization_count = sum(1 for result in results if result.used_normalization)

    breakdown: dict[str, dict[str, int]] = {}
    for result in results:
        type_breakdown = breakdown.setdefault(
            result.case_type,
            {
                "total_cases": 0,
                "pass_level_count": 0,
                "warn_level_count": 0,
                "fail_level_count": 0,
            },
        )
        type_breakdown["total_cases"] += 1
        if result.semantic_status == "pass":
            type_breakdown["pass_level_count"] += 1
        elif result.semantic_status == "warn":
            type_breakdown["warn_level_count"] += 1
        else:
            type_breakdown["fail_level_count"] += 1

    parity_failures_by_check: dict[str, int] = {}
    all_parity_checks_passing = 0
    for result in results:
        if all(result.parity_checks.values()):
            all_parity_checks_passing += 1
        for check_name, passed in result.parity_checks.items():
            if not passed:
                parity_failures_by_check[check_name] = parity_failures_by_check.get(check_name, 0) + 1

    parity_failure_cases = sum(
        1 for result in results if not all(result.parity_checks.values())
    )

    overall_status = "pass"
    if fail_level_count or parity_failure_cases:
        overall_status = "fail"
    elif warn_level_count:
        overall_status = "warn"

    return {
        "overall_status": overall_status,
        "total_cases": total_cases,
        "fail_level_count": fail_level_count,
        "warn_level_count": warn_level_count,
        "fallback_frequency": {
            "reason": _build_frequency(fallback_reason_count, total_cases),
            "impact": _build_frequency(fallback_impact_count, total_cases),
            "either": _build_frequency(fallback_either_count, total_cases),
        },
        "retry_frequency": _build_frequency(retry_count, total_cases),
        "normalization_frequency": _build_frequency(normalization_count, total_cases),
        "breakdown_by_case_type": breakdown,
        "clear_intent_quality_pass_rate": _build_frequency(clear_intent_passes, clear_intent_cases),
        "ambiguous_case_restraint_truthfulness": {
            "total_cases": ambiguous_cases,
            "non_fail_semantic_cases": ambiguous_non_fail_cases,
            "reason_fallback_cases": ambiguous_reason_fallbacks,
            "impact_fallback_cases": ambiguous_impact_fallbacks,
            "non_fail_rate": _build_rate(ambiguous_non_fail_cases, ambiguous_cases),
        },
        "parity": {
            "cases_with_all_checks_passing": all_parity_checks_passing,
            "cases_with_any_mismatch": parity_failure_cases,
            "failures_by_check": parity_failures_by_check,
        },
        "corpus": [
            {
                "case_name": case.case_name,
                "case_type": case.case_type,
                "has_context": case.has_context,
            }
            for case in cases
        ],
    }


def _build_frequency(count: int, total: int) -> dict[str, Any]:
    return {
        "count": count,
        "total": total,
        "rate": _build_rate(count, total),
    }


def _build_rate(count: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return round(count / total, 3)


def _safe_load_yaml_commit_fields(yaml_text: str) -> dict[str, Any] | None:
    from cartero.cli import _load_commit_fields_from_yaml_text

    try:
        data = _load_commit_fields_from_yaml_text(yaml_text)
    except yaml.YAMLError:
        return None
    if not isinstance(data, dict):
        return None
    return data


def _coerce_commit_fields(candidate: object) -> dict[str, Any] | None:
    if not isinstance(candidate, dict):
        return None
    return {
        "summary": str(candidate.get("summary", "")).strip(),
        "reason": str(candidate.get("reason", "")).strip(),
        "impact": str(candidate.get("impact", "")).strip(),
        "actions": list(candidate.get("actions", []))
        if isinstance(candidate.get("actions"), (list, tuple))
        else [],
    }


def _coerce_semantic_warnings(candidate: object) -> list[dict[str, Any]]:
    if not isinstance(candidate, list):
        return []
    warnings: list[dict[str, Any]] = []
    for item in candidate:
        if isinstance(item, dict):
            warnings.append({str(key): value for key, value in item.items()})
    return warnings


def _coerce_str_list(candidate: object) -> list[str]:
    if not isinstance(candidate, list):
        return []
    return [str(item) for item in candidate]


def _coerce_int(candidate: object) -> int:
    try:
        return int(candidate)
    except (TypeError, ValueError):
        return 0
