# /// script
# requires-python = ">=3.9"
# ///
# PreToolUse hook: points Claude at a matching codestyle skill. See the plugin README.
from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

from checker import (
    _basename,
    _extension,
    config_from_env,
    emit,
    parse_payload,
    payload_str,
    reviewed_files,
)

STYLE_SUFFIX = "-style"
PLUGIN_NAME = "codestyles"
GENERIC = "generic"

EXT_LANGUAGE: dict[str, str] = {
    ".py": "python", ".pyi": "python", ".pyw": "python",
    ".js": "javascript", ".jsx": "javascript", ".mjs": "javascript", ".cjs": "javascript",
    ".ts": "typescript", ".tsx": "typescript",
    ".go": "go",
    ".java": "java",
    ".kt": "kotlin", ".kts": "kotlin",
    ".scala": "scala",
    ".rs": "rust",
    ".rb": "ruby",
    ".php": "php",
    ".swift": "swift",
    ".sql": "sql",
    ".sh": "shell", ".bash": "shell", ".zsh": "shell",
    ".cs": "csharp",
    ".c": "c", ".h": "c",
    ".cpp": "cpp", ".cc": "cpp", ".cxx": "cpp", ".hpp": "cpp",
}


def language_for(path: str) -> str:
    return EXT_LANGUAGE.get(_extension(_basename(path).lower()), "")


def skill_ref(name: str) -> str:
    return f"`{PLUGIN_NAME}:{name}{STYLE_SUFFIX}`"


def language_skill_context(language: str, filename: str, has_generic: bool) -> str:
    if not has_generic:
        return (
            f"A {skill_ref(language)} skill is available for {filename}. "
            "Read and apply that style guide as you write this file."
        )
    return (
        f"A {skill_ref(language)} skill is available for {filename}. "
        f"It builds on {skill_ref(GENERIC)}. "
        "Read and apply both style guides as you write this file."
    )


def generic_skill_context(filename: str) -> str:
    return (
        f"No language-specific style skill exists for {filename}. "
        f"Read and apply {skill_ref(GENERIC)} as you write this file."
    )


def precheck_context(path: str, available: frozenset[str]) -> str | None:
    language = language_for(path)
    filename = _basename(path)
    has_generic = GENERIC in available
    if not language:
        return None
    if language in available:
        return language_skill_context(language, filename, has_generic)
    if has_generic:
        return generic_skill_context(filename)
    return None


@dataclass(frozen=True)
class Reminder:
    language: str
    context: str


def first_per_language(candidates: Iterable[Reminder]) -> tuple[Reminder, ...]:
    by_language: dict[str, Reminder] = {}
    for reminder in candidates:
        by_language.setdefault(reminder.language, reminder)
    return tuple(by_language.values())


def reminders(
    payload: Mapping[str, object], available: frozenset[str], ignore: tuple[str, ...] = ()
) -> tuple[Reminder, ...]:
    return first_per_language(
        Reminder(language_for(path), context)
        for path, _ in reviewed_files(payload, ignore)
        if (context := precheck_context(path, available))
    )


def unseen(candidates: tuple[Reminder, ...], seen: frozenset[str]) -> tuple[Reminder, ...]:
    return tuple(reminder for reminder in candidates if reminder.language not in seen)


def reminder_text(selected: tuple[Reminder, ...]) -> str | None:
    return "\n".join(reminder.context for reminder in selected) or None


def review(
    payload: Mapping[str, object],
    available: frozenset[str],
    seen: frozenset[str] = frozenset(),
    ignore: tuple[str, ...] = (),
) -> str | None:
    return reminder_text(unseen(reminders(payload, available, ignore), seen))


def available_languages(skills_dir: Path) -> frozenset[str]:
    if not skills_dir.is_dir():
        return frozenset()
    return frozenset(
        entry.name[: -len(STYLE_SUFFIX)]
        for entry in skills_dir.iterdir()
        if entry.is_dir() and entry.name.endswith(STYLE_SUFFIX)
    )


def skills_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "skills"


def state_path(session_id: str) -> Path:
    safe_id = re.sub(r"[^A-Za-z0-9_-]", "_", session_id)
    return Path(tempfile.gettempdir()) / "codestyles-precheck" / f"{safe_id}.json"


def load_seen(path: Path) -> frozenset[str]:
    try:
        return frozenset(json.loads(path.read_text()))
    except FileNotFoundError:
        return frozenset()
    except (OSError, ValueError, TypeError):
        # A broken state file only costs a repeated reminder; the hook must not fail.
        return frozenset()


def save_seen(path: Path, seen: frozenset[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(sorted(seen)))


def remind_once_per_session(
    payload: Mapping[str, object], available: frozenset[str], ignore: tuple[str, ...]
) -> str | None:
    session_id = payload_str(payload, "session_id")
    if not session_id:
        return review(payload, available, ignore=ignore)
    path = state_path(session_id)
    seen = load_seen(path)
    fresh = unseen(reminders(payload, available, ignore), seen)
    if fresh:
        save_seen(path, seen | {reminder.language for reminder in fresh})
    return reminder_text(fresh)


def main() -> int:
    payload = parse_payload(sys.stdin.read())
    ignore = config_from_env(os.environ).ignore
    available = available_languages(skills_dir())
    return emit("PreToolUse", remind_once_per_session(payload, available, ignore))


if __name__ == "__main__":
    sys.exit(main())
