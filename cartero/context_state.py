from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

MASTER_CONTEXT_PATH = Path("context/master-context.md")
SYSTEM_STATE_PATH = Path("context/system-state.md")
PENDING_STATUS = "pending"
DONE_STATUS = "done"


@dataclass(frozen=True)
class MasterRefreshGuard:
    current_master_timestamp: str
    master_timestamp_at_start: str | None
    master_timestamp_after_refresh: str | None
    master_refresh_status: str
    system_state_exists: bool
    system_state_initialized: bool

    @property
    def timestamp_changed(self) -> bool:
        return (
            self.master_timestamp_at_start is not None
            and self.current_master_timestamp != self.master_timestamp_at_start
        )

    @property
    def is_fresh(self) -> bool:
        return self.master_refresh_status == DONE_STATUS or self.timestamp_changed

    @property
    def needs_refresh(self) -> bool:
        return not self.is_fresh


def get_master_refresh_guard() -> MasterRefreshGuard:
    current_timestamp = get_master_context_timestamp()
    state, state_exists = _load_system_state()
    initialized = False

    if not _as_optional_str(state.get("master_timestamp_at_start")):
        state["master_timestamp_at_start"] = current_timestamp
        initialized = True

    normalized_status = _normalize_status(state.get("master_refresh_status"))
    if state.get("master_refresh_status") != normalized_status:
        state["master_refresh_status"] = normalized_status
        initialized = True

    if initialized or not state_exists:
        _write_system_state(state)

    return MasterRefreshGuard(
        current_master_timestamp=current_timestamp,
        master_timestamp_at_start=_as_optional_str(state.get("master_timestamp_at_start")),
        master_timestamp_after_refresh=_as_optional_str(
            state.get("master_timestamp_after_refresh")
        ),
        master_refresh_status=_normalize_status(state.get("master_refresh_status")),
        system_state_exists=state_exists,
        system_state_initialized=initialized or not state_exists,
    )


def mark_master_refresh_done() -> MasterRefreshGuard:
    current_timestamp = get_master_context_timestamp()
    state, _ = _load_system_state()
    state["master_timestamp_at_start"] = _as_optional_str(
        state.get("master_timestamp_at_start")
    ) or current_timestamp
    state["master_timestamp_after_refresh"] = current_timestamp
    state["master_refresh_status"] = DONE_STATUS
    _write_system_state(state)
    return get_master_refresh_guard()


def start_session_tracking() -> MasterRefreshGuard:
    current_timestamp = get_master_context_timestamp()
    state, _ = _load_system_state()
    state["master_timestamp_at_start"] = current_timestamp
    state["master_refresh_status"] = PENDING_STATUS
    state.pop("master_timestamp_after_refresh", None)
    _write_system_state(state)
    return get_master_refresh_guard()


def get_master_context_timestamp() -> str:
    if not MASTER_CONTEXT_PATH.exists():
        raise ValueError(
            f"Master context not found at {MASTER_CONTEXT_PATH}. "
            "Run this command from the root of the Cartero repository."
        )

    try:
        stat_result = MASTER_CONTEXT_PATH.stat()
    except OSError as exc:
        raise ValueError(
            f"Unable to read timestamp from {MASTER_CONTEXT_PATH}: {exc}"
        ) from exc

    return datetime.fromtimestamp(
        stat_result.st_mtime_ns / 1_000_000_000,
        tz=timezone.utc,
    ).isoformat()


def _load_system_state() -> tuple[dict[str, Any], bool]:
    if not SYSTEM_STATE_PATH.exists():
        return {}, False

    try:
        raw_text = SYSTEM_STATE_PATH.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"Unable to read {SYSTEM_STATE_PATH}: {exc}") from exc

    try:
        loaded = yaml.safe_load(raw_text) or {}
    except yaml.YAMLError as exc:
        raise ValueError(f"Invalid YAML in {SYSTEM_STATE_PATH}: {exc}") from exc

    if not isinstance(loaded, dict):
        raise ValueError(f"{SYSTEM_STATE_PATH} must contain a YAML mapping.")

    return dict(loaded), True


def _write_system_state(state: dict[str, Any]) -> None:
    try:
        SYSTEM_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        SYSTEM_STATE_PATH.write_text(
            yaml.safe_dump(state, sort_keys=False),
            encoding="utf-8",
        )
    except OSError as exc:
        raise ValueError(f"Unable to write {SYSTEM_STATE_PATH}: {exc}") from exc


def _normalize_status(raw_status: object) -> str:
    if isinstance(raw_status, str) and raw_status.strip().lower() == DONE_STATUS:
        return DONE_STATUS
    return PENDING_STATUS


def _as_optional_str(value: object) -> str | None:
    if isinstance(value, str):
        stripped = value.strip()
        if stripped:
            return stripped
    return None
