from __future__ import annotations

import unittest

from cartero.canonical import parse_canonical_record
from cartero.generator import SummaryGenerationResult
from cartero.readiness import (
    ReadinessCase,
    load_default_readiness_corpus,
    run_readiness_harness,
)


def _canonical_text(summary: str, changelog: str) -> str:
    return "\n".join(
        [
            "<<<CARTERO_RECORD_V1>>>",
            "<<<SUMMARY>>>",
            summary,
            "<<<END_SUMMARY>>>",
            "<<<CHANGELOG>>>",
            changelog,
            "<<<END_CHANGELOG>>>",
            "<<<FAQ>>>",
            "NONE",
            "<<<END_FAQ>>>",
            "<<<KNOWLEDGE_BASE>>>",
            "NONE",
            "<<<END_KNOWLEDGE_BASE>>>",
            "<<<END_CARTERO_RECORD_V1>>>",
        ]
    )


def _summary_result(
    *,
    summary: str,
    reason: str,
    impact: str,
    semantic_status: str,
    semantic_warnings: list[dict[str, str]] | None = None,
    retry_count: int = 0,
    used_normalization: bool = False,
    normalization_rules: list[str] | None = None,
    used_fallback_reason: bool = False,
    used_fallback_impact: bool = False,
    commit_fields: dict[str, object] | None = None,
    warning_message: str | None = None,
) -> SummaryGenerationResult:
    canonical_text = _canonical_text(
        summary,
        "Cartero now keeps the generated explanation aligned with the change intent.",
    )
    yaml_text = (
        f"summary: {summary}\n"
        f"reason: {reason}\n"
        f"impact: {impact}\n"
        "actions: []\n"
    )
    return SummaryGenerationResult(
        record=parse_canonical_record(canonical_text),
        canonical_text=canonical_text,
        yaml_text=yaml_text,
        warning_message=warning_message,
        commit_fields=commit_fields
        or {
            "summary": summary,
            "reason": reason,
            "impact": impact,
            "actions": [],
        },
        quality_metadata={
            "semantic_status": semantic_status,
            "semantic_warnings": semantic_warnings or [],
            "retry_count": retry_count,
            "used_normalization": used_normalization,
            "normalization_rules": normalization_rules or [],
            "used_fallback_reason": used_fallback_reason,
            "used_fallback_impact": used_fallback_impact,
        },
    )


class ReadinessCorpusTests(unittest.TestCase):
    def test_default_corpus_covers_expected_case_types(self) -> None:
        cases = load_default_readiness_corpus()

        self.assertEqual(len(cases), 7)
        self.assertEqual(
            [case.case_name for case in cases],
            [
                "clear_intent_with_context",
                "clear_intent_without_context",
                "docs_only_diff",
                "tests_only_diff",
                "formatting_only_diff",
                "ambiguous_small_diff",
                "chunked_larger_diff",
            ],
        )
        self.assertEqual(
            [case.case_type for case in cases],
            [
                "clear_intent",
                "clear_intent",
                "docs_only",
                "tests_only",
                "formatting_only",
                "ambiguous_small",
                "chunked_large",
            ],
        )
        self.assertTrue(cases[0].has_context)
        self.assertFalse(cases[1].has_context)
        self.assertEqual(cases[-1].config.max_diff_tokens, 20)


