from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path
from typing import Iterable, Sequence

import yaml
from rich.console import Console, Group
from rich.panel import Panel
from rich.text import Text

from cartero.context_state import (
    MasterRefreshGuard,
    get_master_refresh_guard,
    mark_master_refresh_done,
    start_session_tracking,
)
from cartero.executor import execute_actions
from cartero.generator import (
    SummaryGenerationResult,
    generate_context_recap,
    generate_summary_result_from_diff,
)
from cartero.git import (
    GitError,
    commit as git_commit,
    get_changed_files,
    get_diff,
    stage_files,
)
from cartero.llm import (
    LLMCallError,
    LLMConfigError,
    generate_changelog,
    generate_session_brief,
)
from cartero.parser import ParseError, load_summary
from cartero.simulator import SimulatedAction, simulate_actions
from cartero.validator import ALLOWED_REPOS, Change, ValidationError, validate_summary

VALID_MODES = {"dry-run", "apply"}
ACTION_STYLES = {
    "write": "blue",
    "delete": "red",
    "mkdir": "yellow",
}
INTERACTIVE_MAIN_OPTIONS = (
    ("1", "Explain my changes"),
    ("2", "Generate summary"),
    ("3", "Generate full update"),
    ("4", "Commit changes"),
    ("5", "Exit"),
)
INTERACTIVE_CONTEXT_OPTIONS = (
    ("1", "No"),
    ("2", "Paste notes now"),
    ("3", "Use a context file"),
)
INTERACTIVE_NEXT_OPTIONS = (
    ("1", "Commit"),
    ("2", "Regenerate"),
    ("3", "Exit"),
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cartero",
        description="Validate Cartero summaries or generate them from a diff.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser(
        "run",
        prog="cartero",
        help="Validate an actions YAML file and print a repo plan.",
    )
    mode_group = run_parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview the execution plan without making changes.",
    )
    mode_group.add_argument(
        "--apply",
        action="store_true",
        help="Apply the changes described in the summary file.",
    )
    run_parser.add_argument("summary", help="Path to the YAML summary file.")
    run_parser.set_defaults(handler=handle_run)

    generate_parser = subparsers.add_parser(
        "generate",
        prog="cartero generate",
        help="Generate a Cartero YAML summary from a diff.",
    )
    generate_diff_source = generate_parser.add_mutually_exclusive_group()
    generate_diff_source.add_argument(
        "--diff-file",
        metavar="PATH",
        help="Path to a file containing the diff.",
    )
    generate_diff_source.add_argument(
        "--stdin",
        action="store_true",
        help="Read the diff from stdin instead of detecting it from git.",
    )
    generate_parser.add_argument(
        "--context-file",
        metavar="PATH",
        help="Optional path to raw context. Cartero will compress it before generation.",
    )
    generate_parser.set_defaults(handler=handle_generate)

    context_parser = subparsers.add_parser(
        "context",
        prog="cartero context",
        help="Compress raw notes or conversation context into a structured recap.",
    )
    context_parser.add_argument(
        "--context-file",
        metavar="PATH",
        help="Path to a file containing raw context. Reads from stdin when omitted.",
    )
    context_parser.set_defaults(handler=handle_context)

    context_state_parser = subparsers.add_parser(
        "context-state",
        prog="cartero context-state",
        help="Inspect or update the persisted master-context refresh state.",
    )
    context_state_subparsers = context_state_parser.add_subparsers(
        dest="context_state_command",
        required=True,
    )

    refresh_done_parser = context_state_subparsers.add_parser(
        "refresh-done",
        prog="cartero context-state refresh-done",
        help="Mark the master context refresh as completed for the current session.",
    )
    refresh_done_parser.set_defaults(handler=handle_context_state_refresh_done)

    changelog_parser = subparsers.add_parser(
        "changelog",
        prog="cartero changelog",
        help="Generate a product-style changelog entry from a git diff.",
    )
    changelog_diff_source = changelog_parser.add_mutually_exclusive_group()
    changelog_diff_source.add_argument(
        "--diff-file",
        metavar="PATH",
        help="Path to a file containing the diff.",
    )
    changelog_diff_source.add_argument(
        "--stdin",
        action="store_true",
        help="Read the diff from stdin instead of detecting it from git.",
    )
    changelog_parser.add_argument(
        "--context-file",
        metavar="PATH",
        help="Optional path to raw context. Cartero will compress it before generation.",
    )
    changelog_parser.set_defaults(handler=handle_changelog)

    commit_parser = subparsers.add_parser(
        "commit",
        prog="cartero commit",
        help="Stage selected files, generate a summary, and create a git commit.",
    )
    commit_parser.add_argument(
        "--context-file",
        metavar="PATH",
        help="Optional path to raw context. Cartero will compress it before generation.",
    )
    commit_parser.set_defaults(handler=handle_commit)

    session_parser = subparsers.add_parser(
        "session",
        prog="cartero session",
        help="Generate a session brief from the master context.",
    )
    session_parser.set_defaults(handler=handle_session)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    raw_args = list(sys.argv[1:] if argv is None else argv)
    console = Console()
    error_console = Console(stderr=True)
    if not raw_args:
        return handle_interactive(console, error_console)
    args = build_parser().parse_args(_normalize_argv(raw_args))
    return args.handler(args, console, error_console)


