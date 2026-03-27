from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from cartero.config import CarteroConfig
from cartero.generator import (
    CHUNKED_DIFF_WARNING,
    SummaryGenerationResult,
    generate_context_recap,
    generate_summary_from_diff,
    generate_summary_result_from_diff,
)
from cartero.llm import (
    LLMCallError,
    LLMConfigError,
    LLMGenerationResult,
    generate_commit_summary_result,
)


VALID_JSON = """{
  "summary": "Add network docs",
  "reason": "Document infrastructure",
  "impact": "Devs can read the docs",
  "actions": [
    {
      "repo": "casadora-core",
      "type": "write",
      "path": "docs/network.md",
      "content": "# Network\\n"
    }
  ]
}"""

VALID_RECAP = """Goal: Keep Cartero outputs aligned with user intent.
User problem: Raw conversation context is noisy and makes downstream summaries inconsistent.
Key decisions: Compress notes into a fixed recap focused on intent, tradeoffs, and user-visible outcomes.
Tradeoffs: Some implementation detail is omitted to keep the recap concise.
Expected user-visible outcome: Generated summaries and explanations stay focused on why the change matters.
Explanation for non-technical users: Cartero now turns messy notes into a short brief that explains the purpose of a change in plain language.
"""


def _make_llm_response(text: str) -> MagicMock:
    """Construye el objeto que devuelve client.messages.create."""
    block = MagicMock()
    block.type = "text"
    block.text = text
    response = MagicMock()
    response.content = [block]
    return response


class HappyPathTests(unittest.TestCase):
    """Caso 1: diff normal, sin truncar, modelo responde JSON valido."""

    def test_returns_yaml_string(self) -> None:
        with self._patch_anthropic(VALID_JSON):
            result = generate_summary_from_diff("diff --git a/x b/x")

        self.assertIsInstance(result, str)
        self.assertIn("summary:", result)
        self.assertIn("actions:", result)

    def test_no_warning_when_diff_is_small(self) -> None:
        with self._patch_anthropic(VALID_JSON):
            result = generate_summary_result_from_diff("diff --git a/x b/x")

        self.assertIsNone(result.warning_message)

    def test_result_is_summary_generation_result(self) -> None:
        with self._patch_anthropic(VALID_JSON):
            result = generate_summary_result_from_diff("diff --git a/x b/x")

        self.assertIsInstance(result, SummaryGenerationResult)
        self.assertIsInstance(result.yaml_text, str)

    def test_strips_markdown_fences(self) -> None:
        fenced = f"```json\n{VALID_JSON}\n```"
        with self._patch_anthropic(fenced):
            result = generate_summary_from_diff("diff --git a/x b/x")

        self.assertIn("summary:", result)

    def test_uses_only_diff_when_context_is_missing(self) -> None:
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _make_llm_response(VALID_JSON)

        with patch("cartero.llm.Anthropic", return_value=mock_client):
            generate_commit_summary_result("diff --git a/x b/x")

        prompt_text = mock_client.messages.create.call_args.kwargs["messages"][0]["content"]
        self.assertEqual(prompt_text, "diff --git a/x b/x")

    def _patch_anthropic(self, response_text: str):
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _make_llm_response(response_text)
        return patch("cartero.llm.Anthropic", return_value=mock_client)


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

        with patch("cartero.llm.Anthropic", return_value=mock_client):
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
        with patch(
            "cartero.generator.llm.generate_context_recap",
            return_value=VALID_RECAP,
        ) as mock_recap, patch(
            "cartero.generator.llm.generate_commit_summary_result",
            return_value=LLMGenerationResult(yaml_text="summary: test\n", was_chunked=False),
        ) as mock_summary:
            result = generate_summary_result_from_diff(
                "diff --git a/x b/x",
                raw_context="messy copied notes",
            )

        self.assertEqual(result.yaml_text, "summary: test\n")
        mock_recap.assert_called_once_with("messy copied notes", None)
        mock_summary.assert_called_once_with(
            "diff --git a/x b/x",
            None,
            context_recap=VALID_RECAP,
        )

    def test_main_generation_prompt_includes_recap_and_diff(self) -> None:
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _make_llm_response(VALID_JSON)

        with patch("cartero.llm.Anthropic", return_value=mock_client):
            generate_commit_summary_result("diff --git a/x b/x", context_recap=VALID_RECAP)

        prompt_text = mock_client.messages.create.call_args.kwargs["messages"][0]["content"]
        self.assertIn("Structured context recap:\nGoal:", prompt_text)
        self.assertIn("Git diff:\ndiff --git a/x b/x", prompt_text)

    def _patch_anthropic(self, response_text: str):
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _make_llm_response(response_text)
        return patch("cartero.llm.Anthropic", return_value=mock_client)


