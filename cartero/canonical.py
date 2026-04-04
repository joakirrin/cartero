from __future__ import annotations

"""Parse and validate the CARTERO_RECORD_V1 canonical contract.

This module enforces structural correctness and performs only minimal,
conservative sanitization:
- normalize newlines
- trim document-level outer whitespace
- reject malformed delimiters and ambiguous records

It does not validate semantic quality, user-impact claims, or whether the
content is written in English. Language quality remains a higher-level concern
for prompt and output validation. The module is intentionally decoupled from
the current JSON/YAML pipeline so both formats can coexist during the Phase 5
migration.

Example:
    raw_record = \"\"\"<<<CARTERO_RECORD_V1>>>
    <<<SUMMARY>>>
    Cartero now shows a real changelog preview before execution.
    <<<END_SUMMARY>>>
    <<<CHANGELOG>>>
    Cartero now shows the real changelog preview before execution.
    <<<END_CHANGELOG>>>
    <<<FAQ>>>
    NONE
    <<<END_FAQ>>>
    <<<KNOWLEDGE_BASE>>>
    NONE
    <<<END_KNOWLEDGE_BASE>>>
    <<<END_CARTERO_RECORD_V1>>>\"\"\"
    record = parse_canonical_record(raw_record)
    assert record.summary.startswith("Cartero")
"""

from dataclasses import dataclass


RECORD_START = "<<<CARTERO_RECORD_V1>>>"
RECORD_END = "<<<END_CARTERO_RECORD_V1>>>"

SUMMARY_START = "<<<SUMMARY>>>"
SUMMARY_END = "<<<END_SUMMARY>>>"
CHANGELOG_START = "<<<CHANGELOG>>>"
CHANGELOG_END = "<<<END_CHANGELOG>>>"
FAQ_START = "<<<FAQ>>>"
FAQ_END = "<<<END_FAQ>>>"
KNOWLEDGE_BASE_START = "<<<KNOWLEDGE_BASE>>>"
KNOWLEDGE_BASE_END = "<<<END_KNOWLEDGE_BASE>>>"

FAQ_ITEM_START = "<<<FAQ_ITEM>>>"
FAQ_ITEM_END = "<<<END_FAQ_ITEM>>>"
KB_ITEM_START = "<<<KB_ITEM>>>"
KB_ITEM_END = "<<<END_KB_ITEM>>>"

EMPTY_MARKER = "NONE"


@dataclass(frozen=True)
class CanonicalFAQItem:
    question: str
    answer: str


@dataclass(frozen=True)
class CanonicalKBItem:
    title: str
    body: str


@dataclass(frozen=True)
class CanonicalRecord:
    summary: str
    changelog: str
    faq_items: tuple[CanonicalFAQItem, ...]
    knowledge_base_items: tuple[CanonicalKBItem, ...]


@dataclass(frozen=True)
class _TopLevelBlockSpec:
    name: str
    start: str
    end: str


TOP_LEVEL_BLOCKS = (
    _TopLevelBlockSpec("SUMMARY", SUMMARY_START, SUMMARY_END),
    _TopLevelBlockSpec("CHANGELOG", CHANGELOG_START, CHANGELOG_END),
    _TopLevelBlockSpec("FAQ", FAQ_START, FAQ_END),
    _TopLevelBlockSpec("KNOWLEDGE_BASE", KNOWLEDGE_BASE_START, KNOWLEDGE_BASE_END),
)

TOP_LEVEL_START_LINES = {block.start for block in TOP_LEVEL_BLOCKS}
TOP_LEVEL_END_LINES = {block.end for block in TOP_LEVEL_BLOCKS}
TOP_LEVEL_START_TO_NAME = {block.start: block.name for block in TOP_LEVEL_BLOCKS}
RECORD_DELIMITER_LINES = {RECORD_START, RECORD_END}
ITEM_DELIMITER_LINES = {FAQ_ITEM_START, FAQ_ITEM_END, KB_ITEM_START, KB_ITEM_END}
ALL_DELIMITER_LINES = (
    RECORD_DELIMITER_LINES | TOP_LEVEL_START_LINES | TOP_LEVEL_END_LINES | ITEM_DELIMITER_LINES
)


class CanonicalRecordError(ValueError):
    """Base error for canonical record parsing and validation failures."""


class EmptyRecordError(CanonicalRecordError):
    """Raised when the candidate record is empty after minimal sanitization."""