def handle_run(args: argparse.Namespace, console: Console, error_console: Console) -> int:
    mode = "apply" if args.apply else "dry-run"
    try:
        raw_summary = load_summary(args.summary)
        summary = validate_summary(raw_summary)
    except (ParseError, ValidationError) as exc:
        error_console.print(Text.assemble(("error: ", "red"), (str(exc),)))
        return 2
    render_plan(Path(args.summary), summary.actions, mode, console=console)
    return 0


def handle_generate(
    args: argparse.Namespace, console: Console, error_console: Console
) -> int:
    try:
        diff_text = _resolve_generate_diff(args)
        raw_context = _read_optional_text_input(_get_arg_value(args, "context_file"))
    except NoDiffError as exc:
        console.print(str(exc))
        return 0
    except GitError as exc:
        error_console.print(Text.assemble(("error: ", "red"), (str(exc),)))
        return 2
    except ValueError as exc:
        error_console.print(Text.assemble(("error: ", "red"), (str(exc),)))
        return 2

    exit_code, result = _generate_summary_result(
        diff_text,
        raw_context,
        console=console,
        error_console=error_console,
    )
    if exit_code != 0 or result is None:
        return exit_code

    console.print(result.yaml_text, markup=False, end="")
    return 0


def handle_changelog(
    args: argparse.Namespace, console: Console, error_console: Console
) -> int:
    try:
        diff_text = _resolve_generate_diff(args)
        raw_context = _read_optional_text_input(_get_arg_value(args, "context_file"))
    except NoDiffError as exc:
        console.print(str(exc))
        return 0
    except GitError as exc:
        error_console.print(Text.assemble(("error: ", "red"), (str(exc),)))
        return 2
    except ValueError as exc:
        error_console.print(Text.assemble(("error: ", "red"), (str(exc),)))
        return 2

    try:
        context_recap = None
        if raw_context:
            context_recap = generate_context_recap(raw_context)
        result = generate_changelog(diff_text, context_recap=context_recap)
    except (LLMConfigError, LLMCallError) as exc:
        error_console.print(Text.assemble(("error: ", "red"), (str(exc),)))
        return 2

    return 0


def handle_session(
    args: argparse.Namespace, console: Console, error_console: Console
) -> int:
    try:
        guard = get_master_refresh_guard()
    except ValueError as exc:
        error_console.print(Text.assemble(("error: ", "red"), (str(exc),)))
        return 2

    if guard.needs_refresh:
        _print_master_context_warning(
            error_console,
            guard,
            command_name="cartero session",
            blocking=True,
        )
        return 2

    try:
        generate_session_brief()
        start_session_tracking()
    except (LLMConfigError, LLMCallError, ValueError) as exc:
        error_console.print(Text.assemble(("error: ", "red"), (str(exc),)))
        return 2
    return 0


