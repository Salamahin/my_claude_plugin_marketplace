# pytest suite for the comment-style hook.
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import checker as cc
import precheck as pc
import pytest
from checker import Config

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
DEFAULT = Config()
PY_AVAILABLE = frozenset({"python"})
WITH_GENERIC = frozenset({"python", "generic"})


def count(text: str, path: str, config: Config = DEFAULT) -> int:
    return cc.scan(text, cc.rules_for(path), config).comment_lines


def findings(text: str, path: str, config: Config = DEFAULT) -> tuple[str, ...]:
    return cc.scan(text, cc.rules_for(path), config).findings


@pytest.mark.parametrize("path", ["a.py", "b.rb", "c.sh", "d.ipynb", "e.tf", "f.ps1"])
def test_hash_languages(path: str) -> None:
    assert cc.rules_for(path).line_markers == ("#",)


@pytest.mark.parametrize("path", ["a.js", "b.ts", "c.go", "d.java", "e.rs"])
def test_slash_languages(path: str) -> None:
    assert cc.rules_for(path).line_markers == ("//",)


def test_sql_marker() -> None:
    assert cc.rules_for("q.sql").line_markers == ("--",)


def test_basename_markers() -> None:
    assert cc.rules_for("Makefile").line_markers == ("#",)
    assert cc.rules_for("Jenkinsfile").line_markers == ("//",)


def test_windows_path_basename() -> None:
    assert cc.rules_for(r"C:\\project\\app\\main.py").line_markers == ("#",)


def test_unknown_extension_has_no_markers() -> None:
    assert cc.rules_for("x.unknown").line_markers == ()


@pytest.mark.parametrize(
    "path", ["README.md", "notes.txt", "doc.rst", "data.json", "c.yaml", "c.yml", "p.toml"]
)
def test_prose_and_data_files_are_not_reviewed(path: str) -> None:
    assert count("# Heading\n<!-- note -->\n// line\nvalue = 1\n", path) == 0


def test_markdown_write_produces_no_review() -> None:
    payload = {
        "tool_name": "Write",
        "tool_input": {"file_path": "spec.md", "content": "# Title\n\n<!-- guidance -->\n"},
    }
    assert cc.review(payload, DEFAULT) is None


def test_parse_globs_trims_and_drops_empty() -> None:
    globs = cc.parse_globs(" .specify/** , ,.claude/skills/**")
    assert globs == (".specify/**", ".claude/skills/**")


def test_config_reads_comment_ignore() -> None:
    config = cc.config_from_env({"COMMENT_IGNORE": ".specify/**,vendor/*"})
    assert config.ignore == (".specify/**", "vendor/*")


def test_is_ignored_matches_relative_to_cwd() -> None:
    globs = (".specify/**",)
    assert cc.is_ignored("/repo/.specify/scripts/a.sh", "/repo", globs)
    assert not cc.is_ignored("/repo/src/a.sh", "/repo", globs)


def test_is_ignored_matches_absolute_glob() -> None:
    assert cc.is_ignored("/repo/gen/a.py", "", ("*/gen/*",))


def test_review_skips_ignored_files() -> None:
    payload = {
        "cwd": "/repo",
        "tool_name": "Write",
        "tool_input": {"file_path": "/repo/.specify/scripts/a.sh", "content": "#bad\n"},
    }
    assert cc.review(payload, Config(ignore=(".specify/**",))) is None
    assert cc.review(payload, DEFAULT) is not None


def test_find_marker_ignores_string_literal() -> None:
    assert cc.find_marker('x = "http://not-a-comment"', ("//",)) is None


def test_find_marker_detects_inline() -> None:
    hit = cc.find_marker("x = 1  # note", ("#",))
    assert hit is not None and hit.inline and hit.marker == "#"


def test_find_marker_whole_line() -> None:
    hit = cc.find_marker("# header", ("#",))
    assert hit is not None and not hit.inline


def test_missing_space_flagged() -> None:
    assert any("add a space" in f for f in findings("#bad\n", "a.py"))


def test_shebang_exempt() -> None:
    assert not any("add a space" in f for f in findings("#!/usr/bin/env python3\n", "a.py"))


def test_banner_exempt() -> None:
    assert findings("# ------------------------------\n", "a.py") == ()


def test_todo_requires_tracker() -> None:
    assert any("tracker issue" in f for f in findings("# TODO fix later\n", "a.py"))


def test_todo_with_key_ok() -> None:
    assert not any("tracker" in f for f in findings("# TODO ABC-123 fix later\n", "a.py"))


def test_todo_with_url_ok() -> None:
    text = "# FIXME https://tracker/issue/1\n"
    assert not any("tracker" in f for f in findings(text, "a.py"))