class MissingRecordStartDelimiterError(CanonicalRecordError):
    """Raised when the record start delimiter is missing."""


class MissingRecordEndDelimiterError(CanonicalRecordError):
    """Raised when the record end delimiter is missing."""


class InvalidBlockOrderError(CanonicalRecordError):
    """Raised when top-level blocks are not in the exact approved order."""


class DuplicateTopLevelBlockError(CanonicalRecordError):
    """Raised when a top-level block appears more than once."""


class MissingTopLevelBlockError(CanonicalRecordError):
    """Raised when a required top-level block or its end delimiter is missing."""


class InvalidEmptyMarkerError(CanonicalRecordError):
    """Raised when the NONE marker is malformed or mixed with content."""


class EmptyRequiredBlockError(CanonicalRecordError):
    """Raised when SUMMARY or CHANGELOG is empty."""


class MalformedFAQItemError(CanonicalRecordError):
    """Raised when an FAQ item does not match the contract."""


class MalformedKBItemError(CanonicalRecordError):
    """Raised when a knowledge base item does not match the contract."""


class EmbeddedDelimiterError(CanonicalRecordError):
    """Raised when a delimiter appears inside content where it is not allowed."""


class InvalidDelimiterSpacingError(CanonicalRecordError):
    """Raised when a delimiter line has leading or trailing whitespace."""


def sanitize_canonical_text(candidate: str) -> str:
    """Return a minimally sanitized canonical record candidate."""

    normalized = candidate.replace("\r\n", "\n").replace("\r", "\n")
    if normalized.strip() == "":
        raise EmptyRecordError("Canonical record is empty.")

    _validate_delimiter_spacing(normalized)
    sanitized = normalized.strip()
    if sanitized == "":
        raise EmptyRecordError("Canonical record is empty.")
    return sanitized


def validate_canonical_record(candidate: str) -> None:
    """Validate a candidate canonical record and raise on failure."""

    parse_canonical_record(candidate)


def parse_canonical_record(candidate: str) -> CanonicalRecord:
    """Parse a candidate canonical record into a stable Python structure."""

    text = sanitize_canonical_text(candidate)
    lines = text.split("\n")

    if lines[0] != RECORD_START:
        raise MissingRecordStartDelimiterError(
            f"Canonical record must start with {RECORD_START!r}."
        )
    if lines[-1] != RECORD_END:
        raise MissingRecordEndDelimiterError(
            f"Canonical record must end with {RECORD_END!r}."
        )

    index = 1
    seen_blocks: set[str] = set()
    block_bodies: dict[str, str] = {}

    for block in TOP_LEVEL_BLOCKS:
        index = _expect_top_level_block_start(lines, index, block, seen_blocks)
        seen_blocks.add(block.name)
        body, index = _collect_top_level_block_body(lines, index, block)
        block_bodies[block.name] = body

    if index != len(lines) - 1:
        extra_line = lines[index]
        if extra_line in TOP_LEVEL_START_TO_NAME:
            block_name = TOP_LEVEL_START_TO_NAME[extra_line]
            if block_name in seen_blocks:
                raise DuplicateTopLevelBlockError(
                    f"Top-level block {block_name} appears more than once."
                )
            raise InvalidBlockOrderError(
                f"Unexpected top-level block {block_name} found after KNOWLEDGE_BASE."
            )
        if extra_line in ALL_DELIMITER_LINES:
            raise EmbeddedDelimiterError(
                f"Unexpected delimiter line {extra_line!r} found before {RECORD_END!r}."
            )
        raise CanonicalRecordError(
            "Unexpected content found after the final top-level block."
        )

    summary = _parse_required_text_block(block_bodies["SUMMARY"], block_name="SUMMARY")
    changelog = _parse_required_text_block(
        block_bodies["CHANGELOG"],
        block_name="CHANGELOG",
    )
    faq_items = _parse_faq_block(block_bodies["FAQ"])
    knowledge_base_items = _parse_kb_block(block_bodies["KNOWLEDGE_BASE"])

    return CanonicalRecord(
        summary=summary,
        changelog=changelog,
        faq_items=faq_items,
        knowledge_base_items=knowledge_base_items,
    )


def _validate_delimiter_spacing(text: str) -> None:
    for line in text.split("\n"):
        stripped = line.strip()
        if stripped in ALL_DELIMITER_LINES and line != stripped:
            raise InvalidDelimiterSpacingError(
                f"Delimiter line must match exactly with no extra spaces: {stripped!r}."
            )