def handle_context(
    args: argparse.Namespace, console: Console, error_console: Console
) -> int:
    try:
        raw_context = _read_text_input(_get_arg_value(args, "context_file"))
        recap = generate_context_recap(raw_context)
    except (LLMConfigError, LLMCallError, ValueError) as exc:
        error_console.print(Text.assemble(("error: ", "red"), (str(exc),)))
        return 2
    console.print(recap, markup=False, end="")
    return 0


def handle_context_state_refresh_done(
    args: argparse.Namespace, console: Console, error_console: Console
) -> int:
    del args
    try:
        guard = mark_master_refresh_done()
    except ValueError as exc:
        error_console.print(Text.assemble(("error: ", "red"), (str(exc),)))
        return 2

    console.print("Recorded master context refresh.")
    console.print(f"master_timestamp_at_start: {guard.master_timestamp_at_start}")
    console.print(
        f"master_timestamp_after_refresh: {guard.master_timestamp_after_refresh}"
    )
    console.print(f"master_refresh_status: {guard.master_refresh_status}")
    return 0


def handle_commit(
    args: argparse.Namespace, console: Console, error_console: Console
) -> int:
    return _run_commit_flow(
        console,
        error_console,
        context_file=_get_arg_value(args, "context_file"),
    )


def handle_interactive(console: Console, error_console: Console) -> int:
    try:
        changed_files = get_changed_files()
        diff_text = get_diff()
    except GitError as exc:
        error_console.print(Text.assemble(("error: ", "red"), (str(exc),)))
        return 2

    while True:
        _print_interactive_change_summary(changed_files, diff_text, console)

        action = _prompt_choice(
            console,
            "What do you want to do?",
            INTERACTIVE_MAIN_OPTIONS,
        )
        if action is None or action == "5":
            return 0

        if action == "4":
            raw_context = _capture_interactive_context(console, error_console)
            return _run_commit_flow(
                console,
                error_console,
                raw_context=raw_context,
            )

        raw_context: str | None = None
        context_prompted = False

        if action in {"1", "2"}:
            raw_context = _capture_interactive_context(console, error_console)
            context_prompted = True
            exit_code = _run_interactive_generation_action(
                action,
                diff_text,
                raw_context,
                console=console,
                error_console=error_console,
            )
            if exit_code != 0:
                return exit_code
        else:
            console.print("Full update is not implemented yet.")

        next_action = _prompt_choice(
            console,
            "What next?",
            INTERACTIVE_NEXT_OPTIONS,
        )
        if next_action is None or next_action == "3":
            return 0
        if next_action == "2":
            try:
                changed_files = get_changed_files()
                diff_text = get_diff()
            except GitError as exc:
                error_console.print(Text.assemble(("error: ", "red"), (str(exc),)))
                return 2
            continue
        if not context_prompted:
            raw_context = _capture_interactive_context(console, error_console)
        return _run_commit_flow(
            console,
            error_console,
            raw_context=raw_context,
        )


