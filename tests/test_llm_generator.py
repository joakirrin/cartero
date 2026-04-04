from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch
import yaml

from cartero.canonical import parse_canonical_record
from cartero.config import CarteroConfig
from cartero import llm as llm_module
from cartero.generator import (
    CHUNKED_DIFF_WARNING,
    SummaryGenerationResult,
    generate_context_recap,
    generate_summary_from_diff,
    generate_summary_result_from_diff,
)
from cartero.llm import (
    CanonicalLLMGenerationResult,
    LLMCallError,
    LLMConfigError,
    generate_canonical_record_result,
    generate_changelog,
    generate_commit_summary_result,
)


def _build_canonical_record(
    summary: str,
    changelog: str,
    *,
    faq: str = "NONE",
    knowledge_base: str = "NONE",
) -> str:
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
            faq,
            "<<<END_FAQ>>>",
            "<<<KNOWLEDGE_BASE>>>",
            knowledge_base,
            "<<<END_KNOWLEDGE_BASE>>>",
            "<<<END_CARTERO_RECORD_V1>>>",
        ]
    )


VALID_CANONICAL_RECORD = _build_canonical_record(
    "Cartero now explains network documentation changes in plain language.",
    (
        "Cartero now turns network documentation changes into a clearer release note.\n\n"
        "- Teams can review the purpose of infrastructure changes faster\n"
        "- Communication stays focused on user-facing impact"
    ),
)

VALID_CANONICAL_RECORD_WITH_ITEMS = _build_canonical_record(
    "Cartero now keeps documentation changes aligned with a reusable communication record.",
    (
        "Cartero now returns a canonical communication record for documentation updates.\n\n"
        "- The summary and changelog stay structurally consistent\n"
        "- Reusable FAQ and knowledge base content can travel with the same record"
    ),
    faq=(
        "<<<FAQ_ITEM>>>\n"
        "Q:\n"
        "What changed in the communication pipeline?\n"
        "A:\n"
        "Cartero now produces a canonical record that keeps summary and changelog content aligned.\n"
        "<<<END_FAQ_ITEM>>>"
    ),
    knowledge_base=(
        "<<<KB_ITEM>>>\n"
        "TITLE:\n"
        "Canonical record contract\n"
        "BODY:\n"
        "The LLM must return the approved block order and exact delimiters.\n"
        "<<<END_KB_ITEM>>>"
    ),
)

VALID_RECAP = """Goal: Keep Cartero outputs aligned with user intent.
User problem: Raw conversation context is noisy and makes downstream summaries inconsistent.
Key decisions: Compress notes into a fixed recap focused on intent, tradeoffs, and user-visible outcomes.
Tradeoffs: Some implementation detail is omitted to keep the recap concise.
Expected user-visible outcome: Generated summaries and explanations stay focused on why the change matters.
Explanation for non-technical users: Cartero now turns messy notes into a short brief that explains the purpose of a change in plain language.
"""


def _make_llm_response(text: str) -> MagicMock:
    """Build the object returned by client.messages.create."""
    block = MagicMock()
    block.type = "text"
    block.text = text
    response = MagicMock()
    response.content = [block]
    return response


