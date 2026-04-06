from __future__ import annotations

import io
import unittest
from contextlib import redirect_stderr, redirect_stdout

from cartero.cli import main


class SessionHelpTests(unittest.TestCase):
    def test_session_help_mentions_strict_v1_import_contract(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()

        with self.assertRaises(SystemExit) as context:
            with redirect_stdout(stdout), redirect_stderr(stderr):
                main(["session", "--help"])

        self.assertEqual(context.exception.code, 0)
        self.assertEqual(stderr.getvalue(), "")
        help_text = stdout.getvalue()
        self.assertIn("Paste a strict CARTERO_SESSION_V1 block", help_text)
        self.assertIn("decisions, tradeoffs,", help_text)
        self.assertIn("risks_open_issues", help_text)