def _run_commit_flow(
    console: Console,
    error_console: Console,
    *,
    raw_context: str | None = None,
    context_file: object | None = None,
) -> int:
    try:
        changed_files = get_changed_files()
    except GitError as exc:
        error_console.print(Text.assemble(("error: ", "red"), (str(exc),)))
        return 2

    if not changed_files:
        console.print("Nothing to commit. Working tree clean.")
        return 0

    try:
        guard = get_master_refresh_guard()
    except ValueError as exc:
        error_console.print(Text.assemble(("error: ", "red"), (str(exc),)))
        return 2

    if guard.needs_refresh:
        _print_master_context_warning(
            error_console,
            guard,
            command_name="cartero commit",
            blocking=False,
        )
        console.print("Continue with stale master context? [y/N]: ", end="")
        stale_confirmation = input().strip()
        if stale_confirmation.lower() not in {"y", "yes"}:
            console.print("Aborted.")
            return 0

    console.print("Changed files:")
    for index, path in enumerate(changed_files, start=1):
        console.print(f"{index}. {path}")

    console.print('Stage files (numbers separated by spaces, or "a" for all): ', end="")
    selection = input().strip()
    selected_paths = _parse_selected_paths(selection, changed_files)
    if selected_paths is None:
        error_console.print(Text.assemble(("error: ", "red"), ("Invalid file selection",)))
        return 2

    try:
        stage_files(selected_paths)
    except GitError as exc:
        error_console.print(Text.assemble(("error: ", "red"), (str(exc),)))
        return 2

    try:
        diff_text = get_diff()
    except GitError as exc:
        error_console.print(Text.assemble(("error: ", "red"), (str(exc),)))
        return 2

    try:
        if raw_context is None:
            raw_context = _read_optional_text_input(_coerce_optional_str(context_file))
        with console.status("Generating commit summary…"):
            exit_code, result = _generate_summary_result(
                diff_text,
                raw_context,
                console=console,
                error_console=error_console,
            )
    except ValueError as exc:
        error_console.print(Text.assemble(("error: ", "red"), (str(exc),)))
        return 2

    if exit_code != 0 or result is None:
        return exit_code

    console.print(result.yaml_text, markup=False)
    console.print("Commit with this summary? [y/N]: ", end="")
    confirmation = input().strip()

    if confirmation.lower() not in {"y", "yes"}:
        console.print("Aborted.")
        return 0

    try:
        data = yaml.safe_load(result.yaml_text)
    except yaml.YAMLError as exc:
        error_console.print(Text.assemble(("error: ", "red"), (str(exc),)))
        return 2

    subject = ""
    body = None
    if isinstance(data, dict):
        subject = str(data.get("summary", "")).strip()
        body_text = str(data.get("reason", "")).strip()
        body = body_text or None

    if not subject:
        subject = "chore: update files"

    try:
        commit_hash = git_commit(subject, body)
    except GitError as exc:
        error_console.print(Text.assemble(("error: ", "red"), (str(exc),)))
        return 2

    console.print(f"✓ Committed: {commit_hash}")
    return 0


def render_plan(
    summary_path: Path,
    changes: Iterable[Change],
    mode: str,
    *,
    console: Console | None = None,
) -> Group:
    if mode not in VALID_MODES:
        raise ValueError(f"Unsupported mode: {mode}")

    if console is None:
        console = Console()

    change_list = tuple(changes)
    grouped: dict[str, list[SimulatedAction]] = defaultdict(list)
    total_changes = 0

    for simulated_action in simulate_actions(change_list):
        grouped[simulated_action.repo].append(simulated_action)
        total_changes += 1

    renderables = [
        Panel.fit(
            Group(
                Text(f"Cartero {mode} plan"),
                Text(f"Summary file: {summary_path}"),
                Text(f"Mode: {_describe_mode(mode)}"),
                Text(f"Validated actions: {total_changes}"),
            ),
            title="Cartero",
        )
    ]

    for repo in ALLOWED_REPOS:
        repo_changes = grouped.get(repo)
        if not repo_changes:
            continue
        action_label = f"{repo} ({len(repo_changes)} action{'s' if len(repo_changes) != 1 else ''})"
        repo_lines: list[Text] = [Text(action_label)]
        for simulated_action in repo_changes:
            repo_lines.extend(_render_simulated_action(simulated_action))
        renderables.append(Panel(Group(*repo_lines), title=repo))

    plan = Group(*renderables)
    console.print(plan)

    if mode == "dry-run":
        console.print(_build_status_line())
        return plan

    console.rule("Simulated execution")
    execute_actions(change_list, console=console)
    return plan


def _describe_mode(mode: str) -> str:
    if mode == "apply":
        return "apply"
    return "dry-run"


