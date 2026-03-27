from __future__ import annotations

import re
import subprocess


class GitError(Exception):
    pass


def get_changed_files() -> list[str]:
    result = _run_git_command(["git", "status", "--short"])
    if not result.stdout:
        return []

    changed_files: list[str] = []
    for line in result.stdout.splitlines():
        if len(line) < 4:
            continue
        changed_files.append(line[3:])
    return changed_files


def get_diff() -> str:
    if _has_head_commit():
        result = _run_git_command(["git", "diff", "HEAD"])
    else:
        result = _run_git_command(["git", "diff", "--cached"])
    return result.stdout


def stage_files(paths: list[str]) -> None:
    if not paths:
        return
    _run_git_command(["git", "add", "--", *paths])


def commit(message: str, body: str | None = None) -> str:
    command = ["git", "commit", "-m", message]
    if body is not None:
        command.extend(["-m", body])

    result = _run_git_command(command)
    output = "\n".join(part for part in (result.stdout, result.stderr) if part).strip()
    match = re.search(r"\[[^\]]*\b([0-9a-f]{7})\b[^\]]*\]", output)
    if match is None:
        raise GitError("Unable to determine commit hash from git commit output")
    return match.group(1)


def _has_head_commit() -> bool:
    result = _run_git_command(
        ["git", "rev-parse", "--verify", "HEAD"],
        allow_no_head=True,
    )
    return result.returncode == 0


def _run_git_command(
    command: list[str],
    *,
    allow_no_head: bool = False,
) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError as exc:
        raise GitError("git command not found") from exc

    if result.returncode == 0:
        return result

    stderr = (result.stderr or "").strip()
    if allow_no_head and _is_missing_head_error(stderr):
        return result

    raise GitError(stderr or f"git command failed with exit code {result.returncode}")


def _is_missing_head_error(stderr: str) -> bool:
    return "Needed a single revision" in stderr or "unknown revision or path not in the working tree" in stderr
