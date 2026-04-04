from __future__ import annotations

import io
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import MagicMock, patch

from cartero.canonical import parse_canonical_record
from cartero.cli import main
from cartero.context_state import MasterRefreshGuard
from cartero.generator import SummaryGenerationResult
from cartero.git import GitError, commit, get_changed_files, get_diff, stage_files
from cartero.llm import LLMCallError


_CANONICAL_TEXT = """<<<CARTERO_RECORD_V1>>>
<<<SUMMARY>>>
Cartero now explains generated changes in plain language.
<<<END_SUMMARY>>>
<<<CHANGELOG>>>
Cartero now returns a reusable canonical communication record before rendering legacy YAML.
<<<END_CHANGELOG>>>
<<<FAQ>>>
NONE
<<<END_FAQ>>>
<<<KNOWLEDGE_BASE>>>
NONE
<<<END_KNOWLEDGE_BASE>>>
<<<END_CARTERO_RECORD_V1>>>"""


def _summary_result(
    yaml_text: str,
    warning_message: str | None = None,
    *,
    commit_fields: dict[str, object] | None = None,
    quality_metadata: dict[str, object] | None = None,
) -> SummaryGenerationResult:
    return SummaryGenerationResult(
        record=parse_canonical_record(_CANONICAL_TEXT),
        canonical_text=_CANONICAL_TEXT,
        yaml_text=yaml_text,
        warning_message=warning_message,
        commit_fields=commit_fields,
        quality_metadata=quality_metadata,
    )


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

    def test_get_diff_prefers_staged_changes(self) -> None:
        with patch("cartero.git.subprocess.run") as mock_run:
            mock_run.side_effect = [
                self._completed_process(stdout="staged.py\n"),
                self._completed_process(stdout="diff --git a/staged.py b/staged.py\n"),
            ]

            diff_text = get_diff()

        self.assertEqual(diff_text, "diff --git a/staged.py b/staged.py\n")
        self.assertEqual(
            mock_run.call_args_list[0].args[0],
            ["git", "diff", "--cached", "--name-only"],
        )
        self.assertEqual(
            mock_run.call_args_list[1].args[0],
            ["git", "diff", "--cached"],
        )

    def test_get_diff_falls_back_to_working_tree_when_nothing_is_staged(self) -> None:
        with patch("cartero.git.subprocess.run") as mock_run:
            mock_run.side_effect = [
                self._completed_process(stdout=""),
                self._completed_process(stdout="diff --git a/file.py b/file.py\n"),
            ]

            diff_text = get_diff()

        self.assertEqual(diff_text, "diff --git a/file.py b/file.py\n")
        self.assertEqual(
            mock_run.call_args_list[0].args[0],
            ["git", "diff", "--cached", "--name-only"],
        )
        self.assertEqual(
            mock_run.call_args_list[1].args[0],
            ["git", "diff"],
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

    def _completed_process(self, *, stdout: str, returncode: int = 0, stderr: str = ""):
        result = MagicMock()
        result.returncode = returncode
        result.stdout = stdout
        result.stderr = stderr
        return result


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
            return_value=_summary_result(
                "summary: add commit command\n"
                "reason: needed for git flow\n"
                "actions: []\n"
            ),
        ), patch("cartero.cli.git_commit", return_value="abc1234") as mock_git_commit:
            exit_code, stdout, stderr = self._run_commit(["a", "y"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr, "")
        self.assertIn("abc1234", stdout)
        mock_stage_files.assert_called_once_with(["cartero/cli.py"])
        mock_git_commit.assert_called_once_with("add commit command", "needed for git flow")

    def test_commit_prefers_structured_fields_when_yaml_is_invalid(self) -> None:
        with patch("cartero.cli.get_changed_files", return_value=["cartero/cli.py"]), patch(
            "cartero.cli.stage_files"
        ) as mock_stage_files, patch(
            "cartero.cli.get_diff", return_value="diff --git a/cartero/cli.py ..."
        ), patch(
            "cartero.cli.generate_summary_result_from_diff",
            return_value=_summary_result(
                "summary: [\n",
                commit_fields={
                    "summary": "Cartero now commits guided changes",
                    "reason": "Manual testing took too many steps",
                    "impact": "Developers can review changes faster",
                    "actions": [],
                },
            ),
        ), patch("cartero.cli.git_commit", return_value="abc1234") as mock_git_commit:
            exit_code, stdout, stderr = self._run_commit(["a", "y"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr, "")
        self.assertIn("abc1234", stdout)
        mock_stage_files.assert_called_once_with(["cartero/cli.py"])
        mock_git_commit.assert_called_once_with(
            "Cartero now commits guided changes",
            "Manual testing took too many steps",
        )

    def test_commit_falls_back_to_yaml_when_structured_fields_are_invalid(self) -> None:
        with patch("cartero.cli.get_changed_files", return_value=["cartero/cli.py"]), patch(
            "cartero.cli.stage_files"
        ) as mock_stage_files, patch(
            "cartero.cli.get_diff", return_value="diff --git a/cartero/cli.py ..."
        ), patch(
            "cartero.cli.generate_summary_result_from_diff",
            return_value=_summary_result(
                "summary: add commit command\n"
                "reason: needed for git flow\n"
                "actions: []\n",
                commit_fields={"summary": "broken structured data"},
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
            return_value=_summary_result(
                "summary: add commit command\n"
                "reason: needed for git flow\n"
                "actions: []\n"
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

    def test_commit_passes_optional_context(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            context_path = Path(temp_dir) / "context.txt"
            context_path.write_text("messy notes", encoding="utf-8")

            with patch("cartero.cli.get_changed_files", return_value=["cartero/cli.py"]), patch(
                "cartero.cli.stage_files"
            ) as mock_stage_files, patch(
                "cartero.cli.get_diff", return_value="diff --git a/cartero/cli.py ..."
            ), patch(
                "cartero.cli.generate_summary_result_from_diff",
                return_value=_summary_result(
                    "summary: add commit command\n"
                    "reason: needed for git flow\n"
                    "actions: []\n"
                ),
            ) as mock_generate, patch(
                "cartero.cli.git_commit", return_value="abc1234"
            ):
                exit_code, stdout, stderr = self._run_commit(
                    ["a", "y"],
                    argv=["--context-file", str(context_path)],
                )

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr, "")
        self.assertIn("abc1234", stdout)
        mock_stage_files.assert_called_once_with(["cartero/cli.py"])
        mock_generate.assert_called_once_with(
            "diff --git a/cartero/cli.py ...",
            raw_context="messy notes",
        )

    def test_commit_warns_and_aborts_when_master_context_is_stale(self) -> None:
        stale_guard = self._make_guard(
            status="pending",
            current="2026-04-04T08:00:00+00:00",
        )

        with patch("cartero.cli.get_changed_files", return_value=["cartero/cli.py"]), patch(
            "cartero.cli.stage_files"
        ) as mock_stage_files:
            exit_code, stdout, stderr = self._run_commit(["n"], guard=stale_guard)

        self.assertEqual(exit_code, 0)
        self.assertIn("Continue with stale master context?", stdout)
        self.assertIn("Aborted.", stdout)
        self.assertIn("warning:", stderr)
        self.assertIn("summary can be outdated", stderr)
        mock_stage_files.assert_not_called()

    def test_commit_allows_explicit_continue_when_master_context_is_stale(self) -> None:
        stale_guard = self._make_guard(
            status="pending",
            current="2026-04-04T08:00:00+00:00",
        )

        with patch("cartero.cli.get_changed_files", return_value=["cartero/cli.py"]), patch(
            "cartero.cli.stage_files"
        ) as mock_stage_files, patch(
            "cartero.cli.get_diff", return_value="diff --git a/cartero/cli.py ..."
        ), patch(
            "cartero.cli.generate_summary_result_from_diff",
            return_value=_summary_result(
                "summary: add commit command\n"
                "reason: needed for git flow\n"
                "actions: []\n"
            ),
        ), patch(
            "cartero.cli.git_commit", return_value="abc1234"
        ) as mock_git_commit:
            exit_code, stdout, stderr = self._run_commit(
                ["y", "a", "y"],
                guard=stale_guard,
            )

        self.assertEqual(exit_code, 0)
        self.assertIn("Continue with stale master context?", stdout)
        self.assertIn("abc1234", stdout)
        self.assertIn("warning:", stderr)
        mock_stage_files.assert_called_once_with(["cartero/cli.py"])
        mock_git_commit.assert_called_once_with("add commit command", "needed for git flow")

    def _run_commit(
        self,
        input_lines: list[str],
        argv: list[str] | None = None,
        guard: MasterRefreshGuard | None = None,
    ) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        stdin = io.StringIO("\n".join(input_lines) + "\n")

        active_guard = guard or self._make_guard(status="done")

        with patch("cartero.cli.get_master_refresh_guard", return_value=active_guard), patch(
            "sys.stdin", stdin
        ), redirect_stdout(stdout), redirect_stderr(stderr):
            exit_code = main(["commit", *(argv or [])])

        return exit_code, stdout.getvalue(), stderr.getvalue()

    def _make_guard(
        self,
        *,
        status: str,
        at_start: str = "2026-04-04T08:00:00+00:00",
        current: str = "2026-04-04T09:00:00+00:00",
        after_refresh: str | None = None,
    ) -> MasterRefreshGuard:
        return MasterRefreshGuard(
            current_master_timestamp=current,
            master_timestamp_at_start=at_start,
            master_timestamp_after_refresh=after_refresh,
            master_refresh_status=status,
            system_state_exists=True,
            system_state_initialized=False,
        )
