from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path

import yaml

try:
    from anthropic import Anthropic
except ImportError:
    Anthropic = None

try:
    import google.generativeai as genai
except ImportError:
    genai = None

from cartero.canonical import CanonicalRecord, CanonicalRecordError, parse_canonical_record
from cartero.config import CarteroConfig, default_config
from cartero.semantic_quality import (
    normalize_commit_summary_fields,
    validate_commit_summary_quality,
)


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
- summary must be exactly one sentence, start with "Cartero", and stay
  short. Target 140 characters or fewer.
- reason is required and must be exactly one sentence explaining the
  real problem, limitation, inconsistency, ambiguity, or missing capability
  that existed before the change. It must never be empty.
- impact is required and must be exactly one sentence describing the
  concrete user-facing or developer-facing outcome after the change. Keep it short.
- summary, reason, and impact must stay product-style and understandable
  to a non-developer.
- do not use bullets, numbered lists, or multiline blocks in summary,
  reason, or impact.
- do not mention module names, function names, class names, file paths,
  or implementation details in summary, reason, or impact unless that
  identifier is absolutely required for a human to understand the change.
- reason must describe the before-state problem, not the implementation.
- impact must describe what is now clearer, easier, safer, more reliable,
  or possible for the person reading the commit.
- if the diff is broad, noisy, or highly technical, abstract toward the
  single most important human outcome instead of trying to document every
  internal change.
- do not repeat the same sentence across summary, reason, and impact.
- If the input includes a "Structured context recap" section, use it to
  understand intent, the user problem, tradeoffs, and the expected outcome.
  Prioritize a clear user problem from context when writing reason.
  Use the git diff as the source of truth for what changed.
- If no structured recap is provided, infer carefully from the diff and
  avoid over-claiming intent that is not supported.
- If the diff is too ambiguous to justify a strong claim, use a restrained
  truthful fallback instead of generic fluff or invented impact.
- Bad reason: "Improves canonical validation logic."
- Good reason: "Developers did not have a reliable way to trust commit summaries when the diff was noisy."
- Bad impact: "The parser now reuses canonical validation."
- Good impact: "Developers can now rely on commit summaries that stay consistent with the real change."
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
- Do NOT include actions for files under context/, docs/, or any directory
  that contains project documentation, session notes, or internal context.
  These are not executable changes and must never appear in actions.
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

SESSION_BRIEF_SYSTEM_PROMPT = """You are Cartero's session brief generator.

You receive the full content of context/master-context.md.

Your job is to generate a concise session brief that a fresh LLM can use to
start a working session without making decisions that contradict the architecture
or roadmap.

Return ONLY this structure, with no preamble, no markdown fences, no extra text:

# Cartero – Session Brief

## State
<last completed phase and what is pending or in progress>

## Strategic Direction
Cartero turns code changes into structured, reusable communication across
multiple outputs. It is a communication system, not a commit generator.

## Current Priorities
<numbered list of active priorities from the master context>

## Next Task
<the single most important next task, with enough detail to execute it>

## Modules Involved
<only the modules relevant to the next task>

## Rules (Non-Negotiable)
<include hard output rules, tone rules, architecture rules, and any LLM Interaction Rules from the Working Methodology section — keep this short, only rules an LLM would violate by default>

## End of Session
Before closing: summarize what changed, update context/master-context.md,
run `cartero commit --context-file <session-context-file>`, and push.
"""

CHANGELOG_SYSTEM_PROMPT = """You are Cartero's changelog generator.

Given a git diff and optional context, write a changelog entry for a product audience.

Rules:
- Write for end users, not developers
- Use product release note style (Notion / Linear)
- Start with a one-line headline summarizing what's new
- Follow with 2-4 bullet points of concrete user-facing changes
- Do not use git verbs: fix, refactor, chore, update, patch
- Never mention file names, function names, class names, or code identifiers of any kind — not even in backticks
- Describe capabilities in terms of what the user can do, not how it works internally
  - Wrong: "Added `generate_changelog()` to create changelog entries"
  - Right: "Cartero can now generate a changelog entry from any code change"
- If context is provided, use it to understand intent and user impact
- Return only the changelog text, no markdown fences, no preamble
"""

CONTEXT_RECAP_HEADERS = (
    "Goal:",
    "User problem:",
    "Key decisions:",
    "Tradeoffs:",
    "Expected user-visible outcome:",
    "Explanation for non-technical users:",
)

