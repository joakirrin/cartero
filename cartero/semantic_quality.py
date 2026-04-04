from __future__ import annotations

"""Deterministic semantic quality checks for Cartero text outputs.

The public API is intentionally small:

- ``SemanticQualityIssue`` captures one warning or failure
- ``SemanticQualityResult`` reports pass / warn / fail
- ``validate_commit_summary_quality()`` validates commit-summary fields
- ``normalize_commit_summary_fields()`` performs conservative deterministic
  rewrites for weak but salvageable commit-summary fields

This module focuses on low-cost, explainable heuristics. It does not try to
infer product intent from embeddings or model calls. Future output surfaces can
reuse the result objects and add their own validators alongside the commit one.
"""

import re
from dataclasses import dataclass
from typing import Literal


Severity = Literal["warn", "fail"]
Status = Literal["pass", "warn", "fail"]

_CHANGE_VERB_PATTERN = re.compile(
    r"^\s*(adds?|added|introduces?|introduced|implements?|implemented|"
    r"improves?|improved|updates?|updated|changes?|changed|enhances?|enhanced|"
    r"simplifies?|simplified|refactors?|refactored)\b",
    re.IGNORECASE,
)

_IMPLEMENTATION_MARKERS = (
    "api",
    "bridge",
    "canonical",
    "class",
    "cli",
    "delimiter",
    "endpoint",
    "file",
    "function",
    "generator",
    "json",
    "llm",
    "markdown",
    "module",
    "parser",
    "path",
    "prompt",
    "regex",
    "render",
    "renderer",
    "route",
    "schema",
    "stream",
    "token",
    "validator",
    "web",
    "yaml",
)

_PROBLEM_MARKERS = (
    "before this change",
    "could not",
    "couldn't",
    "did not",
    "didn't",
    "difficult to",
    "hard to",
    "had no",
    "inconsistent",
    "lacked",
    "less clear",
    "less reliable",
    "manual",
    "missing",
    "no way",
    "too noisy",
    "too technical",
    "unclear",
    "was harder",
    "was less",
    "were harder",
)

_OUTCOME_MARKERS = (
    "available",
    "can",
    "clearer",
    "confidently",
    "consistent",
    "easier",
    "faster",
    "more predictable",
    "more reliable",
    "no longer",
    "now",
    "possible",
    "predictable",
    "ready",
    "reliable",
    "safer",
    "visible",
    "works",
)

_GENERIC_NOUNS = {
    "change",
    "changes",
    "communication",
    "experience",
    "flow",
    "output",
    "outputs",
    "process",
    "summary",
    "summaries",
    "system",
    "tool",
    "workflow",
}

_USER_FACING_HINTS = (
    "developer",
    "developers",
    "review",
    "summaries",
    "summary",
    "team",
    "teams",
    "user",
    "users",
    "workflow",
    "workflows",
    "output",
    "outputs",
    "change",
    "changes",
    "context",
)

_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "be",
    "before",
    "cartero",
    "can",
    "for",
    "from",
    "in",
    "is",
    "it",
    "its",
    "more",
    "now",
    "of",
    "or",
    "that",
    "the",
    "this",
    "to",
    "users",
    "with",
}


@dataclass(frozen=True)
class SemanticQualityIssue:
    field: str
    code: str
    severity: Severity
    message: str


@dataclass(frozen=True)
class SemanticQualityResult:
    issues: tuple[SemanticQualityIssue, ...] = ()

    @property
    def failures(self) -> tuple[SemanticQualityIssue, ...]:
        return tuple(issue for issue in self.issues if issue.severity == "fail")

    @property
    def warnings(self) -> tuple[SemanticQualityIssue, ...]:
        return tuple(issue for issue in self.issues if issue.severity == "warn")

    @property
    def status(self) -> Status:
        if self.failures:
            return "fail"
        if self.warnings:
            return "warn"
        return "pass"

    def messages(self, *, severity: Severity | None = None) -> tuple[str, ...]:
        if severity is None:
            return tuple(issue.message for issue in self.issues)
        return tuple(issue.message for issue in self.issues if issue.severity == severity)

    def for_field(self, field: str) -> tuple[SemanticQualityIssue, ...]:
        return tuple(issue for issue in self.issues if issue.field == field)


