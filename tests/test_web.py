from __future__ import annotations

import unittest
from pathlib import Path

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