CANONICAL_RECORD_SYSTEM_PROMPT = """You are Cartero's canonical communication record generator.

Given a git diff and optional structured context recap, return ONLY one valid
CARTERO_RECORD_V1 plain-text record using the exact delimiters and block order below.

Required structure:

<<<CARTERO_RECORD_V1>>>
<<<SUMMARY>>>
<1-3 sentences. Must start with "Cartero".>
<<<END_SUMMARY>>>
<<<CHANGELOG>>>
<product-style changelog text in English. Paragraphs and bullet points are allowed.>
<<<END_CHANGELOG>>>
<<<FAQ>>>
<NONE or one or more valid FAQ items>
<<<END_FAQ>>>
<<<KNOWLEDGE_BASE>>>
<NONE or one or more valid KB items>
<<<END_KNOWLEDGE_BASE>>>
<<<END_CARTERO_RECORD_V1>>>

FAQ item format:
<<<FAQ_ITEM>>>
Q:
<question in English>
A:
<answer in English>
<<<END_FAQ_ITEM>>>

Knowledge base item format:
<<<KB_ITEM>>>
TITLE:
<title in English>
BODY:
<body in English>
<<<END_KB_ITEM>>>

Rules:
- Return only the canonical record. No markdown fences, no preamble, no trailing text.
- All content must be in English.
- Use exact delimiters with no extra spaces.
- SUMMARY and CHANGELOG are required and must not be empty.
- FAQ and KNOWLEDGE_BASE must be either NONE or valid items.
- Do not include ACTIONS, executable steps, file paths, code identifiers, or JSON.
- The git diff is the source of truth for what changed.
- Structured context recap can add intent, but must never contradict the diff.
- Use product release note style.
- SUMMARY must start with "Cartero".
- Do not use git verbs such as fix, refactor, chore, update, or patch.
- Do not include delimiter text inside content.
- If FAQ or KNOWLEDGE_BASE have no safe content, use NONE.
"""

CANONICAL_RECORD_RETRY_SUFFIX = """
IMPORTANT: Your previous response did not match the required canonical format.
Return ONLY one valid CARTERO_RECORD_V1 record with the exact delimiters,
exact block order, and no extra text. Do not return JSON. Do not return ACTIONS.
If FAQ or KNOWLEDGE_BASE have no safe content, return NONE for those blocks.
"""

COMMIT_BRIDGE_CANONICAL_GUIDANCE = """
Additional quality requirements for commit-summary bridging:
- The bridge will later derive `reason` and `impact` from this canonical record.
- Make the derived `reason` clearly reflect the pre-change problem, limitation, inconsistency, ambiguity, or missing capability.
- Make the derived `impact` clearly reflect the user-facing or developer-facing outcome after the change.
- SUMMARY must be exactly one sentence, start with "Cartero", and target 140 characters or fewer.
- SUMMARY must describe the most important human-visible improvement, not an implementation detail.
- CHANGELOG must stay concise and product-style. Prefer one short paragraph or at most 2 short bullets.
- The opening sentence of CHANGELOG should make the user-facing or developer-facing outcome obvious.
- When context includes a clear user problem, keep that problem visible in the framing of the record.
- Do not use CHANGELOG to document internal implementation inventories.
- Do not list internal implementation steps, diagnostics, or technical inventories.
- Do not mention module names, function names, class names, or file paths unless essential.
- If the diff is broad or technical, summarize only the most important human outcome.
- If the diff is ambiguous, use a restrained truthful fallback instead of a stronger unsupported claim.
- Bad reason source: "Introduces canonical validation for the bridge."
- Good reason source: "Developers did not have a reliable way to trust the generated summary."
- Bad impact source: "The parser and bridge now share delimiter validation."
- Good impact source: "Developers can now rely on summaries that stay aligned with the real change."
"""

COMMIT_BRIDGE_QUALITY_RETRY_GUIDANCE = """
IMPORTANT: Your previous response was structurally valid but not concise enough for commit-summary bridging.
Retry with a shorter SUMMARY and a more concise CHANGELOG focused on the most important human outcome.
Rewrite the record so the bridge can derive:
- a `reason` about the pre-change problem
- an `impact` about the outcome after the change
Do not include internal implementation details, technical inventories, repeated phrasing, or generic filler.
"""


class LLMConfigError(Exception):
    pass


class LLMCallError(Exception):
    pass


