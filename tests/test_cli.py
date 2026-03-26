from __future__ import annotations

import io
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from cartero.cli import main
from cartero.executor import execute_actions as real_execute_actions


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

    def _run_main(self, argv: list[str]) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()

        with redirect_stdout(stdout), redirect_stderr(stderr):
            exit_code = main(argv)

        return exit_code, stdout.getvalue(), stderr.getvalue()