def _expect_top_level_block_start(
    lines: list[str],
    index: int,
    block: _TopLevelBlockSpec,
    seen_blocks: set[str],
) -> int:
    if index >= len(lines) - 1:
        raise MissingTopLevelBlockError(
            f"Missing top-level block {block.name}."
        )

    line = lines[index]
    if line == block.start:
        return index + 1

    if line in TOP_LEVEL_START_TO_NAME:
        found_name = TOP_LEVEL_START_TO_NAME[line]
        if found_name in seen_blocks:
            raise DuplicateTopLevelBlockError(
                f"Top-level block {found_name} appears more than once."
            )
        raise InvalidBlockOrderError(
            f"Expected top-level block {block.name} but found {found_name}."
        )

    if line == RECORD_END:
        raise MissingTopLevelBlockError(
            f"Missing top-level block {block.name}."
        )

    raise MissingTopLevelBlockError(
        f"Missing start delimiter for top-level block {block.name}."
    )


def _collect_top_level_block_body(
    lines: list[str],
    index: int,
    block: _TopLevelBlockSpec,
) -> tuple[str, int]:
    body_lines: list[str] = []

    while index < len(lines) - 1:
        line = lines[index]
        if line == block.end:
            return "\n".join(body_lines), index + 1
        if line in RECORD_DELIMITER_LINES or line in TOP_LEVEL_START_LINES or line in TOP_LEVEL_END_LINES:
            raise EmbeddedDelimiterError(
                f"Embedded delimiter {line!r} found inside top-level block {block.name}."
            )
        body_lines.append(line)
        index += 1

    raise MissingTopLevelBlockError(
        f"Missing end delimiter for top-level block {block.name}."
    )


def _parse_required_text_block(body: str, *, block_name: str) -> str:
    if body.strip() == "":
        raise EmptyRequiredBlockError(f"{block_name} must not be empty.")
    if body.strip() == EMPTY_MARKER:
        raise InvalidEmptyMarkerError(f"{block_name} does not allow {EMPTY_MARKER!r}.")
    _assert_no_delimiter_lines(body, context=block_name)
    return body.strip()


def _parse_faq_block(body: str) -> tuple[CanonicalFAQItem, ...]:
    if body == EMPTY_MARKER:
        return ()
    _validate_non_item_empty_marker(body, block_name="FAQ")

    lines = body.split("\n")
    index = 0
    items: list[CanonicalFAQItem] = []

    while index < len(lines):
        if lines[index] != FAQ_ITEM_START:
            raise MalformedFAQItemError(
                "FAQ must contain NONE or one or more valid FAQ items."
            )
        index += 1

        if index >= len(lines) or lines[index] != "Q:":
            raise MalformedFAQItemError("FAQ item must contain exactly one Q: marker.")
        index += 1

        question_lines: list[str] = []
        while index < len(lines):
            line = lines[index]
            if line == "A:":
                index += 1
                break
            if line == FAQ_ITEM_END:
                raise MalformedFAQItemError("FAQ item is missing the A: marker.")
            if line in ALL_DELIMITER_LINES:
                raise EmbeddedDelimiterError(
                    f"Embedded delimiter {line!r} found inside an FAQ question."
                )
            if line == "Q:":
                raise MalformedFAQItemError("FAQ item contains a repeated Q: marker.")
            question_lines.append(line)
            index += 1
        else:
            raise MalformedFAQItemError("FAQ item is missing the A: marker.")

        answer_lines: list[str] = []
        while index < len(lines):
            line = lines[index]
            if line == FAQ_ITEM_END:
                index += 1
                break
            if line in RECORD_DELIMITER_LINES or line in TOP_LEVEL_START_LINES or line in TOP_LEVEL_END_LINES:
                raise EmbeddedDelimiterError(
                    f"Embedded delimiter {line!r} found inside an FAQ answer."
                )
            if line in {FAQ_ITEM_START, KB_ITEM_START, KB_ITEM_END}:
                raise EmbeddedDelimiterError(
                    f"Embedded delimiter {line!r} found inside an FAQ answer."
                )
            if line in {"Q:", "A:"}:
                raise MalformedFAQItemError(
                    "FAQ item contains repeated Q:/A: markers."
                )
            answer_lines.append(line)
            index += 1
        else:
            raise MalformedFAQItemError(
                f"FAQ item is missing the {FAQ_ITEM_END} delimiter."
            )

        question = "\n".join(question_lines).strip()
        answer = "\n".join(answer_lines).strip()
        if question == "":
            raise MalformedFAQItemError("FAQ item question must not be empty.")
        if answer == "":
            raise MalformedFAQItemError("FAQ item answer must not be empty.")

        items.append(CanonicalFAQItem(question=question, answer=answer))

    if not items:
        raise MalformedFAQItemError(
            "FAQ must contain NONE or one or more valid FAQ items."
        )

    return tuple(items)


