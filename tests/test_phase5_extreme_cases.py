from __future__ import annotations

import os
from pathlib import Path

import pytest
from cartero.generator import generate_summary_result_from_diff
from cartero.llm import LLMCallError


def _read_case(name: str) -> tuple[str, str]:
    base = Path("tests/fixtures/extreme_cases") / name
    diff_text = (base / "diff.txt").read_text(encoding="utf-8")
    context_text = (base / "context.txt").read_text(encoding="utf-8")
    return diff_text, context_text


def test_empty_diff_case_is_available() -> None:
    diff_text, context_text = _read_case("empty_diff")
    assert diff_text == ""
    assert "No explicit product-facing change confirmed" in context_text


def test_ambiguous_diff_case_is_available() -> None:
    diff_text, context_text = _read_case("ambiguous_diff")
    assert "prepare_prompt_input" in diff_text
    assert "No explicit confirmation" in context_text


def test_partial_rollout_case_is_available() -> None:
    diff_text, context_text = _read_case("partial_rollout")
    assert "scope_limits" in diff_text
    assert "only updated parser and changelog support" in context_text


def test_tests_only_case_is_available() -> None:
    diff_text, context_text = _read_case("tests_only")
    assert "tests/test_generator.py" in diff_text
    assert "no application or renderer change" in context_text


def test_many_changes_case_is_available() -> None:
    diff_text, context_text = _read_case("many_changes")
    assert "catero/parser.py" in diff_text or "cartero/parser.py" in diff_text
    assert "canonical record" in context_text


def test_generate_real_empty_diff_is_handled_conservatively() -> None:
    diff_text, context_text = _read_case("empty_diff")

    try:
        result = generate_summary_result_from_diff(
            diff_text,
            raw_context=context_text,
        )
    except ValueError:
        return

    assert result is not None
    assert isinstance(result.yaml_text, str)
    assert result.yaml_text.strip() != ""


@pytest.mark.integration
def test_generate_real_tests_only_diff_does_not_crash() -> None:
    if not os.getenv("ANTHROPIC_API_KEY"):
        pytest.skip("ANTHROPIC_API_KEY is not configured")

    diff_text, context_text = _read_case("tests_only")

    try:
        result = generate_summary_result_from_diff(
            diff_text,
            raw_context=context_text,
        )
    except ValueError:
        return
    except LLMCallError as exc:
        pytest.fail(f"LLM call failed unexpectedly: {exc}")

    assert result is not None
    assert isinstance(result.yaml_text, str)
    assert result.yaml_text.strip() != ""
