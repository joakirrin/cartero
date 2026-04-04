from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from cartero.canonical import parse_canonical_record
from cartero.generator import SummaryGenerationResult
from cartero.web import create_app


class WebTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = create_app()
        self.client = self.app.test_client()
        self.sample_yaml = Path("tests/fixtures/sample_summary.yaml").read_text(
            encoding="utf-8"
        )

    def test_index_renders_single_page_controls(self) -> None:
        response = self.client.get("/")
        page = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("Cartero Local UI", page)
        self.assertIn("How to use Cartero", page)
        self.assertIn("Paste your changes (YAML)", page)
        self.assertIn('Click "Dry-run" to preview safely', page)
        self.assertIn('Click "Apply (simulated)" to see execution', page)
        self.assertIn("No files are changed yet.", page)
        self.assertIn("Load sample", page)
        self.assertIn("Dry-run", page)
        self.assertIn("Apply (simulated)", page)
        self.assertIn("Download YAML", page)
        self.assertIn("Download output", page)
        self.assertIn("Copy output", page)
        self.assertIn("No output yet", page)
        self.assertIn('id="download-output" disabled', page)
        self.assertIn('id="copy-output" disabled', page)
        self.assertIn('const outputText = ""', page)

    def test_web_dry_run_renders_plan_output(self) -> None:
        response = self.client.post(
            "/",
            data={"yaml_text": self.sample_yaml, "action": "dry-run"},
        )
        page = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("Dry-run", page)
        self.assertIn("Cartero dry-run plan", page)
        self.assertIn("simulate write file: docs/architecture/network.md", page)
        self.assertIn("No file or git changes were made.", page)
        self.assertNotIn("Simulated execution", page)
        self.assertIn("Download output", page)
        self.assertIn("Copy output", page)
        self.assertIn("cartero-dry-run-output.txt", page)
        self.assertIn('const outputText = "', page)

    def test_web_apply_renders_execution_section(self) -> None:
        response = self.client.post(
            "/",
            data={"yaml_text": self.sample_yaml, "action": "apply"},
        )
        page = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn("Apply (simulated)", page)
        self.assertIn("Cartero apply plan", page)
        self.assertIn("Simulated execution", page)
        self.assertIn("[executing] write -&gt; docs/architecture/network.md", page)
        self.assertIn("[executing] delete -&gt; docker/legacy-compose.yaml", page)
        self.assertIn("Execution is simulated", page)
        self.assertIn("cartero-apply-output.txt", page)

    def test_web_shows_validation_errors(self) -> None:
        response = self.client.post(
            "/",
            data={
                "yaml_text": (
                    "actions:\n"
                    "  - repo: cartero\n"
                    "    type: write\n"
                    "    path: docs/plan.md\n"
                ),
                "action": "dry-run",
            },
        )
        page = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 400)
        self.assertIn("Error", page)
        self.assertIn("content", page)
        self.assertIn('id="download-output" disabled', page)

    def test_web_shows_parse_errors(self) -> None:
        response = self.client.post(
            "/",
            data={"yaml_text": "actions: [\n", "action": "dry-run"},
        )
        page = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 400)
        self.assertIn("Error", page)
        self.assertIn("Invalid YAML", page)

    def test_download_yaml_still_uses_yaml_input(self) -> None:
        response = self.client.post(
            "/",
            data={"yaml_text": self.sample_yaml, "action": "dry-run"},
        )
        page = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn('link.download = "commit-summary.yaml"', page)
        self.assertIn("const sampleYaml =", page)

    def test_generate_api_includes_additive_structured_fields(self) -> None:
        canonical_text = """<<<CARTERO_RECORD_V1>>>
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
        result = SummaryGenerationResult(
            record=parse_canonical_record(canonical_text),
            canonical_text=canonical_text,
            yaml_text=(
                "summary: Cartero now explains generated changes in plain language.\n"
                "reason: Manual review was taking too long.\n"
                "impact: Developers can now review changes faster.\n"
                "actions: []\n"
            ),
            warning_message="Diff was too large and was split into multiple chunks.",
            commit_fields={
                "summary": "Cartero now explains generated changes in plain language.",
                "reason": "Manual review was taking too long.",
                "impact": "Developers can now review changes faster.",
                "actions": [],
            },
            quality_metadata={
                "semantic_status": "warn",
                "semantic_warnings": [
                    {
                        "field": "impact",
                        "code": "generic_outcome_fallback",
                        "severity": "warn",
                        "message": "impact is truthful but still generic",
                    }
                ],
                "used_normalization": True,
                "normalization_rules": ["impact"],
                "retry_count": 1,
                "used_fallback_reason": False,
                "used_fallback_impact": True,
            },
        )

        with patch("cartero.web.generate_summary_result_from_diff", return_value=result):
            response = self.client.post(
                "/generate",
                data={"diff_text": "diff --git a/x b/x\n", "context_text": "notes"},
            )

        payload = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["yaml"], result.yaml_text)
        self.assertEqual(payload["warning"], result.warning_message)
        self.assertEqual(payload["canonical_text"], canonical_text)
        self.assertEqual(payload["commit_fields"], result.commit_fields)
        self.assertEqual(payload["quality"], result.quality_metadata)