@dataclass(frozen=True)
class CommitSummaryNormalizationResult:
    summary: str
    reason: str
    impact: str
    applied_rules: tuple[str, ...] = ()

    @property
    def changed(self) -> bool:
        return bool(self.applied_rules)


def validate_commit_summary_quality(
    *,
    summary: str,
    reason: str,
    impact: str,
) -> SemanticQualityResult:
    """Validate semantic quality for commit-summary fields.

    Failures are reserved for obviously low-quality content that should trigger
    a retry. Warnings capture restrained but still truthful fallback wording.
    """

    issues: list[SemanticQualityIssue] = []

    if _looks_generic_reason(reason):
        issues.append(
            SemanticQualityIssue(
                field="reason",
                code="generic_reason",
                severity="fail",
                message="reason must describe the problem before the change, not a generic change verb",
            )
        )

    if _looks_implementation_heavy_reason(reason):
        issues.append(
            SemanticQualityIssue(
                field="reason",
                code="implementation_heavy_reason",
                severity="fail",
                message="reason should explain the real limitation or inconsistency, not internal implementation",
            )
        )

    if _looks_non_user_facing_impact(impact):
        issues.append(
            SemanticQualityIssue(
                field="impact",
                code="non_user_facing_impact",
                severity="fail",
                message="impact must describe an outcome for users or developers, not only internal mechanics",
            )
        )

    if _looks_repeated_impact(summary=summary, impact=impact):
        issues.append(
            SemanticQualityIssue(
                field="impact",
                code="impact_repeats_change",
                severity="fail",
                message="impact should not merely repeat the summary of the change",
            )
        )

    if _looks_safe_but_generic_impact(impact):
        issues.append(
            SemanticQualityIssue(
                field="impact",
                code="generic_outcome_fallback",
                severity="warn",
                message="impact is truthful but still generic; prefer a more concrete outcome when supported",
            )
        )

    return SemanticQualityResult(tuple(issues))


def normalize_commit_summary_fields(
    *,
    summary: str,
    reason: str,
    impact: str,
    problem_hint: str | None = None,
    outcome_hint: str | None = None,
) -> CommitSummaryNormalizationResult:
    """Rewrite only obviously weak fields when a safe deterministic rewrite exists."""

    normalized_summary = _normalize_sentence(summary)
    normalized_reason = _normalize_sentence(reason)
    normalized_impact = _normalize_sentence(impact)
    applied_rules: list[str] = []

    if _looks_generic_reason(normalized_reason) or _looks_implementation_heavy_reason(
        normalized_reason
    ):
        rewritten_reason = _rewrite_reason(
            normalized_reason,
            problem_hint=problem_hint,
        )
        if rewritten_reason and rewritten_reason != normalized_reason:
            normalized_reason = rewritten_reason
            applied_rules.append("reason")

    if _looks_non_user_facing_impact(normalized_impact) or _looks_repeated_impact(
        summary=normalized_summary,
        impact=normalized_impact,
    ):
        rewritten_impact = _rewrite_impact(
            normalized_summary,
            normalized_impact,
            outcome_hint=outcome_hint,
        )
        if rewritten_impact and rewritten_impact != normalized_impact:
            normalized_impact = rewritten_impact
            applied_rules.append("impact")

    return CommitSummaryNormalizationResult(
        summary=normalized_summary,
        reason=normalized_reason,
        impact=normalized_impact,
        applied_rules=tuple(applied_rules),
    )


def _looks_generic_reason(reason: str) -> bool:
    text = reason.strip().lower()
    if not text:
        return False
    if _CHANGE_VERB_PATTERN.match(text):
        return True
    return False


def _looks_implementation_heavy_reason(reason: str) -> bool:
    text = reason.strip().lower()
    if not text:
        return False
    if _has_problem_marker(text):
        return False
    return _implementation_marker_count(text) >= 2 or _contains_code_style_identifier(text)


def _looks_non_user_facing_impact(impact: str) -> bool:
    text = impact.strip().lower()
    if not text:
        return False
    if _CHANGE_VERB_PATTERN.match(text):
        return True
    if _implementation_marker_count(text) >= 1 and not _has_user_facing_hint(text):
        return True
    if _has_outcome_marker(text) and _has_user_facing_hint(text):
        return False
    return _implementation_marker_count(text) >= 1 or _contains_code_style_identifier(text)


