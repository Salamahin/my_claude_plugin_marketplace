---
name: python-uv-project
description: Scaffold a new Python project managed by uv with a src-based layout, wired for ruff, mypy (strict), basedpyright, pytest, and pre-commit. Use when the user wants to create/start/bootstrap a new Python project, package, or repo from scratch.
---

# Create a uv Python project (src-based layout)

Scaffold a fresh Python project that is fully managed by **uv**, uses a **src-based layout**, and comes pre-wired with ruff, mypy (strict), basedpyright, pytest, and pre-commit.

Ask the user for the **project name** if not given (kebab-case, e.g. `hello-world`). Derive the **import package** name by replacing `-` with `_` (e.g. `hello_world`). Below, `<project>` is the kebab-case name and `<pkg>` is the snake_case package.

## Prerequisite

`uv` must be installed. Check with `uv --version`. If missing, install it: `curl -LsSf https://astral.sh/uv/install.sh | sh` (or point the user at https://docs.astral.sh/uv/getting-started/installation/).

## Steps

1. **Initialize** the project with a package + src layout, then remove uv's default flat module so we own the layout:
   ```bash
   uv init --package --name <project> <project>
   cd <project>
   rm -rf src/<pkg>  # recreate below with our own contents; keep the dir tree ours
   ```
   `uv init --package` already produces a `src/<pkg>/` layout and a `[project.scripts]` entry — recreate the files below to match the target contents exactly.

2. **Pin the interpreter** to 3.12:
   ```bash
   uv python pin 3.12
   ```
   This writes `.python-version` containing `3.12`.

3. **Add dev tooling**:
   ```bash
   uv add --dev ruff mypy basedpyright pytest pre-commit
   ```

4. **Write the project files** (contents below).

5. **Sync and install hooks**:
   ```bash
   uv sync
   uv run pre-commit install
   ```

6. **Verify** everything is green before finishing:
   ```bash
   uv run pre-commit run --all-files
   uv run pytest
   uv run <project>   # should print the greeting
   ```

## Target layout

```
<project>/
├── .python-version            # 3.12
├── .gitignore
├── .pre-commit-config.yaml
├── pyproject.toml
├── README.md
├── CLAUDE.md
├── src/
│   └── <pkg>/
│       ├── __init__.py        # empty
│       └── main.py
└── tests/
    └── test_smoke.py
```

## File contents

### `pyproject.toml`

Merge uv's generated file toward this. Keep `requires-python`, `[build-system]`, and the `[project.scripts]` entry; add the tool sections. Replace `hello-world`/`hello_world` with `<project>`/`<pkg>`.

```toml
[project]
name = "<project>"
version = "0.1.0"
description = "Add your description here"
readme = "README.md"
requires-python = ">=3.12"
dependencies = []

[project.scripts]
<project> = "<pkg>.main:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/<pkg>"]

[dependency-groups]
dev = [
    "basedpyright>=1.39.4",
    "mypy>=2.1.0",
    "pre-commit>=4.6.0",
    "pytest>=9.0.3",
    "ruff>=0.15.12",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-ra"
pythonpath = ["src"]

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "I", "B", "UP", "SIM", "RUF"]

[tool.ruff.format]
quote-style = "double"

[tool.mypy]
python_version = "3.12"
strict = true
files = ["src", "tests"]
mypy_path = "src"

[tool.basedpyright]
pythonVersion = "3.12"
typeCheckingMode = "standard"
include = ["src", "tests"]
```

Leave the pinned dev versions as whatever `uv add --dev` resolved to; the versions above are a floor. Do not hand-edit `uv.lock`.

### `.pre-commit-config.yaml`

```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.15.12
    hooks:
      - id: ruff-check
        args: [--fix]
      - id: ruff-format

  - repo: local
    hooks:
      - id: mypy
        name: mypy
        entry: uv run mypy
        language: system
        types: [python]
        pass_filenames: false

      - id: basedpyright
        name: basedpyright
        entry: uv run basedpyright
        language: system
        types: [python]
        pass_filenames: false

      - id: pytest
        name: pytest
        entry: uv run pytest
        language: system
        types: [python]
        pass_filenames: false
        stages: [pre-commit]
```

### `src/<pkg>/__init__.py`

Empty file.

### `src/<pkg>/main.py`

```python
def main() -> None:
    print("Hello from <project>!")


if __name__ == "__main__":
    main()
```

### `tests/test_smoke.py`

```python
def test_arithmetic() -> None:
    assert 2 + 2 == 4
```

### `.gitignore`

```gitignore
# Python-generated files
__pycache__/
*.py[oc]
build/
dist/
wheels/
*.egg-info

# Virtual environments
.venv
```

### `CLAUDE.md`

```markdown
# <project>

## Layout
- Sources: `src/<pkg>/` (src-based layout). Entry point: `<pkg>.main:main`, exposed as the `<project>` console script.
- Tests: `tests/` (pytest discovers `test_*.py`). `pythonpath = ["src"]` is set so tests can `import <pkg>` without installing the package.
- Build backend: `hatchling` (declared in `pyproject.toml`).

## Tooling
- Dependency & environment manager: **uv**. The project is uv-controlled; the lockfile is `uv.lock` and the interpreter is pinned in `.python-version`. Do not use `pip` or manage a venv by hand.
- Test runner: **pytest** (configured via `[tool.pytest.ini_options]` in `pyproject.toml`).
- Linter + formatter: **ruff** (`[tool.ruff]`).
- Type checkers: **mypy** (strict) and **basedpyright**.
- Pre-commit: hooks defined in `.pre-commit-config.yaml`; install once with `uv run pre-commit install`.

## Common commands
- Run the app: `uv run <project>` (or `uv run python -m <pkg>.main`)
- Run tests: `uv run pytest`
- Lint / format: `uv run ruff check .` / `uv run ruff format .`
- Type-check: `uv run mypy` and `uv run basedpyright`
- Run all hooks on the repo: `uv run pre-commit run --all-files`
- Add a dependency: `uv add <pkg>` (use `--dev` for dev-only).
```

### `README.md`

A minimal readme is fine — project title plus the "Common commands" block from `CLAUDE.md`.

## Notes

- If the `codestyles` plugin's `python-style` skill is installed, follow it for any Python you write into the project.
- Everything runs through `uv run`; never invoke `pip` or a hand-made venv.
- Finish only when `uv run pre-commit run --all-files` and `uv run pytest` both pass.
