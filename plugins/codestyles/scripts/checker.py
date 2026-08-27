# /// script
# requires-python = ">=3.9"
# ///
# PostToolUse hook: reviews comments in changed code. See the plugin README.
from __future__ import annotations

import json
import os
import re
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    max_len: int = 100
    max_ratio: float = 0.15
    ste_words: int = 20
    strict: bool = False


def config_from_env(env: Mapping[str, str]) -> Config:
    return Config(
        max_len=int(env.get("COMMENT_MAX_LEN", "100")),
        max_ratio=float(env.get("COMMENT_MAX_RATIO", "0.15")),
        ste_words=int(env.get("COMMENT_STE_WORDS", "20")),
        strict=env.get("COMMENT_STRICT", "0") == "1",
    )


@dataclass(frozen=True)
class Delimiter:
    open: str
    close: str


@dataclass(frozen=True)
class LanguageRules:
    line_markers: tuple[str, ...]
    block_delims: tuple[Delimiter, ...] = ()
    py_doc: bool = False


@dataclass(frozen=True)
class Comment:
    lineno: int
    raw_line: str
    text: str      # what counts toward the length limit
    body: str      # marker-stripped content, used for tracker / STE checks
    marker: str    # "" for block and doc comments
    inline: bool


@dataclass(frozen=True)
class CheckResult:
    findings: tuple[str, ...]
    comment_lines: int
    non_blank_lines: int


TECH_DEBT_RE = re.compile(r"\b(TODO|FIXME|HACK|XXX)\b", re.IGNORECASE)
TRACKER_REFERENCE_RE = re.compile(r"\b[A-Z][A-Z0-9]+-\d+\b|https?://\S+")

_HASH = ("#",)
_SLASH = ("//",)
_DASH = ("--",)
_SEMI = (";",)
_PCT = ("%",)
DEFAULT_MARKERS = ("#", "//")

LINE_MARKERS: dict[str, tuple[str, ...]] = {
    ".py": _HASH, ".pyw": _HASH, ".pyi": _HASH, ".rb": _HASH, ".sh": _HASH,
    ".bash": _HASH, ".zsh": _HASH, ".ps1": _HASH, ".psm1": _HASH, ".pl": _HASH,
    ".pm": _HASH, ".r": _HASH, ".yaml": _HASH, ".yml": _HASH, ".toml": _HASH,
    ".tf": _HASH, ".tfvars": _HASH, ".ex": _HASH, ".exs": _HASH, ".coffee": _HASH,
    ".mk": _HASH, ".cmake": _HASH, ".m4": _HASH,
    ".js": _SLASH, ".jsx": _SLASH, ".mjs": _SLASH, ".cjs": _SLASH, ".ts": _SLASH,
    ".tsx": _SLASH, ".go": _SLASH, ".java": _SLASH, ".kt": _SLASH, ".kts": _SLASH,
    ".scala": _SLASH, ".swift": _SLASH, ".c": _SLASH, ".h": _SLASH, ".hpp": _SLASH,
    ".cc": _SLASH, ".cpp": _SLASH, ".cxx": _SLASH, ".cs": _SLASH, ".rs": _SLASH,
    ".php": _SLASH, ".dart": _SLASH, ".proto": _SLASH, ".m": _SLASH, ".mm": _SLASH,
    ".sql": _DASH, ".lua": _DASH, ".hs": _DASH, ".adb": _DASH, ".ads": _DASH,
    ".elm": _DASH,
    ".lisp": _SEMI, ".clj": _SEMI, ".el": _SEMI, ".ini": _SEMI, ".cfg": _SEMI,
    ".asm": _SEMI,
    ".tex": _PCT, ".erl": _PCT,
}
BASENAME_MARKERS: dict[str, tuple[str, ...]] = {
    "makefile": _HASH, "dockerfile": _HASH, "jenkinsfile": _SLASH,
    "vagrantfile": _HASH, "rakefile": _HASH, "gemfile": _HASH, "brewfile": _HASH,
}