def test_long_comment_flagged() -> None:
    text = "# " + "x" * 200 + "\n"
    assert any("chars (max" in f for f in findings(text, "a.py"))


def test_trailing_whitespace_flagged() -> None:
    assert any("trailing whitespace" in f for f in findings("# note   \n", "a.py"))


def test_ste_long_sentence_flagged() -> None:
    text = "# " + " ".join(["word"] * 25) + ".\n"
    assert any("ASD-STE100" in f for f in findings(text, "a.py"))


def test_strict_capitalization() -> None:
    strict = Config(strict=True)
    assert any("capital letter" in f for f in findings("# lowercase start.\n", "a.py", strict))
    assert not any("capital letter" in f for f in findings("# lowercase start.\n", "a.py"))


def test_python_docstring_counts() -> None:
    text = 'def f():\n    """Doc line one.\n    Doc line two.\n    """\n    return 1\n'
    assert count(text, "m.py") == 3


def test_single_quote_docstring_counts() -> None:
    assert count("x = 1\n'''one line docstring'''\n", "m.py") == 1


def test_triple_quote_inside_string_not_a_docstring() -> None:
    text = 'TRIPLES = (\'"""\', "\'\'\'")\nx = 1\ny = 2\n'
    assert count(text, "m.py") == 0


def test_triple_quotes_outside_python_ignored() -> None:
    assert count('const s = """not a docstring""";\n', "a.js") == 0


def test_javadoc_block_counts_all_lines() -> None:
    assert count("/**\n * Adds numbers.\n */\nint add(){return 0;}\n", "A.java") == 3


def test_scaladoc_single_line() -> None:
    assert count("/** one-line scaladoc */\ndef f = 1\n", "A.scala") == 1


def test_c_block_inline() -> None:
    assert count("int x = 1; /* set x */\n", "a.c") == 1


def test_html_comment_counts() -> None:
    assert count("<div></div>\n<!-- a comment -->\n", "page.html") == 1


def test_block_marker_inside_string_ignored() -> None:
    assert count('const s = "/* not a comment */";\nconst y = 2;\n', "a.js") == 0


def test_todo_in_block_needs_tracker() -> None:
    assert any("tracker issue" in f for f in findings("/*\n TODO fix this\n*/\nint x;\n", "a.c"))


def test_todo_in_docstring_with_tracker_ok() -> None:
    text = 'def f():\n    """TODO ABC-123 fix later."""\n    return 1\n'
    assert not any("tracker issue" in f for f in findings(text, "m.py"))


def test_no_comment_returns_none() -> None:
    assert cc.build_context("x = 1\n", "a.py", DEFAULT) is None


def test_density_over_threshold() -> None:
    ctx = cc.build_context("# a comment here\nx = 1  # b comment\n", "a.py", DEFAULT)
    assert ctx is not None and "Comment density" in ctx


def test_density_under_threshold_omits_section() -> None:
    lenient = Config(max_ratio=0.9)
    body = "# Public API entry\n" + "".join(f"x{i} = {i}\n" for i in range(20))
    ctx = cc.build_context(body, "a.py", lenient)
    assert ctx is not None and "Comment density" not in ctx and "Clean-code stance" in ctx


def test_context_always_has_necessity_and_ste() -> None:
    ctx = cc.build_context("# a\n", "a.py", DEFAULT)
    assert ctx is not None and "Clean-code stance" in ctx and "ASD-STE100" in ctx


def test_docstring_density_via_build_context() -> None:
    text = 'def f():\n    """A.\n    B.\n    C."""\n    return 1\n'
    ctx = cc.build_context(text, "m.py", DEFAULT)
    assert ctx is not None and "Comment density" in ctx


def test_review_reads_write_payload() -> None:
    payload = {"tool_name": "Write", "tool_input": {"file_path": "a.py", "content": "#bad\n"}}
    assert cc.review(payload, DEFAULT) is not None


def test_review_reads_file_text() -> None:
    payload = {"tool_name": "Write", "tool_input": {"file_path": "a.py", "file_text": "# TODO nope\n"}}
    ctx = cc.review(payload, DEFAULT)
    assert ctx is not None and "tracker issue" in ctx


def test_review_reads_edit_new_string() -> None:
    payload = {
        "tool_name": "Edit",
        "tool_input": {"file_path": "a.py", "old_string": "x = 1", "new_string": "#bad\n"},
    }
    assert cc.review(payload, DEFAULT) is not None


def test_review_reads_nested_edits() -> None:
    payload = {
        "tool_name": "Edit",
        "tool_input": {
            "file_path": "a.py",
            "edits": [{"old_str": "x", "new_str": "# TODO nope\n"}],
        },
    }
    ctx = cc.review(payload, DEFAULT)
    assert ctx is not None and "tracker issue" in ctx