class ReadinessHarnessTests(unittest.TestCase):
    def test_harness_builds_structured_case_results_and_aggregate_summary(self) -> None:
        cases = [
            ReadinessCase(
                case_name="clear_pass",
                case_type="clear_intent",
                diff_text="diff-clear-pass",
                context_text="Goal: clarify the change.",
                clear_intent=True,
            ),
            ReadinessCase(
                case_name="ambiguous_warn",
                case_type="ambiguous_small",
                diff_text="diff-ambiguous-warn",
                ambiguous_expected=True,
            ),
            ReadinessCase(
                case_name="clear_fail",
                case_type="clear_intent",
                diff_text="diff-clear-fail",
                clear_intent=True,
            ),
        ]

        mismatched_commit_fields = {
            "summary": "Cartero now ships the readiness harness.",
            "reason": "Before this change, readiness reports were missing.",
            "impact": "Developers can now review readiness results in one place.",
            "actions": [],
        }

        def fake_generate(
            diff_text: str,
            config=None,
            raw_context: str | None = None,
        ) -> SummaryGenerationResult:
            del config, raw_context
            if diff_text == "diff-clear-pass":
                return _summary_result(
                    summary="Cartero now explains readiness cases in plain language.",
                    reason="Before this change, readiness coverage was missing.",
                    impact="Developers can now review readiness results more confidently.",
                    semantic_status="pass",
                )
            if diff_text == "diff-ambiguous-warn":
                return _summary_result(
                    summary="Cartero now evaluates ambiguous diffs more conservatively.",
                    reason="Before this change, this area was described less consistently.",
                    impact="Developers can now review this area with less ambiguity.",
                    semantic_status="warn",
                    semantic_warnings=[
                        {
                            "field": "impact",
                            "code": "generic_outcome_fallback",
                            "severity": "warn",
                            "message": "impact is truthful but still generic",
                        }
                    ],
                    retry_count=1,
                    used_normalization=True,
                    normalization_rules=["impact"],
                    used_fallback_reason=True,
                    used_fallback_impact=True,
                )
            if diff_text == "diff-clear-fail":
                return _summary_result(
                    summary="Cartero now ships the readiness harness.",
                    reason="Improves readiness output.",
                    impact="Cartero now ships the readiness harness.",
                    semantic_status="fail",
                    commit_fields=mismatched_commit_fields,
                )
            raise AssertionError(f"Unexpected diff_text: {diff_text}")

        report = run_readiness_harness(cases=cases, generate_result_fn=fake_generate)

        self.assertEqual(report.summary["total_cases"], 3)
        self.assertEqual(report.summary["fail_level_count"], 1)
        self.assertEqual(report.summary["warn_level_count"], 1)
        self.assertEqual(report.summary["fallback_frequency"]["either"]["count"], 1)
        self.assertEqual(report.summary["retry_frequency"]["count"], 1)
        self.assertEqual(report.summary["normalization_frequency"]["count"], 1)
        self.assertEqual(report.summary["clear_intent_quality_pass_rate"]["count"], 1)
        self.assertEqual(report.summary["clear_intent_quality_pass_rate"]["total"], 2)
        self.assertEqual(
            report.summary["ambiguous_case_restraint_truthfulness"]["reason_fallback_cases"],
            1,
        )
        self.assertEqual(
            report.summary["ambiguous_case_restraint_truthfulness"]["impact_fallback_cases"],
            1,
        )
        self.assertEqual(report.summary["parity"]["cases_with_any_mismatch"], 1)
        self.assertEqual(
            report.summary["parity"]["failures_by_check"]["yaml_matches_commit_fields"],
            1,
        )
        self.assertEqual(
            report.summary["parity"]["failures_by_check"]["cli_commit_fields_align_with_yaml"],
            1,
        )
        self.assertEqual(report.summary["overall_status"], "fail")

        self.assertEqual(report.cases[0].summary, "Cartero now explains readiness cases in plain language.")
        self.assertTrue(report.cases[0].parity_checks["yaml_matches_commit_fields"])
        self.assertEqual(report.cases[1].semantic_status, "warn")
        self.assertTrue(report.cases[1].used_fallback_reason)
        self.assertTrue(report.cases[1].used_fallback_impact)
        self.assertFalse(report.cases[2].parity_checks["yaml_matches_commit_fields"])

    def test_harness_marks_generation_errors_as_failures(self) -> None:
        cases = [
            ReadinessCase(
                case_name="broken_case",
                case_type="clear_intent",
                diff_text="diff-broken",
            )
        ]

        def fake_generate(diff_text: str, config=None, raw_context: str | None = None):
            del diff_text, config, raw_context
            raise ValueError("diff_text must be a non-empty string")

        report = run_readiness_harness(cases=cases, generate_result_fn=fake_generate)

        self.assertEqual(report.summary["fail_level_count"], 1)
        self.assertEqual(report.cases[0].generation_error, "diff_text must be a non-empty string")
        self.assertFalse(report.cases[0].parity_checks["yaml_parseable"])
