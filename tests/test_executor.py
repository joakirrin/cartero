from __future__ import annotations

import io
import unittest

from rich.console import Console

from cartero.executor import execute_actions
from cartero.validator import Change


class ExecutorTests(unittest.TestCase):
    def test_execute_actions_returns_simulated_results(self) -> None:
        buffer = io.StringIO()
        console = Console(file=buffer, force_terminal=False, color_system=None)
        results = execute_actions(
            [
                Change(
                    repo="cartero",
                    change_type="write",
                    path="docs/plan.md",
                    content="updated plan",
                ),
                Change(
                    repo="casadora-services",
                    change_type="delete",
                    path="docker/legacy-compose.yaml",
                ),
            ],
            console=console,
        )

        self.assertEqual(results[0].status, "simulated")
        self.assertEqual(results[1].status, "simulated")
        self.assertEqual(results[0].change_type, "write")
        self.assertEqual(results[1].change_type, "delete")

    def test_execute_actions_prints_executing_lines(self) -> None:
        buffer = io.StringIO()
        console = Console(file=buffer, force_terminal=False, color_system=None)

        execute_actions(
            [
                Change(
                    repo="cartero",
                    change_type="write",
                    path="docs/plan.md",
                    content="updated plan",
                ),
                Change(
                    repo="casadora-services",
                    change_type="delete",
                    path="docker/legacy-compose.yaml",
                ),
            ],
            console=console,
        )

        output = buffer.getvalue()
        self.assertEqual(output.count("[executing]"), 2)
        self.assertIn("write -> docs/plan.md", output)
        self.assertIn("delete -> docker/legacy-compose.yaml", output)
        self.assertIn("Execution is simulated", output)