_C_BLOCK = (Delimiter("/*", "*/"),)
_HTML_BLOCK = (Delimiter("<!--", "-->"),)
BLOCK_DELIMS: dict[str, tuple[Delimiter, ...]] = {
    ".js": _C_BLOCK, ".jsx": _C_BLOCK, ".mjs": _C_BLOCK, ".cjs": _C_BLOCK,
    ".ts": _C_BLOCK, ".tsx": _C_BLOCK, ".go": _C_BLOCK, ".java": _C_BLOCK,
    ".kt": _C_BLOCK, ".kts": _C_BLOCK, ".scala": _C_BLOCK, ".swift": _C_BLOCK,
    ".c": _C_BLOCK, ".h": _C_BLOCK, ".hpp": _C_BLOCK, ".cc": _C_BLOCK,
    ".cpp": _C_BLOCK, ".cxx": _C_BLOCK, ".cs": _C_BLOCK, ".rs": _C_BLOCK,
    ".php": _C_BLOCK, ".dart": _C_BLOCK, ".proto": _C_BLOCK, ".m": _C_BLOCK,
    ".mm": _C_BLOCK, ".css": _C_BLOCK, ".scss": _C_BLOCK, ".less": _C_BLOCK,
    ".sql": _C_BLOCK,
    ".html": _HTML_BLOCK, ".htm": _HTML_BLOCK, ".xml": _HTML_BLOCK,
    ".vue": _HTML_BLOCK, ".svelte": _HTML_BLOCK, ".md": _HTML_BLOCK,
}
PY_DOC_EXTS = {".py", ".pyw", ".pyi"}
_TRIPLES = ('"""', "'''")


def _basename(path: str) -> str:
    return re.split(r"[\\/]", path)[-1] if path else ""


def _extension(name: str) -> str:
    return "." + name.rsplit(".", 1)[1] if "." in name else ""


def rules_for(path: str) -> LanguageRules:
    name = _basename(path).lower()
    ext = _extension(name)
    line_markers = BASENAME_MARKERS.get(name) or LINE_MARKERS.get(ext, DEFAULT_MARKERS)
    return LanguageRules(line_markers, BLOCK_DELIMS.get(ext, ()), ext in PY_DOC_EXTS)


def find_marker(line: str, markers: tuple[str, ...], lineno: int = 0) -> Comment | None:
    quote = ""
    i = 0
    while i < len(line):
        ch = line[i]
        if quote:
            if ch == "\\":
                i += 2
                continue
            if ch == quote:
                quote = ""
            i += 1
            continue
        if ch in ("'", '"', "`"):
            quote = ch
            i += 1
            continue
        for marker in markers:
            if line.startswith(marker, i):
                text = line[i + len(marker):]
                inline = line[:i].strip() != ""
                return Comment(lineno, line, (marker + text).rstrip(), text, marker, inline)
        i += 1
    return None


def _mark_span(text: str, start: int, end: int, start_line: int,
               marks: dict[int, str]) -> None:
    for offset, segment in enumerate(text[start:end].split("\n")):
        marks[start_line + offset] = marks.get(start_line + offset, "") + segment


def _scan_paired(text: str, delims: tuple[Delimiter, ...]) -> dict[int, str]:
    marks: dict[int, str] = {}
    i, line = 0, 1
    while i < len(text):
        ch = text[i]
        if ch == "\n":
            line += 1
            i += 1
            continue
        if ch in ("'", '"', "`"):
            i, line = _skip_string(text, i, line, ch)
            continue
        delim = next((d for d in delims if text.startswith(d.open, i)), None)
        if delim is None:
            i += 1
            continue
        start_line, j = line, i + len(delim.open)
        while j < len(text) and not text.startswith(delim.close, j):
            if text[j] == "\n":
                line += 1
            j += 1
        end = j + len(delim.close) if j < len(text) else len(text)
        _mark_span(text, i, end, start_line, marks)
        i = end
    return marks


def _scan_pydoc(text: str) -> dict[int, str]:
    # Skips ordinary strings and '#' comments so a triple quote inside a string
    # literal (e.g. ('\"\"\"',)) does not open a docstring.
    marks: dict[int, str] = {}
    i, line = 0, 1
    while i < len(text):
        ch = text[i]
        if ch == "\n":
            line += 1
            i += 1
            continue
        triple = next((t for t in _TRIPLES if text.startswith(t, i)), None)
        if triple is not None:
            start_line, j = line, i + 3
            while j < len(text) and not text.startswith(triple, j):
                if text[j] == "\n":
                    line += 1
                j += 1
            end = j + 3 if j < len(text) else len(text)
            _mark_span(text, i, end, start_line, marks)
            i = end
            continue
        if ch in ("'", '"'):
            i, line = _skip_string(text, i, line, ch)
            continue
        if ch == "#":
            while i < len(text) and text[i] != "\n":
                i += 1
            continue
        i += 1
    return marks


