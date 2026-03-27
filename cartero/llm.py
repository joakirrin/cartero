from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass

import yaml

try:
    from anthropic import Anthropic
except ImportError:
    Anthropic = None

from cartero.config import CarteroConfig, default_config


logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a commit summary generator for the Cartero tool.

Given a git diff or description of changes, return ONLY a valid JSON object
with this exact shape:

{
  "summary": "<one sentence: what was done>",
  "reason": "<one sentence: why it was done>",
  "impact": "<one sentence: what changes for the user or system>",
  "actions": [
    {
      "repo": "<repo-name>",
      "type": "<write|delete|mkdir>",
      "path": "<relative/path>",
      "content": "<required for write, omit for delete and mkdir>"
    }
  ]
}

Rules:
- repo must be one of: casadora-core, casadora-services,
  casadora-experiments, cartero
- type must be one of: write, delete, mkdir
- path must be a non-empty relative path using forward slashes
- content is required for type: write
- content must NOT be present for type: delete or mkdir
- Return ONLY valid JSON
- Do not include markdown fences
- Do not include explanations, preamble, or trailing text
"""

STRICT_RETRY_SUFFIX = """
IMPORTANT: Your previous response could not be parsed.
Return ONLY a raw JSON object. No markdown, no explanation, no extra text.
The very first character of your response must be '{' and the last must be '}'.
"""


class LLMConfigError(Exception):
    pass


class LLMCallError(Exception):
    pass


@dataclass(frozen=True)
class LLMGenerationResult:
    yaml_text: str
    was_chunked: bool


class CarteroDumper(yaml.SafeDumper):
    pass


def _str_presenter(dumper: yaml.Dumper, data: str):
    if "\n" in data:
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")
    if len(data) > 88:
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style=">")
    return dumper.represent_scalar("tag:yaml.org,2002:str", data)


CarteroDumper.add_representer(str, _str_presenter)


def _truncate_diff(diff_text: str, max_chars: int) -> tuple[str, bool]:
    if len(diff_text) <= max_chars:
        return diff_text, False
    truncated = diff_text[:max_chars]
    last_newline = truncated.rfind("\n")
    if last_newline > 0:
        truncated = truncated[:last_newline]
    return truncated, True


def _split_diff_into_chunks(diff_text: str, max_chars: int) -> list[str]:
    lines = diff_text.splitlines(keepends=True)
    section_start_indexes = [
        index for index, line in enumerate(lines) if line.startswith("diff --git")
    ]

    if not section_start_indexes:
        return [diff_text]

    sections: list[str] = []
    prefix = "".join(lines[: section_start_indexes[0]])

    for index, start in enumerate(section_start_indexes):
        end = (
            section_start_indexes[index + 1]
            if index + 1 < len(section_start_indexes)
            else len(lines)
        )
        section = "".join(lines[start:end])
        if index == 0 and prefix:
            section = prefix + section
        sections.append(section)

    chunks: list[str] = []
    current_chunk = ""

    for section in sections:
        if not current_chunk:
            current_chunk = section
            continue
        if len(current_chunk) + len(section) <= max_chars:
            current_chunk += section
            continue
        chunks.append(current_chunk)
        current_chunk = section

    if current_chunk:
        chunks.append(current_chunk)

    return chunks


def _merge_results(results: list[dict]) -> dict:
    if not results:
        return {}

    merged = {
        "summary": results[0].get("summary"),
        "reason": results[0].get("reason"),
        "impact": results[0].get("impact"),
        "actions": [],
    }

    for result in results:
        actions = result.get("actions")
        if isinstance(actions, list):
            merged["actions"].extend(actions)

    return merged


def _generate_from_chunks(
    client,
    chunks: list[str],
    config: CarteroConfig,
) -> str:
    parsed_results: list[dict] = []

    for chunk_index, chunk in enumerate(chunks, start=1):
        last_error: Exception | None = None

        for attempt in range(1, max(1, config.max_retries) + 1):
            try:
                raw_output = _call_llm(client, chunk, config, strict=attempt > 1)
                logger.debug(
                    "Raw LLM output for chunk %d (attempt %d):\n%s",
                    chunk_index,
                    attempt,
                    raw_output,
                )
                parsed_output = json.loads(_strip_fences(raw_output))
                if not isinstance(parsed_output, dict):
                    raise LLMCallError("Model returned JSON, but it was not an object")
                parsed_results.append(parsed_output)
                break
            except json.JSONDecodeError as exc:
                last_error = LLMCallError(
                    f"Model returned invalid JSON: {exc}\nRaw output:\n{raw_output}"
                )
                logger.warning(
                    "LLM chunk %d attempt %d failed: %s",
                    chunk_index,
                    attempt,
                    last_error,
                )
            except LLMCallError as exc:
                last_error = exc
                logger.warning(
                    "LLM chunk %d attempt %d failed: %s",
                    chunk_index,
                    attempt,
                    exc,
                )
            except Exception as exc:
                raise LLMCallError(str(exc)) from exc
        else:
            raise LLMCallError(
                f"Failed for chunk {chunk_index} after "
                f"{max(1, config.max_retries)} attempts. Last error: {last_error}"
            )

    merged = _merge_results(parsed_results)
    yaml_output = yaml.dump(
        merged,
        Dumper=CarteroDumper,
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
        width=88,
    )
    try:
        yaml.safe_load(yaml_output)
    except yaml.YAMLError as exc:
        raise LLMCallError(f"Generated YAML could not be parsed: {exc}") from exc
    return yaml_output


def _strip_fences(output: str) -> str:
    if not output.startswith("```"):
        return output
    lines = output.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _parse_and_convert(output: str) -> str:
    output = _strip_fences(output)
    if not output:
        raise LLMCallError("Model returned empty output")
    try:
        data = json.loads(output)
    except json.JSONDecodeError as exc:
        raise LLMCallError(
            f"Model returned invalid JSON: {exc}\nRaw output:\n{output}"
        ) from exc
    if not isinstance(data, dict):
        raise LLMCallError("Model returned JSON, but it was not an object")
    yaml_output = yaml.dump(
        data,
        Dumper=CarteroDumper,
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
        width=88,
    )
    try:
        yaml.safe_load(yaml_output)
    except yaml.YAMLError as exc:
        raise LLMCallError(f"Generated YAML could not be parsed: {exc}") from exc
    return yaml_output


def _call_llm(
    client, diff_text: str, config: CarteroConfig, *, strict: bool = False
) -> str:
    system = SYSTEM_PROMPT + (STRICT_RETRY_SUFFIX if strict else "")
    message = client.messages.create(
        model=config.model,
        max_tokens=config.max_tokens,
        system=system,
        messages=[{"role": "user", "content": diff_text}],
    )
    return "".join(
        block.text for block in message.content if getattr(block, "type", None) == "text"
    ).strip()


def generate_commit_summary_result(
    diff_text: str, config: CarteroConfig | None = None
) -> LLMGenerationResult:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise LLMConfigError("ANTHROPIC_API_KEY environment variable is not set")
    active_config = config or default_config
    if active_config.llm_provider != "anthropic":
        raise LLMConfigError(f"Unsupported llm_provider: {active_config.llm_provider}")
    chunks = _split_diff_into_chunks(diff_text, active_config.max_diff_chars)
    was_chunked = len(chunks) > 1

    if was_chunked:
        logger.warning(
            "Diff was split into %d chunks (max_diff_tokens=%d). "
            "Processing each chunk separately.",
            len(chunks),
            active_config.max_diff_tokens,
        )
    if Anthropic is None:
        raise LLMCallError("anthropic package is not installed")
    client = Anthropic(api_key=api_key)
    if was_chunked:
        yaml_text = _generate_from_chunks(client, chunks, active_config)
        return LLMGenerationResult(yaml_text, was_chunked=True)
    last_error: LLMCallError | None = None
    for attempt in range(1, max(1, active_config.max_retries) + 1):
        try:
            raw_output = _call_llm(client, diff_text, active_config, strict=attempt > 1)
            logger.debug("Raw LLM output (attempt %d):\n%s", attempt, raw_output)
            return LLMGenerationResult(_parse_and_convert(raw_output), was_chunked)
        except LLMCallError as exc:
            last_error = exc
            logger.warning("LLM attempt %d failed: %s", attempt, exc)
        except Exception as exc:
            raise LLMCallError(str(exc)) from exc
    raise LLMCallError(
        f"Failed after {max(1, active_config.max_retries)} attempts. Last error: {last_error}"
    )


def generate_commit_summary(
    diff_text: str, config: CarteroConfig | None = None
) -> str:
    return generate_commit_summary_result(diff_text, config).yaml_text
