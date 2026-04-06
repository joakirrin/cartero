from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import re

SESSION_BLOCK_START = "<<<CARTERO_SESSION_V1>>>"
SESSION_BLOCK_END = "<<<END_CARTERO_SESSION_V1>>>"
SESSION_NOTES_PATH = Path(".cartero") / "session-notes.md"
SESSION_SUMMARY_DIR = Path(".cartero") / "session-summary"
SESSION_ARCHIVE_DIR = Path(".cartero") / "archive"
REQUIRED_SESSION_FIELDS = (
    "decisions",
    "tradeoffs",
    "risks_open_issues",
)
SESSION_NOTE_SEPARATOR = "\n\n---\n\n"
FIELD_LINE_PATTERN = re.compile(
    r"^(decisions|tradeoffs|risks_open_issues):[ \t]*(?P<value>\S.*)$",
    re.MULTILINE,
)


@dataclass(frozen=True)
class ParsedSessionSummary:
    decisions: str
    tradeoffs: str
    risks_open_issues: str

    def as_mapping(self) -> dict[str, str]:
        return {
            "decisions": self.decisions,
            "tradeoffs": self.tradeoffs,
            "risks_open_issues": self.risks_open_issues,
        }


@dataclass(frozen=True)
class SessionImportArtifacts:
    raw_latest_path: Path
    raw_archive_path: Path
    normalized_latest_path: Path | None
    normalized_archive_path: Path | None
    session_notes_path: Path | None


class SessionSummaryParseError(ValueError):
    pass


class SessionSummaryImportError(SessionSummaryParseError):
    def __init__(
        self,
        message: str,
        *,
        raw_latest_path: Path,
        raw_archive_path: Path,
    ) -> None:
        super().__init__(message)
        self.raw_latest_path = raw_latest_path
        self.raw_archive_path = raw_archive_path


def import_session_summary(raw_block: str) -> SessionImportArtifacts:
    imported_at = get_current_time()
    raw_latest_path, raw_archive_path = persist_raw_session_summary(
        raw_block,
        imported_at=imported_at,
    )
    try:
        parsed = parse_session_summary_block(raw_block)
    except SessionSummaryParseError as exc:
        raise SessionSummaryImportError(
            str(exc),
            raw_latest_path=raw_latest_path,
            raw_archive_path=raw_archive_path,
        ) from exc
    normalized_text = render_normalized_session_summary(parsed)
    normalized_latest_path, normalized_archive_path = persist_normalized_session_summary(
        normalized_text,
        imported_at=imported_at,
    )
    session_notes_path = append_normalized_session_note(
        parsed,
        imported_at=imported_at,
    )
    return SessionImportArtifacts(
        raw_latest_path=raw_latest_path,
        raw_archive_path=raw_archive_path,
        normalized_latest_path=normalized_latest_path,
        normalized_archive_path=normalized_archive_path,
        session_notes_path=session_notes_path,
    )


def parse_session_summary_block(raw_block: str) -> ParsedSessionSummary:
    stripped_block = raw_block.strip()
    if not stripped_block:
        raise SessionSummaryParseError("Session summary block is empty.")

    block_pattern = re.compile(
        rf"^{re.escape(SESSION_BLOCK_START)}\n(?P<body>.*)\n{re.escape(SESSION_BLOCK_END)}$",
        re.DOTALL,
    )
    match = block_pattern.fullmatch(stripped_block)
    if match is None:
        raise SessionSummaryParseError(
            "Invalid Cartero session block. Expected exact "
            f"{SESSION_BLOCK_START} ... {SESSION_BLOCK_END} delimiters."
        )

    field_values: dict[str, str] = {}
    for raw_line in match.group("body").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        field_match = re.fullmatch(
            r"(decisions|tradeoffs|risks_open_issues):[ \t]*(?P<value>\S.*)",
            line,
        )
        if field_match is None:
            raise SessionSummaryParseError(
                f"Invalid session summary line: {raw_line!r}."
            )
        field_name = field_match.group(1)
        if field_name in field_values:
            raise SessionSummaryParseError(
                f"Duplicate session summary field: {field_name}."
            )
        field_values[field_name] = field_match.group("value").strip()

    missing_fields = [
        field_name
        for field_name in REQUIRED_SESSION_FIELDS
        if not field_values.get(field_name, "").strip()
    ]
    if missing_fields:
        raise SessionSummaryParseError(
            "Missing required session summary field(s): "
            + ", ".join(missing_fields)
            + "."
        )

    return ParsedSessionSummary(
        decisions=field_values["decisions"],
        tradeoffs=field_values["tradeoffs"],
        risks_open_issues=field_values["risks_open_issues"],
    )


