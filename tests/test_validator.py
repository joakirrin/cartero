from __future__ import annotations

import unittest

from cartero.validator import ValidationError, validate_summary


class ValidateSummaryTests(unittest.TestCase):
    def test_validate_summary_returns_typed_summary(self) -> None:
        summary = validate_summary(
            {
                "actions": [
                    {
                        "repo": "casadora-core",
                        "type": "write",
                        "path": "docs/recovery.md",
                        "content": "updated plan",
                    }
                ],
            }
        )

        self.assertEqual(summary.actions[0].repo, "casadora-core")
        self.assertEqual(summary.actions[0].change_type, "write")

    def test_unknown_repo_fails_validation(self) -> None:
        with self.assertRaisesRegex(ValidationError, "must be one of"):
            validate_summary(
                {
                    "actions": [
                        {
                            "repo": "unknown-repo",
                            "type": "delete",
                            "path": "docs/a.md",
                        }
                    ],
                }
            )

    def test_write_requires_content(self) -> None:
        with self.assertRaisesRegex(ValidationError, "content must be a non-empty string"):
            validate_summary(
                {
                    "actions": [
                        {
                            "repo": "cartero",
                            "type": "write",
                            "path": "cartero/cli.py",
                        }
                    ],
                }
            )

    def test_parent_directory_escape_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValidationError, "must not contain"):
            validate_summary(
                {
                    "actions": [
                        {
                            "repo": "casadora-services",
                            "type": "delete",
                            "path": "../secrets.txt",
                        }
                    ],
                }
            )
