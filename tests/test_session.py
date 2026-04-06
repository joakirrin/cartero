from __future__ import annotations

import io
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from cartero.cli import main


FIXED_IMPORT_TIME = datetime(
    2026,
    4,
    6,
    14,
    15,
    16,
    tzinfo=timezone(timedelta(hours=2)),
)
VALID_SESSION_BLOCK = """<<<CARTERO_SESSION_V1>>>
decisions: Kept session import local and debuggable.
tradeoffs: Strict parsing is less flexible but easier to inspect.
risks_open_issues: Commit flow still ignores structured session fields in this phase.
<<<END_CARTERO_SESSION_V1>>>"""
INVALID_SESSION_BLOCK = """<<<CARTERO_SESSION_V1>>>
decisions: Kept session import local and debuggable.
risks_open_issues: Commit flow still ignores structured session fields in this phase.
<<<END_CARTERO_SESSION_V1>>>"""


class SessionCommandTests(unittest.TestCase):
    def test_session_command_shows_missing_status_without_notes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            exit_code, stdout, stderr = self._run_in_temp_dir(temp_dir, ["session"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr, "")
        self.assertIn("No session notes found at .cartero/session-notes.md.", stdout)
        self.assertIn("- decisions: missing", stdout)
        self.assertIn("- tradeoffs: missing", stdout)
        self.assertIn("- risks_open_issues: missing", stdout)

    def test_session_command_shows_current_notes_and_field_status(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            notes_path = Path(temp_dir) / ".cartero" / "session-notes.md"
            notes_path.parent.mkdir(parents=True, exist_ok=True)
            notes_path.write_text(
                "\n".join(
                    [
                        "[LLM] 2026-04-06T12:00:00+02:00",
                        "decisions: Keep the session parser strict.",
                        "tradeoffs: none identified this session",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            exit_code, stdout, stderr = self._run_in_temp_dir(temp_dir, ["session"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr, "")
        self.assertIn("Session notes: .cartero/session-notes.md", stdout)
        self.assertIn("decisions: Keep the session parser strict.", stdout)
        self.assertIn("- decisions: present", stdout)
        self.assertIn("- tradeoffs: present", stdout)
        self.assertIn("- risks_open_issues: missing", stdout)

    def test_session_command_does_not_run_master_context_freshness_check(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch(
                "cartero.cli.get_master_refresh_guard",
                side_effect=AssertionError("session should not read freshness state"),
            ):
                exit_code, stdout, stderr = self._run_in_temp_dir(temp_dir, ["session"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr, "")
        self.assertIn("Required field status:", stdout)

    def test_session_import_success_path_appends_normalized_note(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            exit_code, stdout, stderr = self._run_import(temp_dir, VALID_SESSION_BLOCK)
            notes_path = Path(temp_dir) / ".cartero" / "session-notes.md"

            self.assertEqual(exit_code, 0)
            self.assertEqual(stderr, "")
            self.assertIn("Imported session summary into .cartero/session-notes.md.", stdout)
            self.assertEqual(
                notes_path.read_text(encoding="utf-8"),
                "\n".join(
                    [
                        "[LLM] 2026-04-06T14:15:16+02:00",
                        "decisions: Kept session import local and debuggable.",
                        "tradeoffs: Strict parsing is less flexible but easier to inspect.",
                        "risks_open_issues: Commit flow still ignores structured session fields in this phase.",
                        "",
                    ]
                ),
            )

    def test_session_import_persists_raw_backup_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            exit_code, _, stderr = self._run_import(temp_dir, VALID_SESSION_BLOCK)
            raw_latest = Path(temp_dir) / ".cartero" / "session-summary" / "raw-latest.md"
            raw_archive = (
                Path(temp_dir)
                / ".cartero"
                / "archive"
                / "session-summary-2026-04-06-141516-raw.md"
            )

            self.assertEqual(exit_code, 0)
            self.assertEqual(stderr, "")
            self.assertEqual(raw_latest.read_text(encoding="utf-8"), VALID_SESSION_BLOCK)
            self.assertEqual(raw_archive.read_text(encoding="utf-8"), VALID_SESSION_BLOCK)

    def test_session_import_persists_normalized_backup_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            exit_code, _, stderr = self._run_import(temp_dir, VALID_SESSION_BLOCK)
            normalized_latest = (
                Path(temp_dir) / ".cartero" / "session-summary" / "normalized-latest.md"
            )
            normalized_archive = (
                Path(temp_dir)
                / ".cartero"
                / "archive"
                / "session-summary-2026-04-06-141516-normalized.md"
            )

            self.assertEqual(exit_code, 0)
            self.assertEqual(stderr, "")
            expected_normalized = "\n".join(
                [
                    "decisions: Kept session import local and debuggable.",
                    "tradeoffs: Strict parsing is less flexible but easier to inspect.",
                    "risks_open_issues: Commit flow still ignores structured session fields in this phase.",
                    "",
                ]
            )
            self.assertEqual(
                normalized_latest.read_text(encoding="utf-8"),
                expected_normalized,
            )
            self.assertEqual(
                normalized_archive.read_text(encoding="utf-8"),
                expected_normalized,
            )

    def test_session_import_parse_failure_preserves_raw_only(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            exit_code, stdout, stderr = self._run_import(temp_dir, INVALID_SESSION_BLOCK)
            raw_latest = Path(temp_dir) / ".cartero" / "session-summary" / "raw-latest.md"
            raw_archive = (
                Path(temp_dir)
                / ".cartero"
                / "archive"
                / "session-summary-2026-04-06-141516-raw.md"
            )
            normalized_latest = (
                Path(temp_dir) / ".cartero" / "session-summary" / "normalized-latest.md"
            )
            normalized_archive = (
                Path(temp_dir)
                / ".cartero"
                / "archive"
                / "session-summary-2026-04-06-141516-normalized.md"
            )
            notes_path = Path(temp_dir) / ".cartero" / "session-notes.md"

            self.assertEqual(exit_code, 2)
            self.assertEqual(stdout, "")
            self.assertIn("Missing required session summary field(s): tradeoffs.", stderr)
            self.assertIn(
                "Raw latest preserved at .cartero/session-summary/raw-latest.md.",
                stderr,
            )
            self.assertIn(
                ".cartero/archive/session-summary-2026-04-06-141516-raw.md.",
                stderr,
            )
            self.assertEqual(raw_latest.read_text(encoding="utf-8"), INVALID_SESSION_BLOCK)
            self.assertEqual(raw_archive.read_text(encoding="utf-8"), INVALID_SESSION_BLOCK)
            self.assertFalse(normalized_latest.exists())
            self.assertFalse(normalized_archive.exists())
            self.assertFalse(notes_path.exists())

    def _run_import(self, temp_dir: str, raw_block: str) -> tuple[int, str, str]:
        stdin = io.StringIO(raw_block)
        with patch("cartero.session_summary.get_current_time", return_value=FIXED_IMPORT_TIME):
            return self._run_in_temp_dir(
                temp_dir,
                ["session", "--import"],
                stdin=stdin,
            )

    def _run_in_temp_dir(
        self,
        temp_dir: str,
        argv: list[str],
        *,
        stdin: io.StringIO | None = None,
    ) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        original_cwd = os.getcwd()
        os.chdir(temp_dir)
        try:
            patches = [redirect_stdout(stdout), redirect_stderr(stderr)]
            if stdin is not None:
                patches.append(patch("sys.stdin", stdin))

            with patches[0], patches[1]:
                if stdin is None:
                    exit_code = main(argv)
                else:
                    with patches[2]:
                        exit_code = main(argv)
        finally:
            os.chdir(original_cwd)

        return exit_code, stdout.getvalue(), stderr.getvalue()
