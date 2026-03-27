from __future__ import annotations

import io
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch

from cartero.cli import main
from cartero.generator import SummaryGenerationResult
from cartero.git import GitError, commit, get_changed_files, stage_files
from cartero.llm import LLMCallError


class GitModuleTests(unittest.TestCase):
    def test_get_changed_files_parses_status_output(self) -> None:
        with patch("cartero.git.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = " M cartero/cli.py\n?? newfile.py\nA  staged.py\n"
            mock_run.return_value.stderr = ""

            changed_files = get_changed_files()

        self.assertEqual(
            changed_files,
            ["cartero/cli.py", "newfile.py", "staged.py"],
        )

    def test_get_changed_files_returns_empty_on_clean(self) -> None:
        with patch("cartero.git.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = ""
            mock_run.return_value.stderr = ""

            changed_files = get_changed_files()

        self.assertEqual(changed_files, [])

    def test_get_changed_files_raises_on_error(self) -> None:
        with patch("cartero.git.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 128
            mock_run.return_value.stdout = ""
            mock_run.return_value.stderr = "not a git repository"

            with self.assertRaises(GitError) as context:
                get_changed_files()

        self.assertIn("not a git repository", str(context.exception))

    def test_stage_files_calls_git_add(self) -> None:
        with patch("cartero.git.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = ""
            mock_run.return_value.stderr = ""

            stage_files(["file1.py", "file2.py"])

        mock_run.assert_called_once_with(
            ["git", "add", "--", "file1.py", "file2.py"],
            capture_output=True,
            text=True,
            check=False,
        )

    def test_commit_returns_short_hash(self) -> None:
        with patch("cartero.git.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = "[main abc1234] feat: add thing\n 1 file changed\n"
            mock_run.return_value.stderr = ""

            commit_hash = commit("feat: add thing")

        self.assertEqual(commit_hash, "abc1234")

    def test_commit_with_body_passes_two_m_flags(self) -> None:
        with patch("cartero.git.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = "[main abc1234] subject\n 1 file changed\n"
            mock_run.return_value.stderr = ""

            commit("subject", "body text")

        mock_run.assert_called_once_with(
            ["git", "commit", "-m", "subject", "-m", "body text"],
            capture_output=True,
            text=True,
            check=False,
        )


class CommitCommandTests(unittest.TestCase):
    def test_commit_aborts_when_no_changed_files(self) -> None:
        with patch("cartero.cli.get_changed_files", return_value=[]):
            exit_code, stdout, stderr = self._run_commit([])

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr, "")
        self.assertIn("Nothing to commit", stdout)

    def test_commit_aborts_on_invalid_selection(self) -> None:
        with patch("cartero.cli.get_changed_files", return_value=["file.py"]):
            exit_code, stdout, stderr = self._run_commit([""])

        self.assertEqual(exit_code, 2)
        self.assertEqual(
            stdout,
            'Changed files:\n1. file.py\nStage files (numbers separated by spaces, or "a" for all): ',
        )
        self.assertIn("error:", stderr)

    def test_commit_full_happy_path(self) -> None:
        with patch("cartero.cli.get_changed_files", return_value=["cartero/cli.py"]), patch(
            "cartero.cli.stage_files"
        ) as mock_stage_files, patch(
            "cartero.cli.get_diff", return_value="diff --git a/cartero/cli.py ..."
        ), patch(
            "cartero.cli.generate_summary_result_from_diff",
            return_value=SummaryGenerationResult(
                yaml_text=(
                    "summary: add commit command\n"
                    "reason: needed for git flow\n"
                    "actions: []\n"
                ),
                warning_message=None,
            ),
        ), patch("cartero.cli.git_commit", return_value="abc1234") as mock_git_commit:
            exit_code, stdout, stderr = self._run_commit(["a", "y"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr, "")
        self.assertIn("abc1234", stdout)
        mock_stage_files.assert_called_once_with(["cartero/cli.py"])
        mock_git_commit.assert_called_once_with("add commit command", "needed for git flow")

    def test_commit_aborts_on_user_rejection(self) -> None:
        with patch("cartero.cli.get_changed_files", return_value=["cartero/cli.py"]), patch(
            "cartero.cli.stage_files"
        ) as mock_stage_files, patch(
            "cartero.cli.get_diff", return_value="diff --git a/cartero/cli.py ..."
        ), patch(
            "cartero.cli.generate_summary_result_from_diff",
            return_value=SummaryGenerationResult(
                yaml_text=(
                    "summary: add commit command\n"
                    "reason: needed for git flow\n"
                    "actions: []\n"
                ),
                warning_message=None,
            ),
        ), patch("cartero.cli.git_commit") as mock_git_commit:
            exit_code, stdout, stderr = self._run_commit(["a", "n"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr, "")
        self.assertIn("Aborted", stdout)
        mock_stage_files.assert_called_once_with(["cartero/cli.py"])
        mock_git_commit.assert_not_called()

    def test_commit_surfaces_llm_error(self) -> None:
        with patch("cartero.cli.get_changed_files", return_value=["file.py"]), patch(
            "cartero.cli.stage_files"
        ), patch("cartero.cli.get_diff", return_value="diff --git a/file.py b/file.py"), patch(
            "cartero.cli.generate_summary_result_from_diff",
            side_effect=LLMCallError("timeout"),
        ):
            exit_code, stdout, stderr = self._run_commit(["a"])

        self.assertEqual(exit_code, 2)
        self.assertIn("error:", stderr)
        self.assertIn("Changed files:", stdout)

    def _run_commit(self, input_lines: list[str]) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        stdin = io.StringIO("\n".join(input_lines) + "\n")

        with patch("sys.stdin", stdin), redirect_stdout(stdout), redirect_stderr(stderr):
            exit_code = main(["commit"])

        return exit_code, stdout.getvalue(), stderr.getvalue()