def render_normalized_session_summary(summary: ParsedSessionSummary) -> str:
    return "\n".join(
        f"{field_name}: {field_value}"
        for field_name, field_value in summary.as_mapping().items()
    ) + "\n"


def persist_raw_session_summary(
    raw_block: str,
    *,
    imported_at: datetime,
) -> tuple[Path, Path]:
    latest_path = SESSION_SUMMARY_DIR / "raw-latest.md"
    archive_path = SESSION_ARCHIVE_DIR / f"session-summary-{_format_archive_stamp(imported_at)}-raw.md"
    _write_text(latest_path, raw_block)
    _write_text(archive_path, raw_block)
    return latest_path, archive_path


def persist_normalized_session_summary(
    normalized_text: str,
    *,
    imported_at: datetime,
) -> tuple[Path, Path]:
    latest_path = SESSION_SUMMARY_DIR / "normalized-latest.md"
    archive_path = (
        SESSION_ARCHIVE_DIR
        / f"session-summary-{_format_archive_stamp(imported_at)}-normalized.md"
    )
    _write_text(latest_path, normalized_text)
    _write_text(archive_path, normalized_text)
    return latest_path, archive_path


def append_normalized_session_note(
    summary: ParsedSessionSummary,
    *,
    imported_at: datetime,
) -> Path:
    note_text = "\n".join(
        [
            f"[LLM] {_format_display_timestamp(imported_at)}",
            *[
                f"{field_name}: {field_value}"
                for field_name, field_value in summary.as_mapping().items()
            ],
        ]
    )

    try:
        SESSION_NOTES_PATH.parent.mkdir(parents=True, exist_ok=True)
        if SESSION_NOTES_PATH.exists():
            existing_content = SESSION_NOTES_PATH.read_text(encoding="utf-8").strip()
            if existing_content:
                rendered_content = (
                    f"{existing_content}{SESSION_NOTE_SEPARATOR}{note_text}\n"
                )
            else:
                rendered_content = f"{note_text}\n"
        else:
            rendered_content = f"{note_text}\n"
        SESSION_NOTES_PATH.write_text(rendered_content, encoding="utf-8")
    except OSError as exc:
        raise ValueError(
            f"Unable to write session notes to {SESSION_NOTES_PATH}: {exc}"
        ) from exc
    return SESSION_NOTES_PATH


def get_session_field_status(note_text: str | None) -> dict[str, bool]:
    if not note_text:
        return {field_name: False for field_name in REQUIRED_SESSION_FIELDS}

    present_fields = {
        match.group(1)
        for match in FIELD_LINE_PATTERN.finditer(note_text)
    }
    return {
        field_name: field_name in present_fields
        for field_name in REQUIRED_SESSION_FIELDS
    }


def read_session_notes() -> str | None:
    if not SESSION_NOTES_PATH.exists():
        return None
    try:
        note_text = SESSION_NOTES_PATH.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise ValueError(
            f"Unable to read session notes from {SESSION_NOTES_PATH}: {exc}"
        ) from exc
    return note_text or None


def archive_session_notes(*, archived_at: datetime | None = None) -> Path | None:
    if not SESSION_NOTES_PATH.exists():
        return None

    if archived_at is None:
        archived_at = get_current_time()
    archive_path = SESSION_ARCHIVE_DIR / f"session-notes-{_format_archive_stamp(archived_at)}.md"

    try:
        archive_path.parent.mkdir(parents=True, exist_ok=True)
        if archive_path.exists():
            raise ValueError(f"Archive target already exists: {archive_path}")
        SESSION_NOTES_PATH.rename(archive_path)
    except OSError as exc:
        raise ValueError(
            f"Unable to archive session notes from {SESSION_NOTES_PATH} to {archive_path}: {exc}"
        ) from exc

    return archive_path


def get_current_time() -> datetime:
    return datetime.now().astimezone()


def _format_archive_stamp(value: datetime) -> str:
    return value.strftime("%Y-%m-%d-%H%M%S")


def _format_display_timestamp(value: datetime) -> str:
    return value.isoformat(timespec="seconds")


def _write_text(path: Path, content: str) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"Unable to write {path}: {exc}") from exc