def _skip_string(text: str, i: int, line: int, quote: str) -> tuple[int, int]:
    i += 1
    while i < len(text):
        if text[i] == "\n":
            line += 1
            i += 1
            continue
        if text[i] == "\\":
            i += 2
            continue
        if text[i] == quote:
            i += 1
            break
        i += 1
    return i, line


def block_segments(text: str, rules: LanguageRules) -> dict[int, str]:
    marks: dict[int, str] = {}
    if rules.block_delims:
        marks.update(_scan_paired(text, rules.block_delims))
    if rules.py_doc:
        for lineno, segment in _scan_pydoc(text).items():
            marks[lineno] = marks.get(lineno, "") + segment
    return marks


def _strip_block_delims(segment: str) -> str:
    stripped = segment.strip()
    for token in ("/**", "/*", "*/", "<!--", "-->", '"""', "'''"):
        stripped = stripped.replace(token, " ")
    return re.sub(r"^\*+\s?", "", stripped.strip()).strip()


def comments_in(text: str, rules: LanguageRules) -> list[Comment]:
    segments = block_segments(text, rules)
    comments: list[Comment] = []
    for lineno, raw_line in enumerate(text.splitlines(), start=1):
        if lineno in segments:
            segment = segments[lineno]
            comments.append(Comment(
                lineno, raw_line, segment.strip(),
                _strip_block_delims(segment), "", False,
            ))
            continue
        hit = find_marker(raw_line, rules.line_markers, lineno)
        if hit is not None:
            comments.append(hit)
    return comments


def _sentence_word_counts(body: str) -> list[int]:
    sentences = [s for s in re.split(r"[.!?]+", body.strip()) if s.strip()]
    return [len(s.split()) for s in sentences]


def _is_shebang(comment: Comment) -> bool:
    return comment.marker == "#" and comment.lineno == 1 and comment.raw_line.startswith("#!")


def _is_banner(comment: Comment) -> bool:
    return comment.marker != "" and comment.body.strip("-#=/ ") == ""


def _length_finding(comment: Comment, config: Config) -> str | None:
    if len(comment.text) <= config.max_len:
        return None
    if comment.marker == "":
        kind = "doc/block comment"
    else:
        kind = "inline comment" if comment.inline else "comment"
    return f"line {comment.lineno}: {kind} is {len(comment.text)} chars (max {config.max_len})"


def _spacing_finding(comment: Comment) -> str | None:
    if comment.marker == "" or _is_shebang(comment) or _is_banner(comment):
        return None
    if not comment.body or comment.body.startswith(" "):
        return None
    return f"line {comment.lineno}: add a space after '{comment.marker}'"


def _tracker_finding(comment: Comment) -> str | None:
    if not TECH_DEBT_RE.search(comment.body) or TRACKER_REFERENCE_RE.search(comment.body):
        return None
    return (f"line {comment.lineno}: TODO/FIXME must link a tracker issue "
            "(e.g. ABC-123 or a URL) — otherwise remove it")


def _trailing_finding(comment: Comment) -> str | None:
    if comment.raw_line == comment.raw_line.rstrip():
        return None
    return f"line {comment.lineno}: trailing whitespace on comment line"


def _ste_finding(comment: Comment, config: Config) -> str | None:
    if _is_shebang(comment) or _is_banner(comment):
        return None
    longest = max(_sentence_word_counts(comment.body), default=0)
    if longest <= config.ste_words:
        return None
    return (f"line {comment.lineno}: comment sentence has {longest} words; "
            f"ASD-STE100 recommends <= {config.ste_words} — shorten it")


def _capitalization_finding(comment: Comment, config: Config) -> str | None:
    if not config.strict or comment.marker == "" or _is_banner(comment):
        return None
    first = comment.body.strip()[:1]
    if not first or not first.isalpha() or first.isupper():
        return None
    return f"line {comment.lineno}: start the comment with a capital letter"


def findings_for(comment: Comment, config: Config) -> list[str]:
    candidates = [
        _length_finding(comment, config),
        _spacing_finding(comment),
        _tracker_finding(comment),
        _trailing_finding(comment),
        _ste_finding(comment, config),
        _capitalization_finding(comment, config),
    ]
    return [f for f in candidates if f is not None]


def scan(text: str, rules: LanguageRules, config: Config) -> CheckResult:
    comments = comments_in(text, rules)
    non_blank = sum(1 for line in text.splitlines() if line.strip())
    findings = tuple(f for c in comments for f in findings_for(c, config))
    return CheckResult(findings, len(comments), non_blank)