@dataclass(frozen=True)
class LLMGenerationResult:
    yaml_text: str
    was_chunked: bool
    canonical_text: str | None = None
    commit_fields: dict[str, object] | None = None
    quality_metadata: dict[str, object] | None = None


@dataclass(frozen=True)
class CanonicalLLMGenerationResult:
    canonical_text: str
    record: CanonicalRecord
    was_chunked: bool
    retry_count: int = 0


@dataclass(frozen=True)
class LegacySummaryBridgeResult:
    yaml_text: str
    commit_fields: dict[str, object]
    quality_metadata: dict[str, object]


@dataclass(frozen=True)
class LegacySummaryPayloadResult:
    payload: dict[str, object]
    used_normalization: bool
    normalization_rules: tuple[str, ...]
    used_fallback_reason: bool
    used_fallback_impact: bool


@dataclass(frozen=True)
class CommitBridgeDiffAssessment:
    file_paths: tuple[str, ...]
    change_line_count: int
    documentation_only: bool
    tests_only: bool
    formatting_only: bool
    ambiguous: bool


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


def _render_canonical_record(record: CanonicalRecord) -> str:
    return "\n".join(
        [
            "<<<CARTERO_RECORD_V1>>>",
            "<<<SUMMARY>>>",
            record.summary,
            "<<<END_SUMMARY>>>",
            "<<<CHANGELOG>>>",
            record.changelog,
            "<<<END_CHANGELOG>>>",
            "<<<FAQ>>>",
            _render_faq_block(record),
            "<<<END_FAQ>>>",
            "<<<KNOWLEDGE_BASE>>>",
            _render_knowledge_base_block(record),
            "<<<END_KNOWLEDGE_BASE>>>",
            "<<<END_CARTERO_RECORD_V1>>>",
        ]
    )


def _render_faq_block(record: CanonicalRecord) -> str:
    if not record.faq_items:
        return "NONE"

    lines: list[str] = []
    for item in record.faq_items:
        lines.extend(
            [
                "<<<FAQ_ITEM>>>",
                "Q:",
                item.question,
                "A:",
                item.answer,
                "<<<END_FAQ_ITEM>>>",
            ]
        )
    return "\n".join(lines)


def _render_knowledge_base_block(record: CanonicalRecord) -> str:
    if not record.knowledge_base_items:
        return "NONE"

    lines: list[str] = []
    for item in record.knowledge_base_items:
        lines.extend(
            [
                "<<<KB_ITEM>>>",
                "TITLE:",
                item.title,
                "BODY:",
                item.body,
                "<<<END_KB_ITEM>>>",
            ]
        )
    return "\n".join(lines)


def _parse_canonical_output(output: str) -> tuple[str, CanonicalRecord]:
    canonical_text = _strip_fences(output)
    if not canonical_text:
        raise LLMCallError("Model returned empty output")

    try:
        record = parse_canonical_record(canonical_text)
    except CanonicalRecordError as exc:
        raise LLMCallError(
            f"Model returned an invalid canonical record: {exc}\nRaw output:\n{canonical_text}"
        ) from exc

    return canonical_text, record


def _merge_canonical_records(records: list[CanonicalRecord]) -> CanonicalRecord:
    if not records:
        raise LLMCallError("No canonical records were available to merge.")

    first_summary = records[0].summary
    if any(record.summary != first_summary for record in records[1:]):
        logger.warning(
            "Chunked canonical generation returned multiple summaries. "
            "Keeping the first summary and merging the remaining blocks."
        )

    merged_changelog = "\n\n".join(
        record.changelog.strip()
        for record in records
        if record.changelog.strip()
    )
    faq_items = tuple(
        item
        for record in records
        for item in record.faq_items
    )
    knowledge_base_items = tuple(
        item
        for record in records
        for item in record.knowledge_base_items
    )

    merged_record = CanonicalRecord(
        summary=first_summary,
        changelog=merged_changelog,
        faq_items=faq_items,
        knowledge_base_items=knowledge_base_items,
    )

    # Re-parse the rendered text to ensure the merged output still satisfies
    # the same contract we accept from the model.
    parse_canonical_record(_render_canonical_record(merged_record))
    return merged_record


def _canonical_record_to_legacy_yaml(record: CanonicalRecord) -> str:
    """Temporary bridge while downstream CLI/web paths still expect YAML."""
    return _canonical_record_to_legacy_yaml_with_context(
        record,
        context_recap=None,
        diff_text=None,
    )


