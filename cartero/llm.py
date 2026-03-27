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

try:
    import google.generativeai as genai
except ImportError:
    genai = None

from cartero.config import CarteroConfig, default_config


logger = logging.getLogger(__name__)

COMMIT_SUMMARY_SYSTEM_PROMPT = """You are a commit summary generator for the Cartero tool.

Given a git diff or description of changes, return ONLY a valid JSON object
with this exact shape:

{
  "summary": "<one sentence starting with 'Cartero': describe what the tool can now do or do better, in plain language that a non-developer can understand. Do not use git verbs like 'fix', 'refactor', 'chore', or technical jargon. Example: 'Cartero now handles large codebases without losing context'>",
  "reason": "<one sentence explaining why this was needed: what problem the user was experiencing before. Example: 'Large diffs were causing errors because the tool tried to process everything at once'>",
  "impact": "<one sentence describing what the user can now do that they could not before, or what now works reliably. Example: 'Diffs of any size are automatically split and processed in sections, so summaries are generated without errors'>",
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
- summary must describe the change from the user's perspective, not the
  developer's. Write it like a release note: what can Cartero do now?
- reason must explain the user-facing problem that existed before,
  not the technical cause.
- impact must describe a concrete, observable outcome. Avoid vague
  phrases like "improves performance" or "enhances reliability".
- If the input includes a "Structured context recap" section, use it to
  understand intent, audience framing, tradeoffs, and why the change
  matters. Use the git diff as the source of truth for what changed.
- If no structured recap is provided, infer carefully from the diff and
  avoid over-claiming intent that is not supported.
- repo must be one of: casadora-core, casadora-services,
  casadora-experiments, cartero
- type must be one of: write, delete, mkdir
- path must be a non-empty relative path using forward slashes
- content is required for type: write
- content must NOT be present for type: delete or mkdir
- Do NOT include actions for auto-generated or dependency lock files such as
  uv.lock, poetry.lock, package-lock.json, yarn.lock, Pipfile.lock,
  Cargo.lock, composer.lock, or any file ending in .lock. Also exclude
  binary files, compiled artifacts, and any file whose content exceeds
  500 characters. These files should be acknowledged in the summary or
  impact fields if relevant, but never reproduced in actions.
- Return ONLY valid JSON
- Do not include markdown fences
- Do not include explanations, preamble, or trailing text
"""

STRICT_RETRY_SUFFIX = """
IMPORTANT: Your previous response could not be parsed.
Return ONLY a raw JSON object. No markdown, no explanation, no extra text.
The very first character of your response must be '{' and the last must be '}'.
"""

CONTEXT_RECAP_SYSTEM_PROMPT = """You are Cartero's context processor.

Cartero turns code changes into structured outputs like commit summaries,
changelogs, FAQs, and product-facing explanations.

You receive raw context copied from an LLM conversation, notes, or free text.
This input may be messy, redundant, incomplete, or overly detailed.

Your job is to compress that input into a short, high-signal recap that will be
used together with a git diff.

Important:

* The git diff will show what changed
* Your recap must explain why it matters
* Focus on intent, decisions, tradeoffs, and expected user-visible outcomes
* Do not describe code line by line
* Do not restate the whole conversation
* Do not hallucinate missing intent

Return ONLY this structure:

Goal:
User problem:
Key decisions:
Tradeoffs:
Expected user-visible outcome:
Explanation for non-technical users:

Rules:

* Be concise
* Remove redundancy
* Ignore implementation details unless they affect user-visible behavior
* Prefer clarity over completeness
* If something is unclear, leave it brief rather than guessing

Output only the structured recap.
"""

CONTEXT_RECAP_RETRY_SUFFIX = """
IMPORTANT: Your previous response did not follow the required structure.
Return ONLY this exact set of section headers in this order:
Goal:
User problem:
Key decisions:
Tradeoffs:
Expected user-visible outcome:
Explanation for non-technical users:
Do not add markdown fences, bullets outside the sections, or extra text.
"""

CONTEXT_RECAP_HEADERS = (
    "Goal:",
    "User problem:",
    "Key decisions:",
    "Tradeoffs:",
    "Expected user-visible outcome:",
    "Explanation for non-technical users:",
)


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


def _build_commit_generation_input(
    diff_text: str,
    *,
    context_recap: str | None = None,
) -> str:
    if not context_recap:
        return diff_text
    return (
        "Structured context recap:\n"
        f"{context_recap}\n\n"
        "Git diff:\n"
        f"{diff_text}"
    )


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
                raw_output = _call_llm(
                    client,
                    chunk,
                    config,
                    system_prompt=COMMIT_SUMMARY_SYSTEM_PROMPT,
                    retry_suffix=STRICT_RETRY_SUFFIX,
                    strict=attempt > 1,
                )
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


def _parse_context_recap(output: str) -> str:
    recap_text = _strip_fences(output).strip()
    if not recap_text:
        raise LLMCallError("Model returned empty output")
    if not recap_text.startswith(CONTEXT_RECAP_HEADERS[0]):
        raise LLMCallError("Model returned an invalid context recap: missing Goal header")

    last_position = -1
    for header in CONTEXT_RECAP_HEADERS:
        position = recap_text.find(header)
        if position == -1:
            raise LLMCallError(
                f"Model returned an invalid context recap: missing {header[:-1]!r} section"
            )
        if position <= last_position:
            raise LLMCallError("Model returned an invalid context recap: headers out of order")
        last_position = position
    return recap_text