def test_review_reads_notebook_edit() -> None:
    payload = {
        "tool_name": "NotebookEdit",
        "tool_input": {"notebook_path": "nb.ipynb", "new_source": "#bad\n"},
    }
    assert cc.review(payload, DEFAULT) is not None


def test_changed_files_multiedit_keeps_each_path() -> None:
    args = {
        "file_edits": [
            {"file_path": "a.py", "edits": [{"old_str": "x", "new_str": "# one\n"}]},
            {"file_path": "B.java", "edits": [{"old_str": "y", "new_str": "// two\n"}]},
        ]
    }
    assert [path for path, _ in cc.changed_files(args)] == ["a.py", "B.java"]


def test_review_multiedit_reports_every_file() -> None:
    payload = {
        "tool_name": "MultiEdit",
        "tool_input": {
            "file_edits": [
                {"file_path": "a.py", "edits": [{"old_str": "x", "new_str": "#bad\n"}]},
                {"file_path": "B.java", "edits": [{"old_str": "y", "new_str": "//bad\n"}]},
            ]
        },
    }
    ctx = cc.review(payload, DEFAULT)
    assert ctx is not None and "a.py" in ctx and "B.java" in ctx


def test_review_ignores_missing_text() -> None:
    assert cc.review({"tool_name": "Bash", "tool_input": {"command": "ls"}}, DEFAULT) is None


def test_review_bad_toolinput() -> None:
    assert cc.review({"tool_input": "notadict"}, DEFAULT) is None


def test_config_from_env() -> None:
    config = cc.config_from_env({"COMMENT_MAX_LEN": "50", "COMMENT_STRICT": "1"})
    assert config.max_len == 50 and config.strict is True and config.max_ratio == 0.15


def test_parse_payload_bad_json() -> None:
    assert cc.parse_payload("not json") == {}


def _run(payload: dict) -> str:
    proc = subprocess.run(
        [sys.executable, str(SCRIPTS / "checker.py")],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    return proc.stdout


def test_end_to_end_finding() -> None:
    out = _run({"tool_name": "Write", "tool_input": {"file_path": "a.py", "content": "#bad\n"}})
    hook_output = json.loads(out)["hookSpecificOutput"]
    assert hook_output["hookEventName"] == "PostToolUse"
    assert "add a space" in hook_output["additionalContext"]


def test_end_to_end_silent_on_clean() -> None:
    out = _run({"tool_name": "Write", "tool_input": {"file_path": "a.py", "content": "x = 1\n"}})
    assert out.strip() == ""


def test_language_for_extensions() -> None:
    assert pc.language_for("a.py") == "python"
    assert pc.language_for("a.ts") == "typescript"
    assert pc.language_for("a.unknown") == ""


def test_precheck_matches_available_skill() -> None:
    ctx = pc.precheck_context("src/app.py", PY_AVAILABLE)
    assert ctx is not None and "python-style" in ctx


def test_precheck_no_skill_for_language() -> None:
    assert pc.precheck_context("a.ts", PY_AVAILABLE) is None


def test_precheck_unknown_extension() -> None:
    assert pc.precheck_context("notes.txt", PY_AVAILABLE) is None


def test_precheck_language_skill_points_to_generic() -> None:
    ctx = pc.precheck_context("src/app.py", WITH_GENERIC)
    assert ctx is not None
    assert "codestyles:python-style" in ctx and "codestyles:generic-style" in ctx


def test_precheck_falls_back_to_generic() -> None:
    ctx = pc.precheck_context("main.go", WITH_GENERIC)
    assert ctx is not None and "codestyles:generic-style" in ctx and "go-style" not in ctx


def test_precheck_generic_needs_known_language() -> None:
    assert pc.precheck_context("notes.txt", WITH_GENERIC) is None
    assert pc.precheck_context("README.md", WITH_GENERIC) is None


def test_precheck_review_requires_write_intent() -> None:
    read_payload = {"tool_name": "Read", "tool_input": {"file_path": "a.py"}}
    assert pc.review(read_payload, PY_AVAILABLE) is None
    write_payload = {"tool_name": "Write", "tool_input": {"file_path": "a.py", "content": "x=1\n"}}
    assert pc.review(write_payload, PY_AVAILABLE) is not None


def test_precheck_review_no_path() -> None:
    assert pc.review({"tool_name": "Bash", "tool_input": {"command": "ls"}}, PY_AVAILABLE) is None


def test_precheck_review_dedupes_same_file() -> None:
    payload = {
        "tool_name": "MultiEdit",
        "tool_input": {
            "file_edits": [
                {"file_path": "a.py", "edits": [{"old_str": "x", "new_str": "y"}]},
                {"file_path": "b.py", "edits": [{"old_str": "x", "new_str": "y"}]},
                {"file_path": "a.py", "edits": [{"old_str": "y", "new_str": "z"}]},
            ]
        },
    }
    context = pc.review(payload, PY_AVAILABLE)
    assert context is not None and context.count("a.py") == 1


def test_tool_args_reads_snake_case_and_fallbacks() -> None:
    assert cc.tool_args({"tool_input": {"file_path": "a.py"}}) == {"file_path": "a.py"}
    assert cc.tool_args({"toolInput": {"path": "b.py"}}) == {"path": "b.py"}
    assert cc.tool_args({"toolArgs": {"path": "c.py"}}) == {"path": "c.py"}
    assert cc.tool_args({"other": 1}) == {}


def test_tool_name_reads_both_spellings() -> None:
    assert cc.tool_name({"tool_name": "Write"}) == "Write"
    assert cc.tool_name({"toolName": "Write"}) == "Write"
    assert cc.tool_name({}) == ""


def test_emit_wraps_context_in_hook_output(capsys: pytest.CaptureFixture[str]) -> None:
    assert cc.emit("PostToolUse", "note") == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload == {
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": "note",
        }
    }