class TruncationTests(unittest.TestCase):
    """Caso 2: diff grande, debe truncar y propagar warning."""

    TINY_CONFIG = CarteroConfig(max_diff_tokens=1)

    def test_warning_message_when_truncated(self) -> None:
        big_diff = (
            "diff --git a/file1.py b/file1.py\n"
            "+ " + "x" * 100 + "\n"
            "diff --git a/file2.py b/file2.py\n"
            "+ " + "y" * 100 + "\n"
        )
        with self._patch_anthropic(VALID_JSON):
            result = generate_summary_result_from_diff(big_diff, config=self.TINY_CONFIG)

        self.assertEqual(result.warning_message, CHUNKED_DIFF_WARNING)

    def test_no_warning_when_not_truncated(self) -> None:
        small_diff = "x" * 3
        with self._patch_anthropic(VALID_JSON):
            result = generate_summary_result_from_diff(small_diff, config=self.TINY_CONFIG)

        self.assertIsNone(result.warning_message)

    def test_yaml_still_returned_when_truncated(self) -> None:
        big_diff = "x" * 1000
        with self._patch_anthropic(VALID_JSON):
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
        return patch("cartero.llm.Anthropic", return_value=mock_client)


class RetryTests(unittest.TestCase):
    """Caso 3: modelo falla N veces, retry con prompt estricto."""

    BASE_CONFIG = CarteroConfig(max_retries=3)

    def test_succeeds_on_second_attempt(self) -> None:
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = [
            _make_llm_response("not valid json {{{"),
            _make_llm_response(VALID_JSON),
        ]
        with patch("cartero.llm.Anthropic", return_value=mock_client):
            result = generate_summary_from_diff("some diff", config=self.BASE_CONFIG)

        self.assertIn("summary:", result)
        self.assertEqual(mock_client.messages.create.call_count, 2)

    def test_strict_prompt_used_on_retry(self) -> None:
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = [
            _make_llm_response("not valid json"),
            _make_llm_response(VALID_JSON),
        ]
        with patch("cartero.llm.Anthropic", return_value=mock_client):
            generate_summary_from_diff("some diff", config=self.BASE_CONFIG)

        first_call_system = mock_client.messages.create.call_args_list[0].kwargs["system"]
        second_call_system = mock_client.messages.create.call_args_list[1].kwargs["system"]

        self.assertNotIn("IMPORTANT", first_call_system)
        self.assertIn("IMPORTANT", second_call_system)

    def test_raises_after_all_retries_exhausted(self) -> None:
        mock_client = MagicMock()
        mock_client.messages.create.return_value = _make_llm_response("bad json {{{")

        with patch("cartero.llm.Anthropic", return_value=mock_client):
            with self.assertRaises(LLMCallError) as ctx:
                generate_summary_from_diff("some diff", config=self.BASE_CONFIG)

        self.assertIn("Failed after 3 attempts", str(ctx.exception))
        self.assertEqual(mock_client.messages.create.call_count, 3)

    def test_empty_response_triggers_retry(self) -> None:
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = [
            _make_llm_response(""),
            _make_llm_response(VALID_JSON),
        ]
        with patch("cartero.llm.Anthropic", return_value=mock_client):
            result = generate_summary_from_diff("some diff", config=self.BASE_CONFIG)

        self.assertIn("summary:", result)


class ValidationTests(unittest.TestCase):
    """Casos de error en entrada o config."""

    def test_raises_value_error_for_empty_diff(self) -> None:
        with self.assertRaises(ValueError):
            generate_summary_from_diff("")

    def test_raises_value_error_for_whitespace_diff(self) -> None:
        with self.assertRaises(ValueError):
            generate_summary_from_diff("   \n  ")

    def test_raises_llm_config_error_without_api_key(self) -> None:
        with patch("cartero.llm.os.getenv", return_value=None):
            with self.assertRaises(LLMConfigError):
                generate_summary_from_diff("some diff")

    def test_raises_llm_config_error_for_unknown_provider(self) -> None:
        bad_config = CarteroConfig(llm_provider="openai")
        with patch("cartero.llm.os.getenv", return_value="fake-key"):
            with self.assertRaises(LLMConfigError) as ctx:
                generate_summary_from_diff("some diff", config=bad_config)
        self.assertIn("openai", str(ctx.exception))
