from __future__ import annotations

import io
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

import yaml

from cartero import context_state
from cartero.cli import main
from cartero.context_state import (
    DONE_STATUS,
    PENDING_STATUS,
    MasterRefreshGuard,
    get_master_refresh_guard,
    mark_master_refresh_done,
    start_session_tracking,
)


class ContextStateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.context_dir = Path(self.temp_dir.name) / "context"
        self.context_dir.mkdir(parents=True, exist_ok=True)
        self.master_path = self.context_dir / "master-context.md"
        self.state_path = self.context_dir / "system-state.md"
        self.master_path.write_text("# Master context\n", encoding="utf-8")

        self.master_patch = patch.object(context_state, "MASTER_CONTEXT_PATH", self.master_path)
        self.state_patch = patch.object(context_state, "SYSTEM_STATE_PATH", self.state_path)
        self.master_patch.start()
        self.state_patch.start()
        self.addCleanup(self.master_patch.stop)
        self.addCleanup(self.state_patch.stop)

    def test_missing_system_state_is_initialized_as_pending_and_stale(self) -> None:
        guard = get_master_refresh_guard()

        self.assertTrue(self.state_path.exists())
        self.assertTrue(guard.system_state_initialized)
        self.assertTrue(guard.needs_refresh)
        self.assertEqual(guard.master_refresh_status, PENDING_STATUS)

        persisted_state = yaml.safe_load(self.state_path.read_text(encoding="utf-8"))
        self.assertEqual(
            persisted_state["master_timestamp_at_start"],
            guard.current_master_timestamp,
        )
        self.assertEqual(persisted_state["master_refresh_status"], PENDING_STATUS)

    def test_pending_status_with_same_timestamp_stays_stale(self) -> None:
        start_session_tracking()

        guard = get_master_refresh_guard()

        self.assertFalse(guard.timestamp_changed)
        self.assertTrue(guard.needs_refresh)
        self.assertEqual(guard.master_refresh_status, PENDING_STATUS)

    def test_master_timestamp_change_marks_guard_fresh(self) -> None:
        start_session_tracking()
        self._bump_master_timestamp()

        guard = get_master_refresh_guard()

        self.assertTrue(guard.timestamp_changed)
        self.assertTrue(guard.is_fresh)
        self.assertFalse(guard.needs_refresh)

    def test_done_status_marks_guard_fresh_without_timestamp_change(self) -> None:
        start_session_tracking()

        refreshed_guard = mark_master_refresh_done()

        self.assertEqual(refreshed_guard.master_refresh_status, DONE_STATUS)
        self.assertEqual(
            refreshed_guard.master_timestamp_after_refresh,
            refreshed_guard.current_master_timestamp,
        )
        self.assertTrue(refreshed_guard.is_fresh)
        self.assertFalse(refreshed_guard.needs_refresh)

    def _bump_master_timestamp(self) -> None:
        current_stat = self.master_path.stat()
        next_timestamp = current_stat.st_mtime_ns + 1_000_000_000
        os.utime(self.master_path, ns=(current_stat.st_atime_ns, next_timestamp))


class ContextStateCliTests(unittest.TestCase):
    def test_context_state_refresh_done_command_prints_persisted_status(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()

        with patch(
            "cartero.cli.mark_master_refresh_done",
            return_value=_make_guard(
                status=DONE_STATUS,
                after_refresh="2026-04-04T09:00:00+00:00",
            ),
        ), redirect_stdout(stdout), redirect_stderr(stderr):
            exit_code = main(["context-state", "refresh-done"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(stderr.getvalue(), "")
        self.assertIn("Recorded master context refresh.", stdout.getvalue())
        self.assertIn("master_refresh_status: done", stdout.getvalue())


def _make_guard(
    *,
    status: str,
    current: str = "2026-04-04T09:00:00+00:00",
    at_start: str = "2026-04-04T08:00:00+00:00",
    after_refresh: str | None = None,
) -> MasterRefreshGuard:
    return MasterRefreshGuard(
        current_master_timestamp=current,
        master_timestamp_at_start=at_start,
        master_timestamp_after_refresh=after_refresh,
        master_refresh_status=status,
        system_state_exists=True,
        system_state_initialized=False,
    )