def _necessity_section(comment_lines: int, where: str) -> str:
    return (
        f"Reviewed {comment_lines} comment(s) in the CHANGED code of {where} "
        "(docstrings and Javadoc/JSDoc/Scaladoc/block comments count too). "
        "Clean-code stance: a comment usually means the code could be clearer. "
        "Keep a comment only if it is one of: (1) intentional tech debt "
        "(TODO/FIXME) that links a tracker issue, or (2) documentation of an "
        "external/public API. Otherwise improve names/structure and delete it."
    )


def _density_section(result: CheckResult, config: Config) -> str | None:
    ratio = result.comment_lines / result.non_blank_lines if result.non_blank_lines else 0.0
    if ratio <= config.max_ratio:
        return None
    return (
        f"Comment density in this change is {ratio:.1%} "
        f"({result.comment_lines}/{result.non_blank_lines} changed lines), above "
        f"the {config.max_ratio:.0%} threshold. Rewrite this changed block with "
        "fewer comments — fewer is almost always better."
    )


def _style_section(findings: tuple[str, ...], config: Config) -> str | None:
    if not findings:
        return None
    listing = "\n".join(f"  - {f}" for f in findings)
    return (
        f"Style issues to fix ({len(findings)}):\n{listing}\n"
        f"Keep each comment line within {config.max_len} characters, put a space "
        "after the comment marker, and remove trailing whitespace."
    )


def _ste_section(config: Config) -> str:
    return (
        "For comments you keep, write them in ASD-STE100 Simplified Technical "
        "English: short sentences, active voice, present tense, one instruction "
        f"per sentence, and simple approved vocabulary (max {config.ste_words} words)."
    )


def build_context(text: str, path: str, config: Config, tool_name: str = "") -> str | None:
    result = scan(text, rules_for(path), config)
    if result.comment_lines == 0:
        return None
    where = path or tool_name or "the edited file"
    sections = [
        _necessity_section(result.comment_lines, where),
        _density_section(result, config),
        _style_section(result.findings, config),
        _ste_section(config),
    ]
    return "\n\n".join(s for s in sections if s is not None)


PATH_KEYS = ("file_path", "notebook_path", "path", "filePath", "filename", "file")
TEXT_KEYS = ("new_string", "new_str", "newText", "file_text", "content", "text",
             "code", "new_source")


def extract_path(tool_input: Mapping[str, object]) -> str:
    for key in PATH_KEYS:
        value = tool_input.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


def _mappings(value: object) -> list[Mapping[str, object]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def extract_new_text(tool_input: Mapping[str, object]) -> str:
    direct = [
        value
        for key in TEXT_KEYS
        if isinstance(value := tool_input.get(key), str)
    ]
    nested = [
        text
        for edit in _mappings(tool_input.get("edits"))
        if (text := extract_new_text(edit))
    ]
    return "\n".join([*direct, *nested])


def changed_files(tool_input: Mapping[str, object]) -> tuple[tuple[str, str], ...]:
    # MultiEdit carries one entry per file; every other write tool edits one file.
    groups = _mappings(tool_input.get("file_edits")) or [tool_input]
    pairs = (
        (extract_path(group) or extract_path(tool_input), extract_new_text(group))
        for group in groups
    )
    return tuple((path, text) for path, text in pairs if text)


def tool_args(payload: Mapping[str, object]) -> Mapping[str, object]:
    for key in ("tool_input", "toolInput", "toolArgs"):
        value = payload.get(key)
        if isinstance(value, Mapping):
            return value
    return {}


def tool_name(payload: Mapping[str, object]) -> str:
    for key in ("tool_name", "toolName"):
        value = payload.get(key)
        if isinstance(value, str):
            return value
    return ""


def review(payload: Mapping[str, object], config: Config) -> str | None:
    name = tool_name(payload)
    contexts = [
        context
        for path, text in changed_files(tool_args(payload))
        if (context := build_context(text, path, config, name))
    ]
    return "\n\n".join(contexts) or None


def parse_payload(raw: str) -> dict:
    if not raw.strip():
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


def emit(event: str, context: str | None) -> int:
    if context:
        json.dump(
            {"hookSpecificOutput": {"hookEventName": event, "additionalContext": context}},
            sys.stdout,
        )
    return 0


def main() -> int:
    return emit(
        "PostToolUse",
        review(parse_payload(sys.stdin.read()), config_from_env(os.environ)),
    )


if __name__ == "__main__":
    sys.exit(main())