def _canonical_record_to_legacy_yaml_with_context(
    record: CanonicalRecord,
    *,
    context_recap: str | None,
    diff_text: str | None = None,
) -> str:
    bridge_result = build_legacy_yaml_bridge_result(
        record,
        context_recap=context_recap,
        diff_text=diff_text,
    )
    return bridge_result.yaml_text


def build_legacy_yaml_bridge_result(
    record: CanonicalRecord,
    *,
    context_recap: str | None = None,
    diff_text: str | None = None,
    retry_count: int = 0,
) -> LegacySummaryBridgeResult:
    payload_result = _build_legacy_summary_payload(
        record,
        context_recap=context_recap,
        diff_text=diff_text,
    )
    semantic_result = _validate_legacy_summary_payload(payload_result.payload)
    yaml_output = yaml.dump(
        payload_result.payload,
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
    return LegacySummaryBridgeResult(
        yaml_text=yaml_output,
        commit_fields=_copy_legacy_commit_fields(payload_result.payload),
        quality_metadata={
            "semantic_status": semantic_result.status,
            "semantic_warnings": [
                _serialize_semantic_issue(issue) for issue in semantic_result.warnings
            ],
            "used_normalization": payload_result.used_normalization,
            "normalization_rules": list(payload_result.normalization_rules),
            "retry_count": retry_count,
            "used_fallback_reason": payload_result.used_fallback_reason,
            "used_fallback_impact": payload_result.used_fallback_impact,
        },
    )


def render_legacy_yaml_bridge(
    record: CanonicalRecord,
    *,
    context_recap: str | None = None,
    diff_text: str | None = None,
) -> str:
    """Temporary public bridge while callers migrate away from YAML."""

    return _canonical_record_to_legacy_yaml_with_context(
        record,
        context_recap=context_recap,
        diff_text=diff_text,
    )


def _build_legacy_summary_payload(
    record: CanonicalRecord,
    *,
    context_recap: str | None,
    diff_text: str | None,
) -> LegacySummaryPayloadResult:
    summary = _normalize_commit_field(record.summary, max_chars=140)
    recap_sections = _parse_context_recap_sections(context_recap)
    diff_assessment = _assess_commit_bridge_diff(diff_text)
    reason_source = recap_sections.get("User problem")
    used_fallback_reason = reason_source is None
    if reason_source is None:
        fallback_reason = _fallback_reason_for_diff_assessment(diff_assessment)
        reason_source = (
            recap_sections.get("Explanation for non-technical users")
            or fallback_reason
        )
    impact_source = recap_sections.get("Expected user-visible outcome")
    used_fallback_impact = impact_source is None
    if impact_source is None:
        fallback_impact = _fallback_impact_for_diff_assessment(diff_assessment)
        impact_source = fallback_impact or _first_commit_sentence(record.changelog) or summary
    reason = _normalize_commit_field(reason_source, max_chars=180)
    impact = _normalize_commit_field(impact_source, max_chars=180)
    normalized_fields = normalize_commit_summary_fields(
        summary=summary,
        reason=reason,
        impact=impact,
        problem_hint=recap_sections.get("User problem"),
        outcome_hint=recap_sections.get("Expected user-visible outcome"),
    )
    if normalized_fields.changed:
        logger.debug(
            "Applied commit-summary normalization rules: %s",
            ", ".join(normalized_fields.applied_rules),
        )
    if "reason" in normalized_fields.applied_rules:
        used_fallback_reason = True
    if "impact" in normalized_fields.applied_rules:
        used_fallback_impact = True
    return LegacySummaryPayloadResult(
        payload={
            "summary": normalized_fields.summary,
            "reason": normalized_fields.reason,
            "impact": normalized_fields.impact,
            "actions": [],
        },
        used_normalization=normalized_fields.changed,
        normalization_rules=normalized_fields.applied_rules,
        used_fallback_reason=used_fallback_reason,
        used_fallback_impact=used_fallback_impact,
    )


def _parse_context_recap_sections(context_recap: str | None) -> dict[str, str]:
    if not context_recap:
        return {}

    sections: dict[str, list[str]] = {}
    current_header: str | None = None
    known_headers = {header[:-1]: header for header in CONTEXT_RECAP_HEADERS}

    for raw_line in context_recap.splitlines():
        stripped = raw_line.strip()
        matched_header = next(
            (header_name for header_name, header in known_headers.items() if stripped.startswith(header)),
            None,
        )
        if matched_header is not None:
            current_header = matched_header
            remainder = stripped.split(":", 1)[1].strip()
            sections[current_header] = [remainder] if remainder else []
            continue
        if current_header is not None and stripped:
            sections[current_header].append(stripped)

    return {
        header: _normalize_commit_field(" ".join(lines), max_chars=220)
        for header, lines in sections.items()
        if lines
    }


def _assess_commit_bridge_diff(diff_text: str | None) -> CommitBridgeDiffAssessment:
    if not diff_text or not diff_text.strip():
        return CommitBridgeDiffAssessment(
            file_paths=(),
            change_line_count=0,
            documentation_only=False,
            tests_only=False,
            formatting_only=False,
            ambiguous=True,
        )

    file_paths = tuple(_extract_diff_paths(diff_text))
    added_lines, removed_lines = _extract_changed_line_pairs(diff_text)
    changed_content_lines = [
        line[1:].strip()
        for line in diff_text.splitlines()
        if line.startswith(("+", "-"))
        and not line.startswith(("+++", "---"))
        and line[1:].strip()
    ]
    documentation_only = bool(file_paths) and all(_is_documentation_like_path(path) for path in file_paths)
    tests_only = bool(file_paths) and all(_is_test_like_path(path) for path in file_paths)
    formatting_only = _is_formatting_only_change(added_lines=added_lines, removed_lines=removed_lines)
    low_change_volume = len(changed_content_lines) <= 6
    low_signal_lines = bool(changed_content_lines) and all(
        _is_low_signal_change_line(line) for line in changed_content_lines
    )
    ambiguous = (
        documentation_only
        or tests_only
        or formatting_only
        or (low_change_volume and low_signal_lines)
    )
    return CommitBridgeDiffAssessment(
        file_paths=file_paths,
        change_line_count=len(changed_content_lines),
        documentation_only=documentation_only,
        tests_only=tests_only,
        formatting_only=formatting_only,
        ambiguous=ambiguous,
    )


def _extract_diff_paths(diff_text: str) -> list[str]:
    paths: list[str] = []
    for line in diff_text.splitlines():
        if line.startswith("+++ b/"):
            path = line[6:].strip()
            if path and path != "/dev/null":
                paths.append(path)
    return paths


def _extract_changed_line_pairs(diff_text: str) -> tuple[list[str], list[str]]:
    added_lines: list[str] = []
    removed_lines: list[str] = []
    for line in diff_text.splitlines():
        if line.startswith("+++") or line.startswith("---"):
            continue
        if line.startswith("+"):
            added_lines.append(line[1:])
        elif line.startswith("-"):
            removed_lines.append(line[1:])
    return added_lines, removed_lines


def _is_documentation_like_path(path: str) -> bool:
    lower_path = path.lower()
    name = Path(lower_path).name
    return (
        lower_path.startswith("docs/")
        or lower_path.startswith("context/")
        or name in {"readme", "readme.md", "readme.rst", "changelog.md"}
        or lower_path.endswith((".md", ".mdx", ".rst", ".txt", ".adoc"))
    )


def _is_test_like_path(path: str) -> bool:
    lower_path = path.lower()
    return (
        lower_path.startswith("tests/")
        or "/tests/" in lower_path
        or "/fixtures/" in lower_path
        or lower_path.endswith(("_test.py", "_spec.py"))
        or lower_path.endswith(".snap")
    )


def _is_low_signal_change_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return True
    if len(stripped) > 120:
        return False
    if _looks_like_code_style_identifier(stripped):
        return True
    if re.search(r'"[^"]+"|\'[^\']+\'', stripped):
        return True
    if re.match(r"^(def|class)\s+[A-Za-z0-9_]+", stripped):
        return True
    if re.match(r"^[A-Z0-9_]+\s*=", stripped):
        return True
    if re.match(r"^(return|assert)\b", stripped):
        return True
    if re.match(r"^[A-Za-z0-9_.:/-]+$", stripped):
        return True
    return False


def _looks_like_code_style_identifier(text: str) -> bool:
    return bool(re.search(r"[a-z0-9_]+\.[a-z0-9_]+|`[^`]+`|[a-z_]+\(\)", text))


def _is_formatting_only_change(*, added_lines: list[str], removed_lines: list[str]) -> bool:
    if not added_lines and not removed_lines:
        return False
    if len(added_lines) != len(removed_lines):
        return False
    return all(
        _normalize_formatting_line(added) == _normalize_formatting_line(removed)
        for added, removed in zip(added_lines, removed_lines)
    )


def _normalize_formatting_line(line: str) -> str:
    return " ".join(line.split())


def _fallback_reason_for_diff_assessment(assessment: CommitBridgeDiffAssessment) -> str:
    if assessment.documentation_only:
        return "Before this change, the documentation around this behavior was easier to misread."
    if assessment.tests_only:
        return "Before this change, the expected behavior was less clearly captured in supporting tests."
    if assessment.formatting_only:
        return "Before this change, this area was formatted less consistently."
    if assessment.ambiguous:
        return "Before this change, this area was described less consistently."
    return "Before this change, the change was harder to interpret from the diff alone."


def _fallback_impact_for_diff_assessment(assessment: CommitBridgeDiffAssessment) -> str | None:
    if assessment.documentation_only:
        return "Developers can now review the documentation with less ambiguity."
    if assessment.tests_only:
        return "Developers can now review the expected behavior with less ambiguity."
    if assessment.formatting_only:
        return "Developers can now scan this area with less visual ambiguity."
    if assessment.ambiguous:
        return "Developers can now review this area with less ambiguity."
    return None


def _first_commit_sentence(text: str) -> str:
    cleaned = _clean_commit_text(text)
    if not cleaned:
        return ""
    parts = re.split(r"(?<=[.!?])\s+", cleaned)
    return parts[0].strip()


def _clean_commit_text(text: str) -> str:
    cleaned_lines: list[str] = []
    for raw_line in _strip_fences(text).replace("\r\n", "\n").replace("\r", "\n").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith(("- ", "* ", "• ")):
            line = line[2:].strip()
        cleaned_lines.append(line.replace("`", ""))
    return " ".join(" ".join(cleaned_lines).split())


def _normalize_commit_field(text: str, *, max_chars: int) -> str:
    cleaned = _clean_commit_text(text)
    if not cleaned:
        return ""
    first_sentence = _first_commit_sentence(cleaned)
    candidate = first_sentence or cleaned
    if len(candidate) <= max_chars:
        return candidate
    truncated = candidate[: max_chars - 3].rsplit(" ", 1)[0].rstrip(" ,;:")
    if not truncated:
        truncated = candidate[: max_chars - 3].rstrip(" ,;:")
    return f"{truncated}..."


def _validate_legacy_summary_payload(payload: dict[str, object]):
    summary = str(payload.get("summary", "")).strip()
    reason = str(payload.get("reason", "")).strip()
    impact = str(payload.get("impact", "")).strip()

    if not summary.startswith("Cartero"):
        raise LLMCallError("Commit summary quality check failed: summary must start with 'Cartero'")
    if _contains_commit_bullets_or_newlines(summary):
        raise LLMCallError("Commit summary quality check failed: summary must be a single short sentence")
    if len(summary) > 160:
        raise LLMCallError("Commit summary quality check failed: summary is too long")
    if not reason:
        raise LLMCallError("Commit summary quality check failed: reason must not be empty")
    if _contains_commit_bullets_or_newlines(reason):
        raise LLMCallError("Commit summary quality check failed: reason must be a single sentence")
    if len(reason) > 220:
        raise LLMCallError("Commit summary quality check failed: reason is too long")
    if not impact:
        raise LLMCallError("Commit summary quality check failed: impact must not be empty")
    if _contains_commit_bullets_or_newlines(impact):
        raise LLMCallError("Commit summary quality check failed: impact must be a single sentence")
    if len(impact) > 220:
        raise LLMCallError("Commit summary quality check failed: impact is too long")

    semantic_result = validate_commit_summary_quality(
        summary=summary,
        reason=reason,
        impact=impact,
    )
    if semantic_result.status == "fail":
        raise LLMCallError(
            "Commit summary semantic quality check failed: "
            + "; ".join(semantic_result.messages(severity="fail"))
        )
    if semantic_result.status == "warn":
        logger.warning(
            "Commit summary semantic quality warning: %s",
            "; ".join(semantic_result.messages(severity="warn")),
        )
    return semantic_result


def _copy_legacy_commit_fields(payload: dict[str, object]) -> dict[str, object]:
    actions = payload.get("actions", [])
    if not isinstance(actions, (list, tuple)):
        actions = []
    return {
        "summary": str(payload.get("summary", "")),
        "reason": str(payload.get("reason", "")),
        "impact": str(payload.get("impact", "")),
        "actions": [
            dict(action) if isinstance(action, dict) else action
            for action in actions
        ],
    }


def _serialize_semantic_issue(issue) -> dict[str, str]:
    return {
        "field": issue.field,
        "code": issue.code,
        "severity": issue.severity,
        "message": issue.message,
    }


def _contains_commit_bullets_or_newlines(text: str) -> bool:
    if "\n" in text:
        return True
    stripped = text.lstrip()
    return stripped.startswith(("- ", "* ", "• "))


def validate_commit_bridge_source_record(record: CanonicalRecord) -> None:
    summary = _clean_commit_text(record.summary)
    if not summary.startswith("Cartero"):
        raise LLMCallError(
            "Commit summary quality check failed: canonical summary must start with 'Cartero'"
        )
    if _contains_commit_bullets_or_newlines(record.summary):
        raise LLMCallError(
            "Commit summary quality check failed: canonical summary must be a single sentence"
        )
    if len(summary) > 160:
        raise LLMCallError(
            "Commit summary quality check failed: canonical summary is too long"
        )


def _generate_canonical_record_from_chunks(
    client,
    chunks: list[str],
    config: CarteroConfig,
    *,
    system_prompt: str,
    retry_suffix: str,
) -> CanonicalLLMGenerationResult:
    parsed_records: list[CanonicalRecord] = []
    retry_count = 0

    for chunk_index, chunk in enumerate(chunks, start=1):
        last_error: Exception | None = None

        for attempt in range(1, max(1, config.max_retries) + 1):
            try:
                raw_output = _call_llm(
                    client,
                    chunk,
                    config,
                    system_prompt=system_prompt,
                    retry_suffix=retry_suffix,
                    strict=attempt > 1,
                )
                logger.debug(
                    "Raw canonical LLM output for chunk %d (attempt %d):\n%s",
                    chunk_index,
                    attempt,
                    raw_output,
                )
                _, record = _parse_canonical_output(raw_output)
                parsed_records.append(record)
                retry_count += attempt - 1
                break
            except LLMCallError as exc:
                last_error = exc
                logger.warning(
                    "Canonical chunk %d attempt %d failed: %s",
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

    merged_record = _merge_canonical_records(parsed_records)
    canonical_text = _render_canonical_record(merged_record)
    return CanonicalLLMGenerationResult(
        canonical_text=canonical_text,
        record=merged_record,
        was_chunked=True,
        retry_count=retry_count,
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
    stream: bool = False,
) -> str:
    system = system_prompt + (retry_suffix if strict else "")
    if stream:
        collected = []
        with client.messages.stream(
            model=config.model,
            max_tokens=config.max_tokens,
            system=system,
            messages=[{"role": "user", "content": prompt_text}],
        ) as s:
            for text in s.text_stream:
                print(text, end="", flush=True)
                collected.append(text)
        print()
        return "".join(collected).strip()
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
    stream: bool = False,
) -> str:
    if config.llm_provider == "anthropic":
        return _call_llm_anthropic(
            client,
            prompt_text,
            config,
            system_prompt=system_prompt,
            retry_suffix=retry_suffix,
            strict=strict,
            stream=stream,
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


def generate_canonical_record_result(
    diff_text: str,
    config: CarteroConfig | None = None,
    *,
    context_recap: str | None = None,
    extra_system_prompt: str = "",
    extra_retry_suffix: str = "",
) -> CanonicalLLMGenerationResult:
    active_config = config or default_config
    llm_input = _build_commit_generation_input(diff_text, context_recap=context_recap)
    chunks = _split_diff_into_chunks(llm_input, active_config.max_diff_chars)
    was_chunked = len(chunks) > 1
    system_prompt = CANONICAL_RECORD_SYSTEM_PROMPT + extra_system_prompt
    retry_suffix = CANONICAL_RECORD_RETRY_SUFFIX + extra_retry_suffix

    if was_chunked:
        logger.warning(
            "Diff was split into %d chunks (max_diff_tokens=%d). "
            "Processing canonical records per chunk.",
            len(chunks),
            active_config.max_diff_tokens,
        )

    client = _get_client(active_config)
    if was_chunked:
        return _generate_canonical_record_from_chunks(
            client,
            chunks,
            active_config,
            system_prompt=system_prompt,
            retry_suffix=retry_suffix,
        )

    last_error: LLMCallError | None = None
    for attempt in range(1, max(1, active_config.max_retries) + 1):
        try:
            raw_output = _call_llm(
                client,
                llm_input,
                active_config,
                system_prompt=system_prompt,
                retry_suffix=retry_suffix,
                strict=attempt > 1,
            )
            logger.debug("Raw canonical LLM output (attempt %d):\n%s", attempt, raw_output)
            canonical_text, record = _parse_canonical_output(raw_output)
            return CanonicalLLMGenerationResult(
                canonical_text=canonical_text,
                record=record,
                was_chunked=False,
                retry_count=attempt - 1,
            )
        except LLMCallError as exc:
            last_error = exc
            logger.warning("Canonical LLM attempt %d failed: %s", attempt, exc)
        except Exception as exc:
            raise LLMCallError(str(exc)) from exc
    raise LLMCallError(
        f"Failed after {max(1, active_config.max_retries)} attempts. Last error: {last_error}"
    )


def generate_canonical_record(
    diff_text: str,
    config: CarteroConfig | None = None,
    *,
    context_recap: str | None = None,
) -> str:
    return generate_canonical_record_result(
        diff_text,
        config,
        context_recap=context_recap,
    ).canonical_text


def generate_commit_summary_result(
    diff_text: str,
    config: CarteroConfig | None = None,
    *,
    context_recap: str | None = None,
) -> LLMGenerationResult:
    # Keep a temporary YAML bridge here so generator/CLI/web can remain stable
    # while the LLM layer switches its primary contract to CARTERO_RECORD_V1.
    canonical_result = generate_canonical_record_result(
        diff_text,
        config,
        context_recap=context_recap,
    )
    bridge_result = build_legacy_yaml_bridge_result(
        canonical_result.record,
        context_recap=context_recap,
        diff_text=diff_text,
        retry_count=canonical_result.retry_count,
    )
    return LLMGenerationResult(
        yaml_text=bridge_result.yaml_text,
        was_chunked=canonical_result.was_chunked,
        canonical_text=canonical_result.canonical_text,
        commit_fields=bridge_result.commit_fields,
        quality_metadata=bridge_result.quality_metadata,
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


def generate_changelog(
    diff_text: str,
    config: CarteroConfig | None = None,
    *,
    context_recap: str | None = None,
) -> str:
    active_config = config or default_config
    client = _get_client(active_config)
    llm_input = _build_commit_generation_input(diff_text, context_recap=context_recap)
    last_error: LLMCallError | None = None

    for attempt in range(1, max(1, active_config.max_retries) + 1):
        try:
            raw_output = _call_llm(
                client,
                llm_input,
                active_config,
                system_prompt=CHANGELOG_SYSTEM_PROMPT,
                retry_suffix="IMPORTANT: Return only the changelog text. No fences, no preamble.",
                strict=attempt > 1,
                stream=True,
            )
            if not raw_output.strip():
                raise LLMCallError("Model returned empty output")
            return raw_output.strip()
        except LLMCallError as exc:
            last_error = exc
            logger.warning("Changelog attempt %d failed: %s", attempt, exc)
        except Exception as exc:
            raise LLMCallError(str(exc)) from exc

    raise LLMCallError(
        f"Failed after {max(1, active_config.max_retries)} attempts. Last error: {last_error}"
    )


def generate_session_brief(config: CarteroConfig | None = None) -> str:
    master_context_path = Path("context/master-context.md")
    if not master_context_path.exists():
        raise ValueError(
            f"Master context not found at {master_context_path}. "
            "Run this command from the root of the Cartero repository."
        )
    master_context = master_context_path.read_text(encoding="utf-8")

    active_config = config or default_config
    client = _get_client(active_config)
    last_error: LLMCallError | None = None

    for attempt in range(1, max(1, active_config.max_retries) + 1):
        try:
            raw_output = _call_llm(
                client,
                master_context,
                active_config,
                system_prompt=SESSION_BRIEF_SYSTEM_PROMPT,
                retry_suffix="IMPORTANT: Return only the session brief. No fences, no preamble.",
                strict=attempt > 1,
                stream=True,
            )
            if not raw_output.strip():
                raise LLMCallError("Model returned empty output")
            return raw_output.strip()
        except LLMCallError as exc:
            last_error = exc
            logger.warning("Session brief attempt %d failed: %s", attempt, exc)
        except Exception as exc:
            raise LLMCallError(str(exc)) from exc

    raise LLMCallError(
        f"Failed after {max(1, active_config.max_retries)} attempts. Last error: {last_error}"
    )


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