def test_emit_stays_silent_without_context(capsys: pytest.CaptureFixture[str]) -> None:
    assert cc.emit("PreToolUse", None) == 0
    assert capsys.readouterr().out == ""


def test_available_languages_reads_real_skills_dir() -> None:
    assert {"python", "generic"} <= pc.available_languages(pc.skills_dir())


def test_precheck_skips_ignored_files() -> None:
    payload = {
        "cwd": "/repo",
        "tool_name": "Write",
        "tool_input": {"file_path": "/repo/.claude/skills/x/a.py", "content": "x=1\n"},
    }
    assert pc.review(payload, WITH_GENERIC, ignore=(".claude/skills/**",)) is None
    assert pc.review(payload, WITH_GENERIC) is not None


def test_precheck_reminds_once_per_language() -> None:
    payload = {
        "tool_name": "MultiEdit",
        "tool_input": {
            "file_edits": [
                {"file_path": "a.go", "edits": [{"old_str": "x", "new_str": "y"}]},
                {"file_path": "b.go", "edits": [{"old_str": "x", "new_str": "y"}]},
                {"file_path": "c.py", "edits": [{"old_str": "x", "new_str": "y"}]},
            ]
        },
    }
    assert [r.language for r in pc.reminders(payload, WITH_GENERIC)] == ["go", "python"]


def test_precheck_skips_languages_already_seen() -> None:
    payload = {"tool_name": "Write", "tool_input": {"file_path": "a.py", "content": "x=1\n"}}
    assert pc.review(payload, WITH_GENERIC, seen=frozenset({"python"})) is None
    assert pc.review(payload, WITH_GENERIC, seen=frozenset({"go"})) is not None


def test_load_seen_tolerates_missing_and_broken_state(tmp_path: Path) -> None:
    assert pc.load_seen(tmp_path / "missing.json") == frozenset()
    broken = tmp_path / "broken.json"
    broken.write_text("{not json")
    assert pc.load_seen(broken) == frozenset()


def _precheck(payload: dict, tmpdir: Path) -> str:
    proc = subprocess.run(
        [sys.executable, str(SCRIPTS / "precheck.py")],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env={**os.environ, "TMPDIR": str(tmpdir)},
    )
    assert proc.returncode == 0, proc.stderr
    return proc.stdout


def test_precheck_session_reminds_each_language_once(tmp_path: Path) -> None:
    def write(path: str) -> dict:
        return {"session_id": "s-1", "tool_name": "Write",
                "tool_input": {"file_path": path, "content": "x=1\n"}}

    assert "python-style" in _precheck(write("a.py"), tmp_path)
    assert _precheck(write("b.py"), tmp_path).strip() == ""
    assert "generic-style" in _precheck(write("main.go"), tmp_path)


def test_python_style_references_generic_style() -> None:
    python_style = (pc.skills_dir() / "python-style" / "SKILL.md").read_text()
    assert "codestyles:generic-style" in python_style


def test_precheck_end_to_end() -> None:
    payload = {"tool_name": "Write", "tool_input": {"file_path": "x.py", "content": "x=1\n"}}
    proc = subprocess.run(
        [sys.executable, str(SCRIPTS / "precheck.py")],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    hook_output = json.loads(proc.stdout)["hookSpecificOutput"]
    assert hook_output["hookEventName"] == "PreToolUse"
    assert "codestyles:python-style" in hook_output["additionalContext"]

