from __future__ import annotations

import io
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from cartero.cli import main


class CliTests(unittest.TestCase):
    def test_cli_prints_grouped_dry_run_plan(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()

        with redirect_stdout(stdout), redirect_stderr(stderr):
            exit_code = main(["tests/fixtures/sample_summary.yaml"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr.getvalue(), "")
        output = stdout.getvalue()
        self.assertIn("Cartero dry-run plan", output)
        self.assertIn("Validated actions: 3", output)
        self.assertIn("casadora-core (1 action)", output)
        self.assertIn("simulate write file: docs/architecture/network.md", output)
        self.assertIn("content preview:", output)
        self.assertIn("# Network", output)
        self.assertIn("casadora-services (1 action)", output)
        self.assertIn("simulate delete file: docker/legacy-compose.yaml", output)
        self.assertIn("cartero (1 action)", output)
        self.assertIn("simulate mkdir dir: tests/fixtures/generated", output)

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