def _render_canonical_record_for_test(record) -> str:
    return "\n".join(
        [
            "<<<CARTERO_RECORD_V1>>>",
            "<<<SUMMARY>>>",
            record.summary,
            "<<<END_SUMMARY>>>",
            "<<<CHANGELOG>>>",
            record.changelog,
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


class HappyPathTests(unittest.TestCase):
    """Small diffs should return stable bridged output."""

    def test_returns_yaml_string(self) -> None:
        with self._patch_anthropic(VALID_CANONICAL_RECORD):
            result = generate_summary_from_diff("diff --git a/x b/x")

        self.assertIsInstance(result, str)
        self.assertIn("summary:", result)
        self.assertIn("actions:", result)

    def test_no_warning_when_diff_is_small(self) -> None:
        with self._patch_anthropic(VALID_CANONICAL_RECORD):
            result = generate_summary_result_from_diff("diff --git a/x b/x")

        self.assertIsNone(result.warning_message)

    def test_result_is_summary_generation_result(self) -> None:
        with self._patch_anthropic(VALID_CANONICAL_RECORD):
            result = generate_summary_result_from_diff("diff --git a/x b/x")

        self.assertIsInstance(result, SummaryGenerationResult)
        self.assertEqual(result.canonical_text, VALID_CANONICAL_RECORD)
        self.assertEqual(
            result.record.summary,
            "Cartero now explains network documentation changes in plain language.",
        )
        self.assertIsInstance(result.yaml_text, str)

    def test_strips_markdown_fences(self) -> None:
        fenced = f"```text\n{VALID_CANONICAL_RECORD}\n```"
        with self._patch_anthropic(fenced):
            result = generate_summary_from_diff("diff --git a/x b/x")

        self.assertIn("summary:", result)

    def test_generator_uses_canonical_llm_route_as_primary_source(self) -> None:
        canonical_result = CanonicalLLMGenerationResult(
            canonical_text=VALID_CANONICAL_RECORD,
            record=parse_canonical_record(VALID_CANONICAL_RECORD),
            was_chunked=False,
        )

        with patch(
            "cartero.generator.llm.generate_canonical_record_result",
            return_value=canonical_result,
        ) as mock_generate_canonical, patch(
            "cartero.generator.llm.generate_commit_summary_result"
        ) as mock_generate_legacy:
            result = generate_summary_result_from_diff("diff --git a/x b/x")

        self.assertEqual(result.canonical_text, VALID_CANONICAL_RECORD)
        self.assertEqual(result.record, canonical_result.record)
        self.assertIn("summary:", result.yaml_text)
        mock_generate_canonical.assert_called_once_with(
            "diff --git a/x b/x",
            llm_module.default_config,
            context_recap=None,
            extra_system_prompt=llm_module.COMMIT_BRIDGE_CANONICAL_GUIDANCE,
        )
        mock_generate_legacy.assert_not_called()

    def test_uses_only_diff_when_context_is_missing(self) -> None:
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _make_llm_response(VALID_CANONICAL_RECORD)

        with patch("cartero.llm.os.getenv", return_value="unit-test-key"), patch(
            "cartero.llm.Anthropic", return_value=mock_client
        ):
            generate_commit_summary_result("diff --git a/x b/x")

        prompt_text = mock_client.messages.create.call_args.kwargs["messages"][0]["content"]
        self.assertEqual(prompt_text, "diff --git a/x b/x")

    def test_commit_summary_result_keeps_canonical_text(self) -> None:
        with self._patch_anthropic(VALID_CANONICAL_RECORD):
            result = generate_commit_summary_result("diff --git a/x b/x")

        self.assertEqual(result.canonical_text, VALID_CANONICAL_RECORD)
        self.assertIn("impact:", result.yaml_text)

    def _patch_anthropic(self, response_text: str):
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _make_llm_response(response_text)
        return patch.multiple(
            "cartero.llm",
            Anthropic=MagicMock(return_value=mock_client),
            os=MagicMock(getenv=MagicMock(return_value="unit-test-key")),
        )


class ContextRecapTests(unittest.TestCase):
    BASE_CONFIG = CarteroConfig(max_retries=3)

    def test_returns_structured_recap(self) -> None:
        with self._patch_anthropic(VALID_RECAP):
            result = generate_context_recap("messy copied notes")

        self.assertTrue(result.startswith("Goal:"))
        self.assertIn("Expected user-visible outcome:", result)

    def test_strips_markdown_fences_for_recap(self) -> None:
        fenced = f"```text\n{VALID_RECAP}\n```"
        with self._patch_anthropic(fenced):
            result = generate_context_recap("messy copied notes")

        self.assertTrue(result.startswith("Goal:"))
        self.assertNotIn("```", result)

    def test_retries_when_recap_headers_are_missing(self) -> None:
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = [
            _make_llm_response("short paragraph without structure"),
            _make_llm_response(VALID_RECAP),
        ]

        with patch("cartero.llm.os.getenv", return_value="unit-test-key"), patch(
            "cartero.llm.Anthropic", return_value=mock_client
        ):
            result = generate_context_recap("messy copied notes", config=self.BASE_CONFIG)

        self.assertTrue(result.startswith("Goal:"))
        self.assertEqual(mock_client.messages.create.call_count, 2)
        first_call_system = mock_client.messages.create.call_args_list[0].kwargs["system"]
        second_call_system = mock_client.messages.create.call_args_list[1].kwargs["system"]
        self.assertNotIn("did not follow the required structure", first_call_system)
        self.assertIn("did not follow the required structure", second_call_system)

    def test_raises_value_error_for_empty_context(self) -> None:
        with self.assertRaises(ValueError):
            generate_context_recap("")

    def test_summary_generation_compresses_context_before_main_prompt(self) -> None:
        canonical_result = CanonicalLLMGenerationResult(
            canonical_text=VALID_CANONICAL_RECORD,
            record=parse_canonical_record(VALID_CANONICAL_RECORD),
            was_chunked=False,
        )
        with patch(
            "cartero.generator.llm.generate_context_recap",
            return_value=VALID_RECAP,
        ) as mock_recap, patch(
            "cartero.generator.llm.generate_canonical_record_result",
            return_value=canonical_result,
        ) as mock_summary:
            result = generate_summary_result_from_diff(
                "diff --git a/x b/x",
                raw_context="messy copied notes",
            )

        self.assertEqual(result.canonical_text, VALID_CANONICAL_RECORD)
        self.assertEqual(result.record, canonical_result.record)
        self.assertIn("summary:", result.yaml_text)
        mock_recap.assert_called_once_with("messy copied notes", llm_module.default_config)
        mock_summary.assert_called_once_with(
            "diff --git a/x b/x",
            self.BASE_CONFIG,
            context_recap=VALID_RECAP,
            extra_system_prompt=llm_module.COMMIT_BRIDGE_CANONICAL_GUIDANCE,
        )

    def test_main_generation_prompt_includes_recap_and_diff(self) -> None:
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _make_llm_response(VALID_CANONICAL_RECORD)

        with patch("cartero.llm.os.getenv", return_value="unit-test-key"), patch(
            "cartero.llm.Anthropic", return_value=mock_client
        ):
            generate_commit_summary_result("diff --git a/x b/x", context_recap=VALID_RECAP)

        prompt_text = mock_client.messages.create.call_args.kwargs["messages"][0]["content"]
        self.assertIn("Structured context recap:\nGoal:", prompt_text)
        self.assertIn("Git diff:\ndiff --git a/x b/x", prompt_text)

    def _patch_anthropic(self, response_text: str):
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _make_llm_response(response_text)
        return patch.multiple(
            "cartero.llm",
            Anthropic=MagicMock(return_value=mock_client),
            os=MagicMock(getenv=MagicMock(return_value="unit-test-key")),
        )


class TruncationTests(unittest.TestCase):
    """Large diffs should propagate the chunking warning."""

    TINY_CONFIG = CarteroConfig(max_diff_tokens=1)

    def test_warning_message_when_truncated(self) -> None:
        big_diff = (
            "diff --git a/file1.py b/file1.py\n"
            "+ " + "x" * 100 + "\n"
            "diff --git a/file2.py b/file2.py\n"
            "+ " + "y" * 100 + "\n"
        )
        with self._patch_anthropic(VALID_CANONICAL_RECORD):
            result = generate_summary_result_from_diff(big_diff, config=self.TINY_CONFIG)

        self.assertEqual(result.warning_message, CHUNKED_DIFF_WARNING)
        self.assertTrue(result.canonical_text.startswith("<<<CARTERO_RECORD_V1>>>"))
        self.assertIn(
            "Cartero now explains network documentation changes in plain language.",
            result.canonical_text,
        )

    def test_no_warning_when_not_truncated(self) -> None:
        small_diff = "x" * 3
        with self._patch_anthropic(VALID_CANONICAL_RECORD):
            result = generate_summary_result_from_diff(small_diff, config=self.TINY_CONFIG)

        self.assertIsNone(result.warning_message)

    def test_yaml_still_returned_when_truncated(self) -> None:
        big_diff = "x" * 1000
        with self._patch_anthropic(VALID_CANONICAL_RECORD):
            result = generate_summary_result_from_diff(big_diff, config=self.TINY_CONFIG)

        self.assertIn("summary:", result.yaml_text)

    def test_cli_prints_warning_to_stderr(self) -> None:
        import io
        from contextlib import redirect_stderr, redirect_stdout
        from cartero.cli import handle_generate

        mock_args = MagicMock()
        mock_args.diff_file = None
        mock_args.stdin = False

        with patch("cartero.cli.generate_summary_result_from_diff") as mock_generate, patch(
            "cartero.cli.get_diff", return_value="fake diff content"
        ):
            mock_generate.return_value = SummaryGenerationResult(
                record=parse_canonical_record(VALID_CANONICAL_RECORD),
                canonical_text=VALID_CANONICAL_RECORD,
                yaml_text="summary: test\n",
                warning_message=CHUNKED_DIFF_WARNING,
            )
            stdout = io.StringIO()
            stderr = io.StringIO()
            console = __import__("rich.console", fromlist=["Console"]).Console(
                file=stdout, force_terminal=False, color_system=None
            )
            error_console = __import__("rich.console", fromlist=["Console"]).Console(
                file=stderr, force_terminal=False, color_system=None
            )
            exit_code = handle_generate(mock_args, console, error_console)

        self.assertEqual(exit_code, 0)
        self.assertIn("warning", stderr.getvalue().lower())
        self.assertIn("summary: test", stdout.getvalue())

    def _patch_anthropic(self, response_text: str):
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _make_llm_response(response_text)
        return patch.multiple(
            "cartero.llm",
            Anthropic=MagicMock(return_value=mock_client),
            os=MagicMock(getenv=MagicMock(return_value="unit-test-key")),
        )


class RetryTests(unittest.TestCase):
    """Retries should keep working with the canonical record contract."""

    BASE_CONFIG = CarteroConfig(max_retries=3)

    def test_succeeds_on_second_attempt(self) -> None:
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = [
            _make_llm_response("not a canonical record"),
            _make_llm_response(VALID_CANONICAL_RECORD),
        ]
        with patch("cartero.llm.os.getenv", return_value="unit-test-key"), patch(
            "cartero.llm.Anthropic", return_value=mock_client
        ):
            result = generate_summary_from_diff("some diff", config=self.BASE_CONFIG)

        self.assertIn("summary:", result)
        self.assertEqual(mock_client.messages.create.call_count, 2)

    def test_strict_prompt_used_on_retry(self) -> None:
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = [
            _make_llm_response("not a canonical record"),
            _make_llm_response(VALID_CANONICAL_RECORD),
        ]
        with patch("cartero.llm.os.getenv", return_value="unit-test-key"), patch(
            "cartero.llm.Anthropic", return_value=mock_client
        ):
            generate_summary_from_diff("some diff", config=self.BASE_CONFIG)

        first_call_system = mock_client.messages.create.call_args_list[0].kwargs["system"]
        second_call_system = mock_client.messages.create.call_args_list[1].kwargs["system"]

        self.assertNotIn("IMPORTANT", first_call_system)
        self.assertIn("IMPORTANT", second_call_system)

    def test_raises_after_all_retries_exhausted(self) -> None:
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _make_llm_response("bad canonical output")

        with patch("cartero.llm.os.getenv", return_value="unit-test-key"), patch(
            "cartero.llm.Anthropic", return_value=mock_client
        ):
            with self.assertRaises(LLMCallError) as ctx:
                generate_summary_from_diff("some diff", config=self.BASE_CONFIG)

        self.assertIn("Failed after 3 attempts", str(ctx.exception))
        self.assertEqual(mock_client.messages.create.call_count, 3)

    def test_empty_response_triggers_retry(self) -> None:
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = [
            _make_llm_response(""),
            _make_llm_response(VALID_CANONICAL_RECORD),
        ]
        with patch("cartero.llm.os.getenv", return_value="unit-test-key"), patch(
            "cartero.llm.Anthropic", return_value=mock_client
        ):
            result = generate_summary_from_diff("some diff", config=self.BASE_CONFIG)

        self.assertIn("summary:", result)


class ChangelogGenerationTests(unittest.TestCase):
    BASE_CONFIG = CarteroConfig(max_retries=3)

    def test_returns_trimmed_changelog_text(self) -> None:
        with patch("cartero.llm._get_client", return_value=object()) as mock_get_client, patch(
            "cartero.llm._call_llm",
            return_value="  Cartero now shows a changelog preview before execution.  \n",
        ) as mock_call_llm:
            result = generate_changelog("diff --git a/x b/x", config=self.BASE_CONFIG)

        self.assertEqual(result, "Cartero now shows a changelog preview before execution.")
        mock_get_client.assert_called_once_with(self.BASE_CONFIG)
        mock_call_llm.assert_called_once()
        self.assertEqual(mock_call_llm.call_args.kwargs["stream"], True)

    def test_prompt_includes_context_recap_when_provided(self) -> None:
        with patch("cartero.llm._get_client", return_value=object()), patch(
            "cartero.llm._call_llm",
            return_value="Cartero now shows a changelog preview before execution.",
        ) as mock_call_llm:
            generate_changelog(
                "diff --git a/x b/x",
                config=self.BASE_CONFIG,
                context_recap=VALID_RECAP,
            )

        prompt_text = mock_call_llm.call_args.args[1]
        self.assertIn("Structured context recap:\nGoal:", prompt_text)
        self.assertIn("Git diff:\ndiff --git a/x b/x", prompt_text)

    def test_retries_when_model_returns_empty_output(self) -> None:
        with patch("cartero.llm._get_client", return_value=object()), patch(
            "cartero.llm._call_llm",
            side_effect=["   ", "Final changelog text"],
        ) as mock_call_llm:
            result = generate_changelog("diff --git a/x b/x", config=self.BASE_CONFIG)

        self.assertEqual(result, "Final changelog text")
        self.assertEqual(mock_call_llm.call_count, 2)
        first_call = mock_call_llm.call_args_list[0]
        second_call = mock_call_llm.call_args_list[1]
        self.assertEqual(first_call.kwargs["strict"], False)
        self.assertEqual(second_call.kwargs["strict"], True)


class CommitBridgeQualityTests(unittest.TestCase):
    BASE_CONFIG = CarteroConfig(max_retries=2)

    def test_bridge_reason_is_never_empty(self) -> None:
        yaml_text = llm_module.render_legacy_yaml_bridge(
            parse_canonical_record(VALID_CANONICAL_RECORD)
        )

        payload = yaml.safe_load(yaml_text)
        self.assertTrue(payload["reason"].strip())

    def test_bridge_impact_is_not_multiline(self) -> None:
        yaml_text = llm_module.render_legacy_yaml_bridge(
            parse_canonical_record(VALID_CANONICAL_RECORD)
        )

        payload = yaml.safe_load(yaml_text)
        self.assertNotIn("\n", payload["impact"])
        self.assertLessEqual(len(payload["impact"]), 220)

    def test_bridge_output_stays_parseable_for_current_flow(self) -> None:
        yaml_text = llm_module.render_legacy_yaml_bridge(
            parse_canonical_record(VALID_CANONICAL_RECORD),
            context_recap=VALID_RECAP,
        )

        payload = yaml.safe_load(yaml_text)
        self.assertEqual(set(payload.keys()), {"summary", "reason", "impact", "actions"})
        self.assertIsInstance(payload["actions"], list)

    def test_large_diff_path_stays_brief_when_mocked(self) -> None:
        long_record = parse_canonical_record(
            _build_canonical_record(
                "Cartero now gives teams a clearer way to review broad communication changes across the product without getting lost in implementation detail.",
                (
                    "Cartero now unifies parser, validator, bridge, canonical record rendering, retry handling, and output cleanup across multiple internal flows.\n\n"
                    "- It removes several technical inconsistencies between old and new generation paths\n"
                    "- It keeps the human-facing output focused on the highest-value outcome"
                ),
            )
        )
        canonical_result = CanonicalLLMGenerationResult(
            canonical_text=_render_canonical_record_for_test(long_record),
            record=long_record,
            was_chunked=False,
        )
        with patch(
            "cartero.generator.llm.generate_context_recap",
            return_value=VALID_RECAP,
        ), patch(
            "cartero.generator.llm.generate_canonical_record_result",
            return_value=canonical_result,
        ):
            result = generate_summary_result_from_diff(
                "diff --git a/x b/x",
                config=self.BASE_CONFIG,
                raw_context="messy copied notes",
            )

        payload = yaml.safe_load(result.yaml_text)
        self.assertLessEqual(len(payload["summary"]), 160)
        self.assertLessEqual(len(payload["impact"]), 220)
        self.assertNotIn("\n", payload["impact"])

    def test_quality_retry_triggers_for_valid_but_bad_content(self) -> None:
        bad_record = parse_canonical_record(
            _build_canonical_record(
                (
                    "Cartero now introduces a very long technical explanation about parser normalization, "
                    "context recap handling, canonical bridge wiring, YAML rendering compatibility, and "
                    "internal retry coordination across generation paths for multiple surfaces."
                ),
                "Cartero now keeps communication output aligned.",
            )
        )
        good_record = parse_canonical_record(VALID_CANONICAL_RECORD)
        with patch(
            "cartero.generator.llm.generate_canonical_record_result",
            side_effect=[
                CanonicalLLMGenerationResult(
                    canonical_text=_render_canonical_record_for_test(bad_record),
                    record=bad_record,
                    was_chunked=False,
                ),
                CanonicalLLMGenerationResult(
                    canonical_text=VALID_CANONICAL_RECORD,
                    record=good_record,
                    was_chunked=False,
                ),
            ],
        ) as mock_generate:
            result = generate_summary_result_from_diff(
                "diff --git a/x b/x",
                config=self.BASE_CONFIG,
            )

        self.assertEqual(mock_generate.call_count, 2)
        self.assertIn(
            "structurally valid but not concise enough",
            mock_generate.call_args_list[1].kwargs["extra_system_prompt"],
        )
        payload = yaml.safe_load(result.yaml_text)
        self.assertTrue(payload["reason"].strip())


class CanonicalGenerationTests(unittest.TestCase):
    BASE_CONFIG = CarteroConfig(max_retries=3)

    def test_generate_canonical_record_result_returns_parsed_record(self) -> None:
        with self._patch_anthropic(VALID_CANONICAL_RECORD_WITH_ITEMS):
            result = generate_canonical_record_result("diff --git a/x b/x")

        self.assertEqual(
            result.record.summary,
            "Cartero now keeps documentation changes aligned with a reusable communication record.",
        )
        self.assertEqual(len(result.record.faq_items), 1)
        self.assertEqual(
            result.record.faq_items[0].question,
            "What changed in the communication pipeline?",
        )
        self.assertEqual(len(result.record.knowledge_base_items), 1)

    def test_canonical_prompt_excludes_actions_json_contract(self) -> None:
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _make_llm_response(VALID_CANONICAL_RECORD)

        with patch("cartero.llm.os.getenv", return_value="unit-test-key"), patch(
            "cartero.llm.Anthropic", return_value=mock_client
        ):
            generate_canonical_record_result("diff --git a/x b/x")

        system_prompt = mock_client.messages.create.call_args.kwargs["system"]
        self.assertIn("CARTERO_RECORD_V1", system_prompt)
        self.assertIn("Do not include ACTIONS", system_prompt)
        self.assertNotIn('"actions"', system_prompt)

    def test_chunked_canonical_generation_merges_records(self) -> None:
        diff_text = (
            "diff --git a/a.py b/a.py\n"
            "+ a\n"
            "diff --git a/b.py b/b.py\n"
            "+ b\n"
        )
        config = CarteroConfig(max_diff_tokens=10, max_retries=2)
        first_chunk_record = _build_canonical_record(
            "Cartero now keeps multi-file communication consistent.",
            "First chunk changelog.\n\n- First chunk detail",
        )
        second_chunk_record = _build_canonical_record(
            "Cartero now keeps multi-file communication consistent.",
            "Second chunk changelog.\n\n- Second chunk detail",
        )
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = [
            _make_llm_response(first_chunk_record),
            _make_llm_response(second_chunk_record),
        ]

        with patch("cartero.llm.os.getenv", return_value="unit-test-key"), patch(
            "cartero.llm.Anthropic", return_value=mock_client
        ):
            result = generate_canonical_record_result(diff_text, config=config)

        self.assertTrue(result.was_chunked)
        self.assertIn("First chunk changelog.", result.record.changelog)
        self.assertIn("Second chunk changelog.", result.record.changelog)
        self.assertEqual(mock_client.messages.create.call_count, 2)

    def _patch_anthropic(self, response_text: str):
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _make_llm_response(response_text)
        return patch.multiple(
            "cartero.llm",
            Anthropic=MagicMock(return_value=mock_client),
            os=MagicMock(getenv=MagicMock(return_value="unit-test-key")),
        )


class ValidationTests(unittest.TestCase):
    """Input and configuration validation errors."""

    def test_raises_value_error_for_empty_diff(self) -> None:
        with self.assertRaises(ValueError):
            generate_summary_from_diff("")

    def test_raises_value_error_for_whitespace_diff(self) -> None:
        with self.assertRaises(ValueError):
            generate_summary_from_diff("   \n  ")

    def test_raises_llm_config_error_without_api_key(self) -> None:
        with patch("cartero.llm.os.getenv", return_value=None):
            with self.assertRaises(LLMConfigError) as ctx:
                generate_summary_from_diff("some diff")
        self.assertIn("ANTHROPIC_API_KEY is not configured", str(ctx.exception))

    def test_anthropic_client_requires_explicit_api_key_without_fallback(self) -> None:
        with patch("cartero.llm.os.getenv", return_value=None) as mock_getenv, patch(
            "cartero.llm.Anthropic"
        ) as mock_anthropic:
            with self.assertRaises(LLMConfigError) as ctx:
                llm_module._get_client(CarteroConfig(llm_provider="anthropic"))

        mock_getenv.assert_called_once_with("ANTHROPIC_API_KEY")
        mock_anthropic.assert_not_called()
        self.assertIn("ANTHROPIC_API_KEY is not configured", str(ctx.exception))

    def test_anthropic_client_rejects_empty_api_key(self) -> None:
        with patch("cartero.llm.os.getenv", return_value="   "), patch(
            "cartero.llm.Anthropic"
        ) as mock_anthropic:
            with self.assertRaises(LLMConfigError) as ctx:
                llm_module._get_client(CarteroConfig(llm_provider="anthropic"))

        mock_anthropic.assert_not_called()
        self.assertIn("ANTHROPIC_API_KEY is not configured", str(ctx.exception))

    def test_raises_llm_config_error_for_unknown_provider(self) -> None:
        bad_config = CarteroConfig(llm_provider="openai")
        with patch("cartero.llm.os.getenv", return_value="fake-key"):
            with self.assertRaises(LLMConfigError) as ctx:
                generate_summary_from_diff("some diff", config=bad_config)
        self.assertIn("openai", str(ctx.exception))
