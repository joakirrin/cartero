from __future__ import annotations

import unittest

from cartero.semantic_quality import (
    normalize_commit_summary_fields,
    validate_commit_summary_quality,
)


class CommitSummarySemanticQualityTests(unittest.TestCase):
    def test_passes_problem_oriented_reason_and_outcome_driven_impact(self) -> None:
        result = validate_commit_summary_quality(
            summary="Cartero now keeps commit summaries aligned with the canonical record.",
            reason=(
                "Developers did not have a reliable way to explain broad changes without "
                "reading the full diff."
            ),
            impact="Developers can now review commit summaries more confidently.",
        )

        self.assertEqual(result.status, "pass")
        self.assertEqual(result.issues, ())

    def test_fails_generic_reason_that_starts_with_change_verb(self) -> None:
        result = validate_commit_summary_quality(
            summary="Cartero now keeps commit summaries aligned with the canonical record.",
            reason="Improves commit summary generation.",
            impact="Developers can now review summaries more confidently.",
        )

        self.assertEqual(result.status, "fail")
        self.assertEqual(result.for_field("reason")[0].code, "generic_reason")

    def test_fails_implementation_heavy_reason(self) -> None:
        result = validate_commit_summary_quality(
            summary="Cartero now keeps commit summaries aligned with the canonical record.",
            reason="The parser and YAML bridge now validate canonical fields before rendering output.",
            impact="Developers can now trust the generated summaries more easily.",
        )

        self.assertEqual(result.status, "fail")
        self.assertEqual(result.for_field("reason")[0].code, "implementation_heavy_reason")

    def test_fails_non_user_facing_impact(self) -> None:
        result = validate_commit_summary_quality(
            summary="Cartero now keeps commit summaries aligned with the canonical record.",
            reason="Developers did not have a reliable way to explain broad changes.",
            impact="The YAML bridge and parser now reuse canonical delimiter validation.",
        )

        self.assertEqual(result.status, "fail")
        self.assertEqual(result.for_field("impact")[0].code, "non_user_facing_impact")

    def test_fails_impact_that_repeats_the_change(self) -> None:
        result = validate_commit_summary_quality(
            summary="Cartero now keeps commit summaries aligned with the canonical record.",
            reason="Developers did not have a reliable way to explain broad changes.",
            impact="Cartero now keeps commit summaries aligned with the canonical record.",
        )

        self.assertEqual(result.status, "fail")
        self.assertEqual(result.for_field("impact")[0].code, "impact_repeats_change")

    def test_warns_on_safe_but_generic_impact_fallback(self) -> None:
        result = validate_commit_summary_quality(
            summary="Cartero now keeps commit summaries aligned with the canonical record.",
            reason="Developers did not have a reliable way to explain broad changes.",
            impact="The workflow is now clearer.",
        )

        self.assertEqual(result.status, "warn")
        self.assertEqual(result.for_field("impact")[0].code, "generic_outcome_fallback")


class CommitSummaryNormalizationTests(unittest.TestCase):
    def test_rewrites_reason_from_problem_hint_when_reason_is_generic(self) -> None:
        result = normalize_commit_summary_fields(
            summary="Cartero now keeps commit summaries aligned with the canonical record.",
            reason="Improves canonical validation logic.",
            impact="Developers can now rely on more consistent commit summaries.",
            problem_hint="Developers did not have a reliable way to trust generated summaries.",
        )

        self.assertEqual(
            result.reason,
            "Developers did not have a reliable way to trust generated summaries.",
        )
        self.assertIn("reason", result.applied_rules)

    def test_rewrites_safe_missing_capability_reason_without_context(self) -> None:
        result = normalize_commit_summary_fields(
            summary="Cartero now accepts context files during generation.",
            reason="Introduces context file support.",
            impact="Developers can now pass context files during generation.",
        )

        self.assertEqual(result.reason, "Before this change, context file support was missing.")
        self.assertIn("reason", result.applied_rules)

    def test_rewrites_repeated_impact_from_outcome_hint(self) -> None:
        result = normalize_commit_summary_fields(
            summary="Cartero now keeps commit summaries aligned with the canonical record.",
            reason="Developers did not have a reliable way to trust generated summaries.",
            impact="Cartero now keeps commit summaries aligned with the canonical record.",
            outcome_hint="Developers can now rely on more consistent commit summaries.",
        )

        self.assertEqual(
            result.impact,
            "Developers can now rely on more consistent commit summaries.",
        )
        self.assertIn("impact", result.applied_rules)

    def test_rewrites_technical_impact_from_summary_when_safe(self) -> None:
        result = normalize_commit_summary_fields(
            summary="Cartero now keeps commit summaries aligned with the canonical record.",
            reason="Developers did not have a reliable way to trust generated summaries.",
            impact="The YAML bridge and parser now share canonical validation.",
        )

        self.assertEqual(
            result.impact,
            "Developers can now rely on more consistent commit summaries.",
        )
        self.assertIn("impact", result.applied_rules)

    def test_leaves_text_unchanged_when_no_safe_rewrite_exists(self) -> None:
        result = normalize_commit_summary_fields(
            summary="Cartero now changes prompt labels for developers.",
            reason="Improves prompt behavior.",
            impact="Improves prompt behavior.",
        )

        self.assertEqual(result.reason, "Improves prompt behavior.")
        self.assertEqual(result.impact, "Improves prompt behavior.")
        self.assertEqual(result.applied_rules, ())
