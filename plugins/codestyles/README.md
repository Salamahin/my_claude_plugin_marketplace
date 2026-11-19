# codestyles

Coding style guides for Claude Code, plus two hooks that keep generated code on-style.

## Skills

| Skill | What it does |
|-------|--------------|
| `generic-style` | The language-agnostic style guide: side effects vs business logic, immutability, non-nullable inputs, boundary validation, error handling, logging, documentation, naming, paradigm, testing, types, complexity. Applies to any language. |
| `python-style` | Builds on `generic-style`: the same rules in Python idioms with examples, plus Python-only rules (frozen dataclasses, mutable defaults, Pydantic at the edge, `MagicMock`/`patch`, type hints). |

## Hooks

`hooks/hooks.json` is picked up automatically when the plugin is enabled — no `settings.json` editing. Both hooks are **advisory**: they never block a tool call, they only feed observations back to Claude as `additionalContext`.

| Event | Matcher | What it does |
|-------|---------|--------------|
| `PreToolUse` | `Write\|Edit\|MultiEdit\|NotebookEdit` | Before Claude writes a source file, reminds it to read and apply the matching `{language}-style` skill together with `generic-style`, which it builds on. For a language without its own skill, points at `generic-style` alone. |
| `PostToolUse` | `Write\|Edit\|MultiEdit\|NotebookEdit` | Reviews comments in the **changed code only**: clean-code stance (a comment usually means the code could be clearer — keep one only for tracker-linked `TODO`/`FIXME` tech debt or public-API docs), comment density, comment length/spacing/trailing whitespace, and ASD-STE100 phrasing. Docstring- and block-comment-aware. |

Both hooks read the Claude Code hook payload from stdin and understand every write shape: `Write` (`content`/`file_text`), `Edit` (`new_string`, or nested `edits[]`), `MultiEdit` (`file_edits[]`, reported per file), and `NotebookEdit` (`new_source`).

### Requirements

[`uv`](https://docs.astral.sh/uv/) on `PATH` (the hook falls back to `python3`). The scripts are standard-library only and carry PEP 723 inline metadata, so nothing is installed.

### Tuning

Set these before starting Claude Code:

| Env var | Default | Effect |
|---------|---------|--------|
| `COMMENT_MAX_LEN` | `100` | Max characters per comment line. |
| `COMMENT_MAX_RATIO` | `0.15` | Comment-to-code ratio above which the density warning fires. |
| `COMMENT_STE_WORDS` | `20` | Max words per comment sentence (ASD-STE100). |
| `COMMENT_STRICT` | unset | `1` also flags comments that do not start with a capital letter. |

## Development

The hook scripts live in `scripts/` (`precheck.py` for `PreToolUse`, `checker.py` for `PostToolUse`; `precheck.py` imports the shared payload/parsing helpers from `checker.py`). Run the tests from the repo root:

```bash
uv run --with pytest pytest
```

## Adding a style guide

1. Create `skills/{language}-style/SKILL.md` with YAML frontmatter (`name`, `description`). The `PreToolUse` hook discovers it by directory name — no code change needed.
2. Make it build on `generic-style`: open with a pointer to `codestyles:generic-style`, follow its section order, and keep only that language's idioms, examples and language-only rules. Do not restate the generic rules.
3. Bump `version` in `.claude-plugin/plugin.json`.
