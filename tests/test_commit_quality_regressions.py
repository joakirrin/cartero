from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

from cartero.canonical import parse_canonical_record
from cartero.config import CarteroConfig
from cartero.generator import generate_summary_result_from_diff
from cartero.llm import CanonicalLLMGenerationResult
from cartero.semantic_quality import validate_commit_summary_quality


def _read_case(name: str) -> tuple[str, str]:
    base = Path("tests/fixtures/extreme_cases") / name
    diff_text = (base / "diff.txt").read_text(encoding="utf-8")
    context_text = (base / "context.txt").read_text(encoding="utf-8")
    return diff_text, context_text


def _canonical_result(summary: str, changelog: str) -> CanonicalLLMGenerationResult:
    canonical_text = "\n".join(
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
    return CanonicalLLMGenerationResult(
        canonical_text=canonical_text,
        record=parse_canonical_record(canonical_text),
        was_chunked=False,
    )


class CommitQualityRegressionTests(unittest.TestCase):
    BASE_CONFIG = CarteroConfig(max_retries=2)

    def test_realistic_partial_rollout_diff_prefers_problem_oriented_reason_from_context(self) -> None:
        diff_text, _ = _read_case("partial_rollout")
        recap = (
            "Goal: Keep documentation outputs aligned.\n"
            "User problem: Developers did not have a reliable way to keep output surfaces consistent.\n"
            "Key decisions: Keep all communication flows tied to the same canonical structure.\n"
            "Tradeoffs: The migration stays incremental while YAML remains for compatibility.\n"
            "Expected user-visible outcome: Developers can now rely on more consistent generated summaries.\n"
            "Explanation for non-technical users: Cartero now keeps generated communication aligned.\n"
        )
        canonical_result = _canonical_result(
            "Cartero now keeps documentation outputs aligned with the same canonical structure.",
            "Cartero now keeps generated communication more consistent across the workflow.",
        )

        with patch(
            "cartero.generator.llm.generate_context_recap",
            return_value=recap,
        ), patch(
            "cartero.generator.llm.generate_canonical_record_result",
            return_value=canonical_result,
        ):
            result = generate_summary_result_from_diff(
                diff_text,
                config=self.BASE_CONFIG,
                raw_context="raw notes",
            )

        payload = yaml.safe_load(result.yaml_text)
        self.assertIn("did not have a reliable way", payload["reason"])
        self.assertFalse(result.quality_metadata["used_fallback_reason"])
        self.assertFalse(result.quality_metadata["used_fallback_impact"])
        self.assertEqual(
            validate_commit_summary_quality(
                summary=payload["summary"],
                reason=payload["reason"],
                impact=payload["impact"],
            ).status,
            "pass",
        )

    def test_realistic_many_changes_diff_keeps_impact_outcome_oriented(self) -> None:
        diff_text, _ = _read_case("many_changes")
        recap = (
            "Goal: Consolidate documentation generation around one canonical record.\n"
            "User problem: Teams had to piece together inconsistent outputs across different communication surfaces.\n"
            "Key decisions: Reuse one canonical contract across generation paths.\n"
            "Tradeoffs: Some bridge code remains while migration stays backward-compatible.\n"
            "Expected user-visible outcome: Teams can now rely on more consistent generated updates.\n"
            "Explanation for non-technical users: Cartero now keeps generated updates more consistent.\n"
        )
        canonical_result = _canonical_result(
            "Cartero now keeps broad documentation generation aligned around one canonical record.",
            "Cartero now keeps generated updates more consistent across the documentation workflow.",
        )

        with patch(
            "cartero.generator.llm.generate_context_recap",
            return_value=recap,
        ), patch(
            "cartero.generator.llm.generate_canonical_record_result",
            return_value=canonical_result,
        ):
            result = generate_summary_result_from_diff(
                diff_text,
                config=self.BASE_CONFIG,
                raw_context="raw notes",
            )

        payload = yaml.safe_load(result.yaml_text)
        self.assertIn("can now rely", payload["impact"].lower())
        self.assertNotIn("parser", payload["impact"].lower())
        self.assertNotIn("yaml", payload["impact"].lower())

    def test_realistic_ambiguous_diff_uses_safe_fallback_without_context(self) -> None:
        diff_text, _ = _read_case("ambiguous_diff")
        canonical_result = _canonical_result(
            "Cartero now keeps internal prompt labeling clearer for developers.",
            "Cartero now keeps internal prompt labeling clearer for developers.",
        )

        with patch(
            "cartero.generator.llm.generate_canonical_record_result",
            return_value=canonical_result,
        ):
            result = generate_summary_result_from_diff(
                diff_text,
                config=self.BASE_CONFIG,
            )

        payload = yaml.safe_load(result.yaml_text)
        self.assertEqual(
            payload["reason"],
            "Before this change, this area was described less consistently.",
        )
        self.assertEqual(
            payload["impact"],
            "Developers can now review this area with less ambiguity.",
        )
        self.assertTrue(result.quality_metadata["used_fallback_reason"])
        self.assertTrue(result.quality_metadata["used_fallback_impact"])
        self.assertNotIn("workflow was less clear", payload["reason"].lower())
        self.assertNotIn("understand the change more clearly", payload["impact"].lower())
        self.assertNotEqual(
            validate_commit_summary_quality(
                summary=payload["summary"],
                reason=payload["reason"],
                impact=payload["impact"],
            ).status,
            "fail",
        )

    def test_docs_only_diff_without_context_uses_documentation_specific_fallbacks(self) -> None:
        diff_text = (
            "diff --git a/README.md b/README.md\n"
            "index 1111111..2222222 100644\n"
            "--- a/README.md\n"
            "+++ b/README.md\n"
            "@@ -1,4 +1,4 @@\n"
            "-Run `cartero generate` from the repo root.\n"
            "+Run `cartero generate` from the project root.\n"
        )
        canonical_result = _canonical_result(
            "Cartero now clarifies README guidance for local generation.",
            "Cartero now clarifies README guidance for local generation.",
        )

        with patch(
            "cartero.generator.llm.generate_canonical_record_result",
            return_value=canonical_result,
        ):
            result = generate_summary_result_from_diff(
                diff_text,
                config=self.BASE_CONFIG,
            )

        payload = yaml.safe_load(result.yaml_text)
        self.assertEqual(
            payload["reason"],
            "Before this change, the documentation around this behavior was easier to misread.",
        )
        self.assertEqual(
            payload["impact"],
            "Developers can now review the documentation with less ambiguity.",
        )
        self.assertTrue(result.quality_metadata["used_fallback_reason"])
        self.assertTrue(result.quality_metadata["used_fallback_impact"])
        self.assertNotIn("README guidance", payload["impact"])
        self.assertNotEqual(
            validate_commit_summary_quality(
                summary=payload["summary"],
                reason=payload["reason"],
                impact=payload["impact"],
            ).status,
            "fail",
        )

    def test_tests_only_diff_without_context_uses_expected_behavior_fallbacks(self) -> None:
        diff_text, _ = _read_case("tests_only")
        canonical_result = _canonical_result(
            "Cartero now keeps test expectations aligned with the latest output shape.",
            "Cartero now keeps test expectations aligned with the latest output shape.",
        )

        with patch(
            "cartero.generator.llm.generate_canonical_record_result",
            return_value=canonical_result,
        ):
            result = generate_summary_result_from_diff(
                diff_text,
                config=self.BASE_CONFIG,
            )

        payload = yaml.safe_load(result.yaml_text)
        self.assertEqual(
            payload["reason"],
            "Before this change, the expected behavior was less clearly captured in supporting tests.",
        )
        self.assertEqual(
            payload["impact"],
            "Developers can now review the expected behavior with less ambiguity.",
        )
        self.assertTrue(result.quality_metadata["used_fallback_reason"])
        self.assertTrue(result.quality_metadata["used_fallback_impact"])
        self.assertNotIn("output shape", payload["impact"])
        self.assertNotEqual(
            validate_commit_summary_quality(
                summary=payload["summary"],
                reason=payload["reason"],
                impact=payload["impact"],
            ).status,
            "fail",
        )

    def test_formatting_only_diff_without_context_uses_visual_consistency_fallbacks(self) -> None:
        diff_text = (
            "diff --git a/cartero/cli.py b/cartero/cli.py\n"
            "index 1111111..2222222 100644\n"
            "--- a/cartero/cli.py\n"
            "+++ b/cartero/cli.py\n"
            "@@ -10,2 +10,2 @@\n"
            "-    return value\n"
            "+  return value\n"
        )
        canonical_result = _canonical_result(
            "Cartero now keeps CLI formatting more consistent.",
            "Cartero now keeps CLI formatting more consistent.",
        )

        with patch(
            "cartero.generator.llm.generate_canonical_record_result",
            return_value=canonical_result,
        ):
            result = generate_summary_result_from_diff(
                diff_text,
                config=self.BASE_CONFIG,
            )

        payload = yaml.safe_load(result.yaml_text)
        self.assertEqual(
            payload["reason"],
            "Before this change, this area was formatted less consistently.",
        )
        self.assertEqual(
            payload["impact"],
            "Developers can now scan this area with less visual ambiguity.",
        )
        self.assertTrue(result.quality_metadata["used_fallback_reason"])
        self.assertTrue(result.quality_metadata["used_fallback_impact"])
        self.assertNotIn("formatting more consistent", payload["impact"].lower())
        self.assertNotEqual(
            validate_commit_summary_quality(
                summary=payload["summary"],
                reason=payload["reason"],
                impact=payload["impact"],
            ).status,
            "fail",
        )

    def test_realistic_diff_path_uses_strengthened_commit_bridge_guidance(self) -> None:
        diff_text, _ = _read_case("tests_only")
        canonical_result = _canonical_result(
            "Cartero now keeps test-only documentation changes easy to review.",
            "Developers can now review test-only documentation changes more clearly.",
        )

        with patch(
            "cartero.generator.llm.generate_canonical_record_result",
            return_value=canonical_result,
        ) as mock_generate:
            generate_summary_result_from_diff(
                diff_text,
                config=self.BASE_CONFIG,
            )

        extra_system_prompt = mock_generate.call_args.kwargs["extra_system_prompt"]
        self.assertIn("pre-change problem", extra_system_prompt)
        self.assertIn("user-facing or developer-facing outcome", extra_system_prompt)
        self.assertIn("Bad reason source", extra_system_prompt)
        self.assertIn("Good impact source", extra_system_prompt)