def _normalize_argv(argv: Sequence[str] | None) -> list[str]:
    args = list(sys.argv[1:] if argv is None else argv)
    SUBCOMMANDS = {
        "run",
        "generate",
        "context",
        "context-state",
        "commit",
        "changelog",
        "session",
    }
    if args and args[0] in SUBCOMMANDS:
        return args
    return ["run", *args]


def _read_diff_text(diff_file: str | None) -> str:
    return _read_text_input(diff_file)


def _resolve_generate_diff(args: argparse.Namespace) -> str:
    diff_file = args.diff_file
    if diff_file is not None:
        return _read_diff_text(diff_file)
    if bool(_get_arg_value(args, "stdin")):
        return _read_text_input(None)

    diff_text = get_diff()
    if diff_text.strip():
        return diff_text
    raise NoDiffError("No changes detected. You can paste a diff or make changes first.")


def _read_text_input(path: str | None) -> str:
    if path is None:
        return sys.stdin.read()
    try:
        return Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"Unable to read input file {path}: {exc}") from exc


def _read_optional_text_input(path: str | None) -> str | None:
    if path is None:
        return None
    return _read_text_input(path)


def _get_arg_value(args: argparse.Namespace, name: str) -> object | None:
    return vars(args).get(name)


def _generate_summary_result(
    diff_text: str,
    raw_context: str | None,
    *,
    console: Console,
    error_console: Console,
) -> tuple[int, SummaryGenerationResult | None]:
    try:
        result = generate_summary_result_from_diff(diff_text, raw_context=raw_context)
    except (LLMConfigError, LLMCallError, ValueError) as exc:
        error_console.print(Text.assemble(("error: ", "red"), (str(exc),)))
        return 2, None

    if result.warning_message:
        error_console.print(Text.assemble(("warning: ", "yellow"), (result.warning_message,)))

    return 0, result


def _print_master_context_warning(
    console: Console,
    guard: MasterRefreshGuard,
    *,
    command_name: str,
    blocking: bool,
) -> None:
    details: list[str] = []
    if guard.system_state_initialized and not guard.system_state_exists:
        details.append(
            "context/system-state.md was missing, so Cartero initialized it conservatively."
        )
    if guard.master_timestamp_at_start is not None:
        details.append(f"master_timestamp_at_start: {guard.master_timestamp_at_start}")
    details.append(f"current_master_timestamp: {guard.current_master_timestamp}")
    details.append(f"master_refresh_status: {guard.master_refresh_status}")

    if blocking:
        message = (
            f"{command_name} was blocked because context/master-context.md was not "
            "refreshed for this session. The session brief can be outdated."
        )
    else:
        message = (
            f"{command_name} is using a stale context/master-context.md. "
            "The commit summary can be outdated."
        )

    guidance = (
        "Update context/master-context.md, then run "
        "`cartero context-state refresh-done`."
    )
    console.print(Text.assemble(("warning: ", "yellow"), (message,)))
    console.print("\n".join([*details, guidance]))


def _print_interactive_change_summary(
    changed_files: Sequence[str],
    diff_text: str,
    console: Console,
) -> None:
    if not changed_files:
        console.print("No git changes detected.")
        return

    label = "file" if len(changed_files) == 1 else "files"
    console.print(f"I found changes in {len(changed_files)} {label}.")
    for path in changed_files[:5]:
        console.print(f"- {path}")
    if len(changed_files) > 5:
        console.print(f"- ... {len(changed_files) - 5} more")
    if not diff_text.strip():
        console.print("There is no diff to summarize yet. New files may need staging first.")


def _run_interactive_generation_action(
    action: str,
    diff_text: str,
    raw_context: str | None,
    *,
    console: Console,
    error_console: Console,
) -> int:
    if not diff_text.strip():
        console.print("No changes detected. You can paste a diff or make changes first.")
        return 0

    exit_code, result = _generate_summary_result(
        diff_text,
        raw_context,
        console=console,
        error_console=error_console,
    )
    if exit_code != 0 or result is None:
        return exit_code

    if action == "1":
        _print_explanation(result.yaml_text, console)
        return 0

    console.print(result.yaml_text, markup=False, end="")
    return 0


