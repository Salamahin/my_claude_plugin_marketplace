# my_claude_plugin_marketplace

A personal [Claude Code](https://code.claude.com/docs) plugin marketplace. It hosts small, focused plugins that add skills to Claude Code — coding style guides and project scaffolding.

## Contents

```
.
├── .claude-plugin/
│   └── marketplace.json          # marketplace manifest (lists the plugins)
├── plugins/
│   ├── codestyles/               # "codestyles" plugin
│   │   ├── .claude-plugin/plugin.json
│   │   ├── hooks/hooks.json      # PreToolUse + PostToolUse hooks
│   │   ├── scripts/              # hook scripts (stdlib only, PEP 723)
│   │   │   ├── precheck.py
│   │   │   └── checker.py
│   │   ├── tests/                # pytest suite for the hook scripts
│   │   ├── skills/
│   │   │   └── python-style/SKILL.md
│   │   └── README.md
│   └── bootstrap/                # "bootstrap" plugin
│       ├── .claude-plugin/plugin.json
│       └── skills/
│           └── python-uv-project/
│               └── SKILL.md
├── pyproject.toml                # pytest config for the hook scripts
└── README.md
```

## Available plugins

### `codestyles`

Coding style guides, exposed as skills Claude auto-applies while writing or reviewing code, plus two hooks that keep it honest.

| Skill | What it does |
|-------|--------------|
| `python-style` | Opinionated Python style guide: separate side effects from business logic, prefer immutable/non-nullable data, validate untrusted external data at the boundary (Pydantic) instead of deep in the core, let exceptions propagate, log only at boundaries, meaningful naming, functional-first paradigm, pure-unit testing, strict typing, and low cyclomatic complexity. Triggers whenever Claude writes, edits, or reviews Python. |

The plugin also ships two **advisory** hooks (`plugins/codestyles/hooks/hooks.json`) — they never block a tool call, they only add context:

| Hook | Fires on | What it does |
|------|----------|--------------|
| `PreToolUse` | `Write`, `Edit`, `MultiEdit`, `NotebookEdit` | If the file's language has a `{language}-style` skill in the plugin, reminds Claude to read and apply it *before* writing. |
| `PostToolUse` | same tools | Reviews comments in the code just written: clean-code stance (keep a comment only for tracker-linked `TODO`/`FIXME` or public-API docs), comment density, length/spacing/trailing whitespace, and ASD-STE100 phrasing. |

Requires [`uv`](https://docs.astral.sh/uv/) on `PATH` (falls back to `python3`); the hook scripts are standard-library only. Tune with `COMMENT_MAX_LEN`, `COMMENT_MAX_RATIO`, `COMMENT_STE_WORDS`, `COMMENT_STRICT` — see [`plugins/codestyles/README.md`](plugins/codestyles/README.md).

### `bootstrap`

Project scaffolding skills.

| Skill | What it does |
|-------|--------------|
| `python-uv-project` | Scaffolds a new Python project managed by **uv** with a **src-based layout**, pre-wired for ruff, mypy (strict), basedpyright, pytest, and pre-commit. Triggers when you ask Claude to create/start/bootstrap a new Python project. |

## Add the marketplace

In a Claude Code session, run:

```
/plugin marketplace add Salamahin/my_claude_plugin_marketplace
```

You can also point at a local clone or a git URL:

```
/plugin marketplace add ./my_claude_plugin_marketplace          # local path
/plugin marketplace add https://github.com/Salamahin/my_claude_plugin_marketplace.git
```

Verify it registered:

```
/plugin marketplace list
```

## Install plugins

Install by `plugin@marketplace` name:

```
/plugin install codestyles@my-claude-plugin-marketplace
/plugin install bootstrap@my-claude-plugin-marketplace
```

Or browse and toggle plugins interactively:

```
/plugin
```

After install, the skills activate automatically when relevant. You can also invoke a skill explicitly, e.g. `/bootstrap:python-uv-project` or `/codestyles:python-style`.

> The marketplace name is `my-claude-plugin-marketplace` (from `.claude-plugin/marketplace.json`), which differs from the GitHub repo name `my_claude_plugin_marketplace`. Use the marketplace name after the `@`.

## Update the marketplace

Pull the latest plugin definitions from the remote:

```
/plugin marketplace update my-claude-plugin-marketplace
```

To remove it entirely:

```
/plugin marketplace remove my-claude-plugin-marketplace
```

## Add a new plugin

1. Create the plugin directory and its manifest:

   ```
   plugins/<plugin-name>/
   └── .claude-plugin/
       └── plugin.json
   ```

   `plugin.json` minimally needs `name` and `description`:

   ```json
   {
     "name": "<plugin-name>",
     "version": "1.0.0",
     "description": "What this plugin adds.",
     "author": { "name": "Salamahin" }
   }
   ```

2. Add components under the plugin directory. Skills live at `skills/<skill-name>/SKILL.md`; plugins can also carry `commands/`, `agents/`, `hooks/hooks.json`, and MCP servers. Hooks are registered automatically when the plugin is enabled, and hook commands can reference the plugin directory as `${CLAUDE_PLUGIN_ROOT}`.

3. Register the plugin in `.claude-plugin/marketplace.json` by appending to the `plugins` array:

   ```json
   {
     "name": "<plugin-name>",
     "source": "./plugins/<plugin-name>",
     "description": "What this plugin adds."
   }
   ```

4. Commit and push. Users then run `/plugin marketplace update my-claude-plugin-marketplace` to pick it up.

## Add a skill to an existing plugin

1. Create `plugins/<plugin>/skills/<skill-name>/SKILL.md` with frontmatter:

   ```markdown
   ---
   name: <skill-name>
   description: One-line description of when Claude should use this skill.
   ---

   # Skill instructions
   ...
   ```

2. Commit and push, then `/plugin marketplace update my-claude-plugin-marketplace`.

The `description` is what Claude reads to decide when to activate the skill — make it specific about the trigger conditions.

## Development

The `codestyles` hook scripts have a pytest suite. From the repo root:

```bash
uv run --with pytest pytest
```

## References

- [Plugin marketplaces](https://code.claude.com/docs/en/plugin-marketplaces.md)
- [Creating plugins](https://code.claude.com/docs/en/plugins.md)
- [Discovering & installing plugins](https://code.claude.com/docs/en/discover-plugins.md)
- [Hooks reference](https://code.claude.com/docs/en/hooks.md)
