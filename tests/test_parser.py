from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from cartero.parser import ParseError, load_summary


class LoadSummaryTests(unittest.TestCase):
    def test_load_summary_returns_mapping(self) -> None:
        fixture = Path("tests/fixtures/sample_summary.yaml")

        loaded = load_summary(fixture)

        self.assertEqual(len(loaded["actions"]), 3)

    def test_duplicate_yaml_keys_raise_parse_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            summary_path = Path(temp_dir) / "duplicate.yaml"
            summary_path.write_text("actions: []\nactions: []\n", encoding="utf-8")

            with self.assertRaises(ParseError):
                load_summary(summary_path)
