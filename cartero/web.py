from __future__ import annotations

import io
from pathlib import Path
from typing import Any

import yaml
from flask import Flask, jsonify, render_template, request
from rich.console import Console

from cartero.cli import render_plan
from cartero.generator import generate_summary_result_from_diff
from cartero.llm import LLMCallError, LLMConfigError
from cartero.parser import ParseError, StrictLoader
from cartero.validator import ValidationError, validate_summary


SAMPLE_SUMMARY_YAML = """actions:
  - repo: casadora-core
    type: write
    path: docs/architecture/network.md
    content: |
      # Network
      - Updated switch inventory
  - repo: casadora-services
    type: delete
    path: docker/legacy-compose.yaml
  - repo: cartero
    type: mkdir
    path: tests/fixtures/generated
"""
WEB_SUMMARY_PATH = Path("web-input.yaml")
SUPPORTED_MODES = {"dry-run", "apply"}


def create_app() -> Flask:
    app = Flask(__name__)

    @app.get("/")
    def index() -> str:
        return _render_page(
            yaml_text="",
            sample_yaml=SAMPLE_SUMMARY_YAML,
        )

    @app.post("/")
    def run() -> tuple[str, int] | str:
        yaml_text = request.form.get("yaml_text", "")
        action = request.form.get("action", "dry-run")

        if action not in SUPPORTED_MODES:
            return (
                _render_page(
                    yaml_text=yaml_text,
                    error_message="Error: Unsupported action.",
                    sample_yaml=SAMPLE_SUMMARY_YAML,
                ),
                400,
            )

        try:
            raw_summary = _load_summary_text(yaml_text)
            summary = validate_summary(raw_summary)
            result_text = _render_output(mode=action, actions=summary.actions)
        except (ParseError, ValidationError) as exc:
            return (
                _render_page(
                    yaml_text=yaml_text,
                    error_message=f"Error: {exc}",
                    sample_yaml=SAMPLE_SUMMARY_YAML,
                ),
                400,
            )

        return _render_page(
            yaml_text=yaml_text,
            result_label=_describe_result_label(action),
            result_text=result_text,
            sample_yaml=SAMPLE_SUMMARY_YAML,
            output_filename=_build_output_filename(action),
        )

    @app.post("/generate")
    def generate() -> tuple[Any, int]:
        diff_text = request.form.get("diff_text", "")
        try:
            result = generate_summary_result_from_diff(diff_text)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        except (LLMConfigError, LLMCallError) as exc:
            return jsonify({"error": str(exc)}), 500
        payload = {"yaml": result.yaml_text}
        if result.warning_message:
            payload["warning"] = result.warning_message
        return jsonify(payload), 200

    return app


def main() -> None:
    app = create_app()
    app.run(host="127.0.0.1", port=8000, debug=False)


def _describe_result_label(mode: str) -> str:
    if mode == "apply":
        return "Apply (simulated)"
    return "Dry-run"


def _build_output_filename(mode: str) -> str:
    if mode == "apply":
        return "cartero-apply-output.txt"
    return "cartero-dry-run-output.txt"


def _load_summary_text(raw_text: str) -> dict[str, Any]:
    try:
        loaded = yaml.load(raw_text, Loader=StrictLoader)
    except yaml.YAMLError as exc:
        raise ParseError(f"Invalid YAML: {exc}") from exc

    if not isinstance(loaded, dict):
        raise ParseError("Summary root must be a YAML mapping.")

    return loaded


def _render_output(*, mode: str, actions: Any) -> str:
    buffer = io.StringIO()
    console = Console(file=buffer, force_terminal=False, color_system=None)
    render_plan(WEB_SUMMARY_PATH, actions, mode, console=console)
    return buffer.getvalue().strip()


def _render_page(
    *,
    yaml_text: str,
    sample_yaml: str,
    error_message: str | None = None,
    result_label: str | None = None,
    result_text: str | None = None,
    output_filename: str | None = None,
) -> str:
    return render_template(
        "index.html",
        yaml_text=yaml_text,
        sample_yaml=sample_yaml,
        error_message=error_message,
        result_label=result_label,
        result_text=result_text,
        output_filename=output_filename,
    )