def _get_client(config: CarteroConfig):
    if config.llm_provider == "anthropic":
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key or not api_key.strip():
            raise LLMConfigError("ANTHROPIC_API_KEY is not configured")
        if Anthropic is None:
            raise LLMConfigError("anthropic package is not installed")
        return Anthropic(api_key=api_key)

    if config.llm_provider == "gemini":
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key or not api_key.strip():
            raise LLMConfigError("GEMINI_API_KEY is not configured")
        if genai is None:
            raise LLMConfigError("google-generativeai package is not installed")
        genai.configure(api_key=api_key)
        return genai

    raise LLMConfigError(f"Unsupported llm_provider: {config.llm_provider}")


def _call_llm_anthropic(
    client,
    prompt_text: str,
    config: CarteroConfig,
    *,
    system_prompt: str,
    retry_suffix: str,
    strict: bool = False,
) -> str:
    system = system_prompt + (retry_suffix if strict else "")
    message = client.messages.create(
        model=config.model,
        max_tokens=config.max_tokens,
        system=system,
        messages=[{"role": "user", "content": prompt_text}],
    )
    return "".join(
        block.text for block in message.content if getattr(block, "type", None) == "text"
    ).strip()


def _call_llm_gemini(
    client,
    prompt_text: str,
    config: CarteroConfig,
    *,
    system_prompt: str,
    retry_suffix: str,
    strict: bool = False,
) -> str:
    try:
        system = system_prompt + (retry_suffix if strict else "")
        prompt = f"{system}\n\n{prompt_text}"
        model = client.GenerativeModel(config.model)
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as exc:
        raise LLMCallError(str(exc)) from exc


def _call_llm(
    client,
    prompt_text: str,
    config: CarteroConfig,
    *,
    system_prompt: str,
    retry_suffix: str,
    strict: bool = False,
) -> str:
    if config.llm_provider == "anthropic":
        return _call_llm_anthropic(
            client,
            prompt_text,
            config,
            system_prompt=system_prompt,
            retry_suffix=retry_suffix,
            strict=strict,
        )
    if config.llm_provider == "gemini":
        return _call_llm_gemini(
            client,
            prompt_text,
            config,
            system_prompt=system_prompt,
            retry_suffix=retry_suffix,
            strict=strict,
        )
    raise LLMConfigError(f"Unsupported llm_provider: {config.llm_provider}")


def generate_commit_summary_result(
    diff_text: str,
    config: CarteroConfig | None = None,
    *,
    context_recap: str | None = None,
) -> LLMGenerationResult:
    active_config = config or default_config
    llm_input = _build_commit_generation_input(diff_text, context_recap=context_recap)
    chunks = _split_diff_into_chunks(llm_input, active_config.max_diff_chars)
    was_chunked = len(chunks) > 1

    if was_chunked:
        logger.warning(
            "Diff was split into %d chunks (max_diff_tokens=%d). "
            "Processing each chunk separately.",
            len(chunks),
            active_config.max_diff_tokens,
        )
    client = _get_client(active_config)
    if was_chunked:
        yaml_text = _generate_from_chunks(client, chunks, active_config)
        return LLMGenerationResult(yaml_text, was_chunked=True)
    last_error: LLMCallError | None = None
    for attempt in range(1, max(1, active_config.max_retries) + 1):
        try:
            raw_output = _call_llm(
                client,
                llm_input,
                active_config,
                system_prompt=COMMIT_SUMMARY_SYSTEM_PROMPT,
                retry_suffix=STRICT_RETRY_SUFFIX,
                strict=attempt > 1,
            )
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
    diff_text: str,
    config: CarteroConfig | None = None,
    *,
    context_recap: str | None = None,
) -> str:
    return generate_commit_summary_result(
        diff_text,
        config,
        context_recap=context_recap,
    ).yaml_text


def generate_context_recap(
    raw_context: str, config: CarteroConfig | None = None
) -> str:
    if not isinstance(raw_context, str) or not raw_context.strip():
        raise ValueError("raw_context must be a non-empty string")

    active_config = config or default_config
    client = _get_client(active_config)
    last_error: LLMCallError | None = None

    for attempt in range(1, max(1, active_config.max_retries) + 1):
        try:
            raw_output = _call_llm(
                client,
                raw_context,
                active_config,
                system_prompt=CONTEXT_RECAP_SYSTEM_PROMPT,
                retry_suffix=CONTEXT_RECAP_RETRY_SUFFIX,
                strict=attempt > 1,
            )
            logger.debug("Raw context recap output (attempt %d):\n%s", attempt, raw_output)
            return _parse_context_recap(raw_output)
        except LLMCallError as exc:
            last_error = exc
            logger.warning("Context recap attempt %d failed: %s", attempt, exc)
        except Exception as exc:
            raise LLMCallError(str(exc)) from exc

    raise LLMCallError(
        f"Failed after {max(1, active_config.max_retries)} attempts. Last error: {last_error}"
    )
