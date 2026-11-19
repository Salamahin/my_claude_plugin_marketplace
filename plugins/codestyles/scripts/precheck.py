# /// script
# requires-python = ">=3.9"
# ///
# PreToolUse hook: points Claude at a matching codestyle skill. See the plugin README.
from __future__ import annotations

import sys
from collections.abc import Mapping
from pathlib import Path

from checker import _basename, _extension, changed_files, emit, parse_payload, tool_args

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


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def review(payload: Mapping[str, object], available: frozenset[str]) -> str | None:
    contexts = [
        context
        for path, _ in changed_files(tool_args(payload))
        if (context := precheck_context(path, available))
    ]
    return "\n".join(_unique(contexts)) or None


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


def main() -> int:
    payload = parse_payload(sys.stdin.read())
    return emit("PreToolUse", review(payload, available_languages(skills_dir())))


if __name__ == "__main__":
    sys.exit(main())