def _print_explanation(yaml_text: str, console: Console) -> None:
    console.print("Explanation:")
    try:
        data = yaml.safe_load(yaml_text)
    except yaml.YAMLError:
        console.print(yaml_text, markup=False, end="")
        return

    if not isinstance(data, dict):
        console.print(yaml_text, markup=False, end="")
        return

    summary = str(data.get("summary", "")).strip()
    reason = str(data.get("reason", "")).strip()
    impact = str(data.get("impact", "")).strip()

    if summary:
        console.print(summary)
    if reason:
        console.print(f"Why: {reason}")
    if impact:
        console.print(f"Impact: {impact}")


def _capture_interactive_context(console: Console, error_console: Console) -> str | None:
    while True:
        choice = _prompt_choice(
            console,
            "Add context?",
            INTERACTIVE_CONTEXT_OPTIONS,
        )
        if choice is None or choice == "1":
            return None
        if choice == "2":
            return _read_pasted_context(console)

        console.print("Context file path: ", end="")
        path = input().strip()
        if not path:
            error_console.print(Text.assemble(("error: ", "red"), ("Invalid context file",)))
            continue
        try:
            return _read_text_input(path)
        except ValueError as exc:
            error_console.print(Text.assemble(("error: ", "red"), (str(exc),)))


def _read_pasted_context(console: Console) -> str | None:
    console.print("Paste notes. Finish with a line that only says END.")
    lines: list[str] = []
    while True:
        try:
            line = input()
        except EOFError:
            break
        if line == "END":
            break
        lines.append(line)

    content = "\n".join(lines).strip()
    return content or None


def _prompt_choice(
    console: Console,
    prompt: str,
    options: Sequence[tuple[str, str]],
) -> str | None:
    option_map = dict(options)
    while True:
        console.print(prompt)
        for key, label in options:
            console.print(f"{key}. {label}")
        console.print("> ", end="")
        try:
            choice = input().strip()
        except EOFError:
            return None
        if choice in option_map:
            return choice
        console.print("Choose a number from the list.")


def _parse_selected_paths(selection: str, changed_files: Sequence[str]) -> list[str] | None:
    if not selection:
        return None

    if selection.lower() in {"a", "all"}:
        return list(changed_files)

    selected_paths: list[str] = []
    seen_indexes: set[int] = set()
    try:
        for token in selection.split():
            selected_index = int(token)
            if selected_index < 1 or selected_index > len(changed_files):
                raise ValueError
            if selected_index in seen_indexes:
                continue
            seen_indexes.add(selected_index)
            selected_paths.append(changed_files[selected_index - 1])
    except ValueError:
        return None

    if not selected_paths:
        return None
    return selected_paths


def _coerce_optional_str(value: object | None) -> str | None:
    if value is None or isinstance(value, str):
        return value
    return str(value)


class NoDiffError(ValueError):
    pass


def _build_status_line() -> Text:
    return Text("No file or git changes were made.", style="green")


def _render_simulated_action(simulated_action: SimulatedAction) -> list[Text]:
    style = ACTION_STYLES[_get_action_type(simulated_action)]
    lines = [Text(f"- {simulated_action.summary}", style=style)]

    for detail in simulated_action.details:
        lines.append(Text(f"  {detail}", style="dim"))

    return lines


def _get_action_type(simulated_action: SimulatedAction) -> str:
    if simulated_action.summary.startswith("simulate write "):
        return "write"
    if simulated_action.summary.startswith("simulate delete "):
        return "delete"
    if simulated_action.summary.startswith("simulate mkdir "):
        return "mkdir"
    raise ValueError(f"Unsupported simulated action summary: {simulated_action.summary}")


if __name__ == "__main__":
    raise SystemExit(main())