def _looks_repeated_impact(*, summary: str, impact: str) -> bool:
    summary_tokens = _content_tokens(summary)
    impact_tokens = _content_tokens(impact)
    if not summary_tokens or not impact_tokens:
        return False
    if summary_tokens == impact_tokens:
        return True
    overlap = len(summary_tokens & impact_tokens) / max(len(summary_tokens | impact_tokens), 1)
    return overlap >= 0.75


def _looks_safe_but_generic_impact(impact: str) -> bool:
    text = impact.strip().lower()
    if not text or _looks_non_user_facing_impact(impact):
        return False
    tokens = _content_tokens(text)
    if len(tokens) > 4:
        return False
    return any(token in _GENERIC_NOUNS for token in tokens)


def _rewrite_reason(reason: str, *, problem_hint: str | None) -> str | None:
    if problem_hint:
        candidate = _normalize_sentence(problem_hint)
        if candidate:
            return candidate
    return _rewrite_missing_capability_reason(reason)


def _rewrite_impact(summary: str, impact: str, *, outcome_hint: str | None) -> str | None:
    if outcome_hint:
        candidate = _normalize_sentence(outcome_hint)
        if candidate:
            return candidate
    return _rewrite_impact_from_summary(summary, impact)


def _rewrite_missing_capability_reason(reason: str) -> str | None:
    match = re.match(
        r"^\s*(adds?|introduced?|introduces?|implements?|implemented)\s+(?P<object>.+?)[.?!]?\s*$",
        reason,
        re.IGNORECASE,
    )
    if match is None:
        return None

    object_phrase = _normalize_sentence(match.group("object"))
    if not object_phrase:
        return None
    lowered_object = object_phrase.lower()
    if any(
        marker in lowered_object
        for marker in (
            "bridge",
            "canonical",
            "delimiter",
            "endpoint",
            "function",
            "json",
            "llm",
            "module",
            "parser",
            "path",
            "regex",
            "renderer",
            "route",
            "schema",
            "validator",
            "yaml",
        )
    ):
        return None
    if _contains_code_style_identifier(object_phrase):
        return None
    if len(object_phrase.split()) > 8:
        return None

    lowered_object = object_phrase[0].lower() + object_phrase[1:]
    lowered_object = re.sub(r"^(a|an|the)\s+", "", lowered_object, count=1, flags=re.IGNORECASE)
    return f"Before this change, {lowered_object} was missing."


def _rewrite_impact_from_summary(summary: str, impact: str) -> str | None:
    summary_text = summary.strip()
    if not summary_text.startswith("Cartero"):
        return None

    lower_summary = summary_text.lower()
    lower_impact = impact.lower()
    if "clear" in lower_summary or "plain language" in lower_summary:
        return "Developers can now understand the change more clearly."
    if (
        "consistent" in lower_summary
        or "aligned" in lower_summary
        or "reliable" in lower_summary
        or "canonical" in lower_summary
    ):
        return "Developers can now rely on more consistent commit summaries."
    if "preview" in lower_summary:
        return "Developers can now review the result before continuing."
    if "context" in lower_summary or "intent" in lower_summary:
        return "Developers can now keep summaries aligned with the intended change."
    if "changelog" in lower_summary:
        return "Developers can now share a clearer product-facing summary of the change."
    if _looks_repeated_impact(summary=summary, impact=impact) and not _has_user_facing_hint(lower_impact):
        return "Developers can now use the result with more confidence."
    return None


def _has_problem_marker(text: str) -> bool:
    return any(marker in text for marker in _PROBLEM_MARKERS)


def _has_outcome_marker(text: str) -> bool:
    return any(marker in text for marker in _OUTCOME_MARKERS)


def _has_user_facing_hint(text: str) -> bool:
    return any(marker in text for marker in _USER_FACING_HINTS)


def _implementation_marker_count(text: str) -> int:
    return sum(1 for marker in _IMPLEMENTATION_MARKERS if marker in text)


def _contains_code_style_identifier(text: str) -> bool:
    return bool(re.search(r"[a-z0-9_]+\.[a-z0-9_]+|`[^`]+`|[a-z_]+\(\)", text))


def _content_tokens(text: str) -> set[str]:
    tokens = {
        token
        for token in re.findall(r"[a-z0-9']+", text.lower())
        if token not in _STOPWORDS
    }
    return tokens


def _normalize_sentence(text: str) -> str:
    return " ".join(text.replace("\r\n", "\n").replace("\r", "\n").split())
