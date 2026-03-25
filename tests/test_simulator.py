from __future__ import annotations

import unittest

from cartero.simulator import simulate_actions
from cartero.validator import Change


class SimulatorTests(unittest.TestCase):
    def test_simulate_actions_builds_write_preview(self) -> None:
        simulated = simulate_actions(
            [
                Change(
                    repo="cartero",
                    change_type="write",
                    path="docs/plan.md",
                    content="line one\nline two",
                )
            ]
        )

        self.assertEqual(simulated[0].summary, "simulate write file: docs/plan.md (17 bytes)")
        self.assertEqual(simulated[0].details[0], "content preview:")
        self.assertEqual(simulated[0].details[1:], ("  line one", "  line two"))

    def test_simulate_actions_builds_non_write_operations(self) -> None:
        simulated = simulate_actions(
            [
                Change(
                    repo="casadora-services",
                    change_type="delete",
                    path="docker/legacy-compose.yaml",
                ),
                Change(
                    repo="casadora-services",
                    change_type="mkdir",
                    path="docker/generated",
                ),
            ]
        )

        self.assertEqual(simulated[0].summary, "simulate delete file: docker/legacy-compose.yaml")
        self.assertEqual(simulated[0].details, ())
        self.assertEqual(simulated[1].summary, "simulate mkdir dir: docker/generated")