def _parse_kb_block(body: str) -> tuple[CanonicalKBItem, ...]:
    if body == EMPTY_MARKER:
        return ()
    _validate_non_item_empty_marker(body, block_name="KNOWLEDGE_BASE")

    lines = body.split("\n")
    index = 0
    items: list[CanonicalKBItem] = []

    while index < len(lines):
        if lines[index] != KB_ITEM_START:
            raise MalformedKBItemError(
                "KNOWLEDGE_BASE must contain NONE or one or more valid KB items."
            )
        index += 1

        if index >= len(lines) or lines[index] != "TITLE:":
            raise MalformedKBItemError("KB item must contain exactly one TITLE: marker.")
        index += 1

        title_lines: list[str] = []
        while index < len(lines):
            line = lines[index]
            if line == "BODY:":
                index += 1
                break
            if line == KB_ITEM_END:
                raise MalformedKBItemError("KB item is missing the BODY: marker.")
            if line in ALL_DELIMITER_LINES:
                raise EmbeddedDelimiterError(
                    f"Embedded delimiter {line!r} found inside a KB title."
                )
            if line == "TITLE:":
                raise MalformedKBItemError("KB item contains a repeated TITLE: marker.")
            title_lines.append(line)
            index += 1
        else:
            raise MalformedKBItemError("KB item is missing the BODY: marker.")

        body_lines: list[str] = []
        while index < len(lines):
            line = lines[index]
            if line == KB_ITEM_END:
                index += 1
                break
            if line in RECORD_DELIMITER_LINES or line in TOP_LEVEL_START_LINES or line in TOP_LEVEL_END_LINES:
                raise EmbeddedDelimiterError(
                    f"Embedded delimiter {line!r} found inside a KB body."
                )
            if line in {KB_ITEM_START, FAQ_ITEM_START, FAQ_ITEM_END}:
                raise EmbeddedDelimiterError(
                    f"Embedded delimiter {line!r} found inside a KB body."
                )
            if line in {"TITLE:", "BODY:"}:
                raise MalformedKBItemError(
                    "KB item contains repeated TITLE:/BODY: markers."
                )
            body_lines.append(line)
            index += 1
        else:
            raise MalformedKBItemError(
                f"KB item is missing the {KB_ITEM_END} delimiter."
            )

        title = "\n".join(title_lines).strip()
        item_body = "\n".join(body_lines).strip()
        if title == "":
            raise MalformedKBItemError("KB item title must not be empty.")
        if item_body == "":
            raise MalformedKBItemError("KB item body must not be empty.")

        items.append(CanonicalKBItem(title=title, body=item_body))

    if not items:
        raise MalformedKBItemError(
            "KNOWLEDGE_BASE must contain NONE or one or more valid KB items."
        )

    return tuple(items)


def _validate_non_item_empty_marker(body: str, *, block_name: str) -> None:
    stripped = body.strip()
    if stripped == "":
        raise InvalidEmptyMarkerError(
            f"{block_name} must contain {EMPTY_MARKER!r} or valid items."
        )
    if stripped == EMPTY_MARKER and body != EMPTY_MARKER:
        raise InvalidEmptyMarkerError(
            f"{EMPTY_MARKER!r} must appear alone in the {block_name} block."
        )
    if any(line.strip() == EMPTY_MARKER for line in body.split("\n")):
        raise InvalidEmptyMarkerError(
            f"{EMPTY_MARKER!r} cannot be mixed with other {block_name} content."
        )


def _assert_no_delimiter_lines(body: str, *, context: str) -> None:
    for line in body.split("\n"):
        if line in ALL_DELIMITER_LINES:
            raise EmbeddedDelimiterError(
                f"Embedded delimiter {line!r} found inside {context}."
            )
