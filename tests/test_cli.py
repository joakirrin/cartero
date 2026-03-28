from __future__ import annotations

import io
import runpy
import tempfile
import unittest
import warnings
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from cartero.cli import main
from cartero.executor import execute_actions as real_execute_actions
from cartero.generator import SummaryGenerationResult


class CliTests(unittest.TestCase):
    def test_cli_defaults_to_dry_run(self) -> None:
        exit_code, output, error = self._run_main(["tests/fixtures/sample_summary.yaml"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(error, "")
        self.assertIn("Cartero dry-run plan", output)
        self.assertIn("Mode: dry-run", output)
        self.assertIn("Validated actions: 3", output)
        self.assertIn("casadora-core (1 action)", output)
        self.assertIn("simulate write file: docs/architecture/network.md", output)
        self.assertIn("content preview:", output)
        self.assertIn("# Network", output)
        self.assertIn("casadora-services (1 action)", output)
        self.assertIn("simulate delete file: docker/legacy-compose.yaml", output)
        self.assertIn("cartero (1 action)", output)
        self.assertIn("simulate mkdir dir: tests/fixtures/generated", output)
        self.assertIn("No file or git changes were made.", output)

    def test_cli_accepts_explicit_dry_run(self) -> None:
        exit_code, output, error = self._run_main(
            ["--dry-run", "tests/fixtures/sample_summary.yaml"]
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(error, "")
        self.assertIn("Cartero dry-run plan", output)
        self.assertIn("Mode: dry-run", output)
        self.assertIn("No file or git changes were made.", output)

    def test_cli_apply_calls_executor(self) -> None:
        with patch("cartero.cli.execute_actions", wraps=real_execute_actions) as mock_execute:
            exit_code, output, error = self._run_main(
                ["--apply", "tests/fixtures/sample_summary.yaml"]
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(error, "")
        self.assertIn("Cartero apply plan", output)
        self.assertIn("Mode: apply", output)
        self.assertIn("Simulated execution", output)
        self.assertIn("[executing] write -> docs/architecture/network.md", output)
        self.assertIn("[executing] delete -> docker/legacy-compose.yaml", output)
        self.assertIn("[executing] mkdir -> tests/fixtures/generated", output)
        self.assertNotIn("No file or git changes were made.", output)
        self.assertLess(output.index("Cartero apply plan"), output.index("Simulated execution"))
        self.assertLess(output.index("Simulated execution"), output.index("[executing]"))
        mock_execute.assert_called_once()

        called_changes = mock_execute.call_args.args[0]
        self.assertEqual(len(called_changes), 3)
        self.assertEqual(called_changes[0].change_type, "write")
        self.assertEqual(called_changes[1].change_type, "delete")
        self.assertEqual(called_changes[2].change_type, "mkdir")
        self.assertIn("console", mock_execute.call_args.kwargs)

    def test_cli_rejects_conflicting_mode_flags(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()

        with self.assertRaises(SystemExit) as context:
            with redirect_stdout(stdout), redirect_stderr(stderr):
                main(["--apply", "--dry-run", "tests/fixtures/sample_summary.yaml"])

        self.assertEqual(context.exception.code, 2)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("not allowed with argument", stderr.getvalue())

    def test_cli_returns_error_for_invalid_summary(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            summary_path = Path(temp_dir) / "invalid.yaml"
            summary_path.write_text("actions:\n  - repo: cartero\n", encoding="utf-8")

            stdout = io.StringIO()
            stderr = io.StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                exit_code = main([str(summary_path)])

        self.assertEqual(exit_code, 2)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("error:", stderr.getvalue())

    def test_context_command_prints_structured_recap(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()
        stdin = io.StringIO("messy notes")

        with patch(
            "cartero.cli.generate_context_recap",
            return_value=(
                "Goal: Clarify intent.\n"
                "User problem: Notes are noisy.\n"
                "Key decisions: Keep a fixed recap format.\n"
                "Tradeoffs: Less implementation detail.\n"
                "Expected user-visible outcome: Clearer generated outputs.\n"
                "Explanation for non-technical users: Cartero explains why a change matters.\n"
            ),
        ), patch("sys.stdin", stdin), redirect_stdout(stdout), redirect_stderr(stderr):
            exit_code = main(["context"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr.getvalue(), "")
        self.assertIn("Goal: Clarify intent.", stdout.getvalue())

    def test_generate_command_passes_optional_context(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            diff_path = Path(temp_dir) / "changes.diff"
            context_path = Path(temp_dir) / "context.txt"
            diff_path.write_text("diff --git a/x b/x\n", encoding="utf-8")
            context_path.write_text("messy notes", encoding="utf-8")

            stdout = io.StringIO()
            stderr = io.StringIO()
            with patch(
                "cartero.cli.generate_summary_result_from_diff",
                return_value=SummaryGenerationResult(
                    yaml_text="summary: test\n",
                    warning_message=None,
                ),
            ) as mock_generate, redirect_stdout(stdout), redirect_stderr(stderr):
                exit_code = main(
                    [
                        "generate",
                        "--diff-file",
                        str(diff_path),
                        "--context-file",
                        str(context_path),
                    ]
                )

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr.getvalue(), "")
        mock_generate.assert_called_once_with(
            "diff --git a/x b/x\n",
            raw_context="messy notes",
        )

    def test_generate_command_uses_git_diff_by_default(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()

        with patch(
            "cartero.cli.get_diff",
            return_value="diff --git a/x b/x\n",
        ), patch(
            "cartero.cli.generate_summary_result_from_diff",
            return_value=SummaryGenerationResult(
                yaml_text="summary: test\n",
                warning_message=None,
            ),
        ) as mock_generate, redirect_stdout(stdout), redirect_stderr(stderr):
            exit_code = main(["generate"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr.getvalue(), "")
        mock_generate.assert_called_once_with(
            "diff --git a/x b/x\n",
            raw_context=None,
        )

    def test_generate_command_reads_stdin_only_when_requested(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()
        stdin = io.StringIO("diff --git a/x b/x\n")

        with patch(
            "cartero.cli.generate_summary_result_from_diff",
            return_value=SummaryGenerationResult(
                yaml_text="summary: test\n",
                warning_message=None,
            ),
        ) as mock_generate, patch("sys.stdin", stdin), redirect_stdout(stdout), redirect_stderr(stderr):
            exit_code = main(["generate", "--stdin"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr.getvalue(), "")
        mock_generate.assert_called_once_with(
            "diff --git a/x b/x\n",
            raw_context=None,
        )

    def test_generate_command_shows_message_when_no_diff_is_detected(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()

        with patch("cartero.cli.get_diff", return_value=""), redirect_stdout(stdout), redirect_stderr(
            stderr
        ):
            exit_code = main(["generate"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr.getvalue(), "")
        self.assertIn(
            "No changes detected. You can paste a diff or make changes first.",
            stdout.getvalue(),
        )

    def test_generate_with_empty_diff_and_context_is_conservative(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()

        with patch(
            "cartero.cli.get_diff",
            return_value="",
        ), patch(
            "cartero.cli.generate_summary_result_from_diff",
            return_value=SummaryGenerationResult(
                yaml_text="summary: no-op\n",
                warning_message=None,
            ),
        ) as mock_generate, redirect_stdout(stdout), redirect_stderr(stderr):
            exit_code = main(["generate"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr.getvalue(), "")
        mock_generate.assert_not_called()
        self.assertIn("No changes detected", stdout.getvalue())

    def test_generate_with_ambiguous_diff_passes_raw_diff_without_overstating_input(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            diff_path = Path("tests/fixtures/extreme_cases/ambiguous_diff/diff.txt")
            context_path = Path("tests/fixtures/extreme_cases/ambiguous_diff/context.txt")

            stdout = io.StringIO()
            stderr = io.StringIO()

            diff_text = diff_path.read_text(encoding="utf-8")
            context_text = context_path.read_text(encoding="utf-8")

            with patch(
                "cartero.cli.generate_summary_result_from_diff",
                return_value=SummaryGenerationResult(
                    yaml_text="summary: conservative\n",
                    warning_message=None,
                ),
            ) as mock_generate, redirect_stdout(stdout), redirect_stderr(stderr):
                exit_code = main(
                    [
                        "generate",
                        "--diff-file",
                        str(diff_path),
                        "--context-file",
                        str(context_path),
                    ]
                )

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr.getvalue(), "")
        self.assertEqual(stdout.getvalue(), "summary: conservative\n")

        mock_generate.assert_called_once_with(
            diff_text,
            raw_context=context_text,
        )

    def test_generate_with_partial_rollout_passes_partial_scope_inputs_without_expanding_them(
        self,
    ) -> None:
        diff_path = Path("tests/fixtures/extreme_cases/partial_rollout/diff.txt")
        context_path = Path("tests/fixtures/extreme_cases/partial_rollout/context.txt")

        stdout = io.StringIO()
        stderr = io.StringIO()

        diff_text = diff_path.read_text(encoding="utf-8")
        context_text = context_path.read_text(encoding="utf-8")

        with patch(
            "cartero.cli.generate_summary_result_from_diff",
            return_value=SummaryGenerationResult(
                yaml_text="summary: partial rollout\n",
                warning_message=None,
            ),
        ) as mock_generate, redirect_stdout(stdout), redirect_stderr(stderr):
            exit_code = main(
                [
                    "generate",
                    "--diff-file",
                    str(diff_path),
                    "--context-file",
                    str(context_path),
                ]
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr.getvalue(), "")
        self.assertEqual(stdout.getvalue(), "summary: partial rollout\n")

        mock_generate.assert_called_once_with(
            diff_text,
            raw_context=context_text,
        )

    def test_generate_with_tests_only_diff_passes_input_without_claiming_product_change(
        self,
    ) -> None:
        diff_path = Path("tests/fixtures/extreme_cases/tests_only/diff.txt")
        context_path = Path("tests/fixtures/extreme_cases/tests_only/context.txt")

        stdout = io.StringIO()
        stderr = io.StringIO()

        diff_text = diff_path.read_text(encoding="utf-8")
        context_text = context_path.read_text(encoding="utf-8")

        with patch(
            "cartero.cli.generate_summary_result_from_diff",
            return_value=SummaryGenerationResult(
                yaml_text="summary: tests only\n",
                warning_message=None,
            ),
        ) as mock_generate, redirect_stdout(stdout), redirect_stderr(stderr):
            exit_code = main(
                [
                    "generate",
                    "--diff-file",
                    str(diff_path),
                    "--context-file",
                    str(context_path),
                ]
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr.getvalue(), "")
        self.assertEqual(stdout.getvalue(), "summary: tests only\n")
        mock_generate.assert_called_once_with(diff_text, raw_context=context_text)

    def test_generate_with_many_changes_passes_full_input_for_downstream_grouping(
        self,
    ) -> None:
        diff_path = Path("tests/fixtures/extreme_cases/many_changes/diff.txt")
        context_path = Path("tests/fixtures/extreme_cases/many_changes/context.txt")

        stdout = io.StringIO()
        stderr = io.StringIO()

        diff_text = diff_path.read_text(encoding="utf-8")
        context_text = context_path.read_text(encoding="utf-8")

        with patch(
            "cartero.cli.generate_summary_result_from_diff",
            return_value=SummaryGenerationResult(
                yaml_text="summary: grouped changes\n",
                warning_message=None,
            ),
        ) as mock_generate, redirect_stdout(stdout), redirect_stderr(stderr):
            exit_code = main(
                [
                    "generate",
                    "--diff-file",
                    str(diff_path),
                    "--context-file",
                    str(context_path),
                ]
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr.getvalue(), "")
        self.assertEqual(stdout.getvalue(), "summary: grouped changes\n")
        mock_generate.assert_called_once_with(diff_text, raw_context=context_text)

    def test_module_generate_help_prints_usage(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()

        with patch("sys.argv", ["python", "generate", "--help"]), redirect_stdout(
            stdout
        ), redirect_stderr(stderr), warnings.catch_warnings(), self.assertRaises(
            SystemExit
        ) as context:
            warnings.simplefilter("ignore", RuntimeWarning)
            runpy.run_module("cartero.cli", run_name="__main__")

        self.assertEqual(context.exception.code, 0)
        self.assertEqual(stderr.getvalue(), "")
        self.assertIn("usage: cartero generate", stdout.getvalue())

    def test_module_generate_command_prints_output_for_explicit_subcommand(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            diff_path = Path(temp_dir) / "changes.diff"
            context_path = Path(temp_dir) / "context.txt"
            diff_path.write_text("diff --git a/x b/x\n", encoding="utf-8")
            context_path.write_text("messy notes", encoding="utf-8")

            stdout = io.StringIO()
            stderr = io.StringIO()

            with patch(
                "cartero.generator.generate_summary_result_from_diff",
                return_value=SummaryGenerationResult(
                    yaml_text="summary: module path\n",
                    warning_message=None,
                ),
            ) as mock_generate, patch(
                "sys.argv",
                [
                    "python",
                    "generate",
                    "--diff-file",
                    str(diff_path),
                    "--context-file",
                    str(context_path),
                ],
            ), redirect_stdout(stdout), redirect_stderr(stderr), self.assertRaises(
                SystemExit
            ) as context, warnings.catch_warnings():
                warnings.simplefilter("ignore", RuntimeWarning)
                runpy.run_module("cartero.cli", run_name="__main__")

        self.assertEqual(context.exception.code, 0)
        self.assertEqual(stderr.getvalue(), "")
        self.assertEqual(stdout.getvalue(), "summary: module path\n")
        mock_generate.assert_called_once_with(
            "diff --git a/x b/x\n",
            raw_context="messy notes",
        )

    def _run_main(self, argv: list[str]) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()

        with redirect_stdout(stdout), redirect_stderr(stderr):
            exit_code = main(argv)

        return exit_code, stdout.getvalue(), stderr.getvalue()


class InteractiveCliTests(unittest.TestCase):
    def test_cli_no_args_launches_interactive_summary_flow(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()
        stdin = io.StringIO("2\n1\n3\n")

        with patch("cartero.cli.get_changed_files", return_value=["cartero/cli.py"]), patch(
            "cartero.cli.get_diff", return_value="diff --git a/cartero/cli.py b/cartero/cli.py\n"
        ), patch(
            "cartero.cli.generate_summary_result_from_diff",
            return_value=SummaryGenerationResult(
                yaml_text="summary: test\n",
                warning_message=None,
            ),
        ) as mock_generate, patch("sys.stdin", stdin), redirect_stdout(stdout), redirect_stderr(
            stderr
        ):
            exit_code = main([])

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr.getvalue(), "")
        self.assertIn("I found changes in 1 file.", stdout.getvalue())
        self.assertIn("Generate summary", stdout.getvalue())
        self.assertIn("summary: test", stdout.getvalue())
        mock_generate.assert_called_once_with(
            "diff --git a/cartero/cli.py b/cartero/cli.py\n",
            raw_context=None,
        )

    def test_cli_no_args_explain_path_accepts_pasted_context(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()
        stdin = io.StringIO("1\n2\nfirst line\nsecond line\nEND\n3\n")

        with patch("cartero.cli.get_changed_files", return_value=["cartero/cli.py"]), patch(
            "cartero.cli.get_diff", return_value="diff --git a/cartero/cli.py b/cartero/cli.py\n"
        ), patch(
            "cartero.cli.generate_summary_result_from_diff",
            return_value=SummaryGenerationResult(
                yaml_text=(
                    "summary: Cartero now explains changes in plain language\n"
                    "reason: It was hard to understand diffs quickly\n"
                    "impact: You can review changes faster\n"
                    "actions: []\n"
                ),
                warning_message=None,
            ),
        ) as mock_generate, patch("sys.stdin", stdin), redirect_stdout(stdout), redirect_stderr(
            stderr
        ):
            exit_code = main([])

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr.getvalue(), "")
        self.assertIn("Explanation:", stdout.getvalue())
        self.assertIn("Why: It was hard to understand diffs quickly", stdout.getvalue())
        self.assertIn("Impact: You can review changes faster", stdout.getvalue())
        mock_generate.assert_called_once_with(
            "diff --git a/cartero/cli.py b/cartero/cli.py\n",
            raw_context="first line\nsecond line",
        )

    def test_cli_no_args_commit_path_reuses_commit_flow(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()
        stdin = io.StringIO("4\n1\na\ny\n")

        with patch(
            "cartero.cli.get_changed_files",
            side_effect=[["cartero/cli.py"], ["cartero/cli.py"]],
        ), patch(
            "cartero.cli.get_diff",
            side_effect=[
                "diff --git a/cartero/cli.py b/cartero/cli.py\n",
                "diff --git a/cartero/cli.py b/cartero/cli.py\n",
            ],
        ), patch("cartero.cli.stage_files") as mock_stage, patch(
            "cartero.cli.generate_summary_result_from_diff",
            return_value=SummaryGenerationResult(
                yaml_text=(
                    "summary: Cartero now commits guided changes\n"
                    "reason: Manual testing took too many steps\n"
                    "actions: []\n"
                ),
                warning_message=None,
            ),
        ) as mock_generate, patch(
            "cartero.cli.git_commit", return_value="abc1234"
        ) as mock_commit, patch("sys.stdin", stdin), redirect_stdout(stdout), redirect_stderr(
            stderr
        ):
            exit_code = main([])

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr.getvalue(), "")
        self.assertIn("Changed files:", stdout.getvalue())
        self.assertIn("abc1234", stdout.getvalue())
        mock_stage.assert_called_once_with(["cartero/cli.py"])
        mock_generate.assert_called_once_with(
            "diff --git a/cartero/cli.py b/cartero/cli.py\n",
            raw_context=None,
        )
        mock_commit.assert_called_once_with(
            "Cartero now commits guided changes",
            "Manual testing took too many steps",
        )
