---
name: stablemate-python-cli
description: "Generic Python CLI conventions — Python 3.12+, type hints, code organization, logging, subprocess, pathlib, exit codes. Applies to all Python files."
metadata:
  generated_by: farrier
  source: library/skills/stacks/python/python-cli/SKILL.md
  resolve: "farrier source .claude/skills/stablemate-python-cli/SKILL.md"
  do_not_edit: "generated — run the `resolve` command below for this machine's editable source path, edit that, then `make agent-install` to regenerate"
---

# Python CLI — Core Conventions

**Applies to every Python file in this repo.**

---

## Language & headers

- Python **3.12+**. Every module starts with `from __future__ import annotations`.
- Full type hints on all public functions and class fields.
- No `*` imports — explicit imports only.

## Imports — absolute from the package root, always

Every import names its package from the root. Relative imports are not accepted,
including the single-dot sibling form.

```python
# Yes — the reader sees which package the name lives in, and grep finds it.
from workhorse.requirements import Requirement
from workhorse.graph import nodes

# No — both are relative.
from ..requirements import Requirement
from .model import Graph
```

A relative import only resolves when the module is imported as part of its package,
so it breaks the moment the file is run directly. It also hides provenance: `.model`
tells the reader nothing about where the code lives, and a rename can't be found by
searching for the package name.

This is enforced, not just advised — ruff's `TID252` with
`ban-relative-imports = "all"` fails the lint. `ruff check --select TID252 --fix
--unsafe-fixes` rewrites existing relative imports to absolute (the fix is "unsafe"
only in that it edits imports; verify by running the suite afterwards).

## `sys.path` manipulation is prohibited

Never write this, in source or in tests:

```python
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # prohibited
sys.path.append(...)                                            # prohibited
```

An unresolved import is a **packaging** problem and gets a packaging fix — add the
package as a workspace member, or install it into the venv — never path surgery at
import time. `sys.path` edits are order-dependent global state: they work in the one
file that does them and leave every other entry point broken.

In a test file this is always redundant: `uv sync` installs the package, so
`from mypkg.thing import X` already resolves — under pytest **and** under a direct
`python tests/test_x.py`. An insert there only shadows the installed package with a
directory that happens to look like it.

The one narrow exception is a harness that **emulates the interpreter** rather than
patching around a packaging gap: running a standalone script in-process has to
reproduce what `python script.py` does — CPython puts the script's own directory on
`sys.path[0]` — or a sibling import resolves in production and fails only in the test.
Scope it to the call and restore `sys.path` afterwards:

```python
@contextmanager
def script_dir_on_path(directory: Path):
    saved = sys.path[:]
    sys.path.insert(0, str(directory))
    try:
        yield
    finally:
        sys.path[:] = saved
```

If you reach for that anywhere other than "I am standing in for the interpreter",
it's the prohibited kind.

## uv is the package manager

Dependencies and the package itself resolve through **uv**, not ad hoc paths.

```bash
uv sync                    # install the workspace + dev group into .venv
uv add httpx               # add a dependency (edits pyproject.toml + uv.lock)
uv run pytest              # run inside the synced environment
```

- Declare dependencies in `pyproject.toml`; let `uv.lock` pin them. Never
  `pip install` into a uv-managed venv — the next `uv sync` reverts it.
- Local packages that import each other are **workspace members**
  (`[tool.uv.workspace] members = [...]`), which makes them importable by their real
  package name everywhere.
- Tests import the package exactly like any consumer does — `from workhorse.requirements
  import Requirement`. `uv sync` installs the workspace, so a test file needs no
  path setup at all.

### The one exception: scripts that run outside a uv project

A script the workflow runner executes standalone (e.g. a workhorse workflow script)
has no package to import from. It gets **no** `sys.path` insert — it must be a single
**monolithic file**: stdlib imports only, no local imports, everything it needs inlined.

If such a script has grown past what one file can hold, that is the signal to make it a
real package with a console entry point, not to reach for `sys.path`.

## Entry point pattern

```python
from __future__ import annotations

def main() -> None:
    ...

if __name__ == "__main__":
    main()
```

## Exit codes

Use `raise SystemExit(code)` — never `sys.exit()` in library code.

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Runtime error |
| 2 | Usage / argument error |

## Logging — never bare `print()` for diagnostics

```python
import logging

logger = logging.getLogger(__name__)   # name = module path, set automatically

# Entry point only — configure once:
logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format="%(name)s %(levelname)s: %(message)s",
)

logger.info("Processing %s items", count)
logger.warning("Skipping %s: %s", path, reason)
logger.error("Failed: %s", err)
```

`logging.getLogger(__name__)` is stateless — no global mutable prefix, no `set_script_name()`.

## Subprocess — prefer Python libraries; subprocess only for CLI tools

```python
import subprocess

# Only when no Python library exists for the command:
result = subprocess.run(
    ["gh", "pr", "create", "--title", title],
    capture_output=True,
    text=True,
    check=False,
    cwd=str(repo_path),
)
if result.returncode != 0:
    raise RuntimeError(f"gh pr create failed: {result.stderr.strip()}")
```

**Prefer purpose-built Python libraries over subprocess:**
- Git operations → `from git import Repo` (gitpython), not `subprocess.run(["git", ...])`
- File parsing → stdlib (`json`, `yaml`, `configparser`), not shell pipelines
- HTTP → `httpx` or `urllib`, not `curl`

Never use `shell=True`.

## Filesystem — `pathlib.Path` over string paths

```python
from pathlib import Path

root = Path(__file__).resolve().parent
config = root / "config.json"
data = config.read_text(encoding="utf-8")
```

Prefer `Path` values throughout the codebase. Convert to `str(path)` only at API boundaries that require strings, such as subprocess `cwd` or third-party libraries without `PathLike` support.

## JSON I/O

```python
import json
from pathlib import Path

def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))

def write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
```

Always specify `encoding="utf-8"` — never rely on platform default.

## Structured data — Pydantic for parsing, dataclasses for trusted records

Any model that parses, validates, coerces, or accepts data from outside the current function must use Pydantic. This includes CLI config, JSON/YAML/TOML files, environment-derived settings, API payloads, and workflow/script input.

Use frozen dataclasses or `TypedDict` for trusted in-memory records that only store values and do not need validation.

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class ServiceRecord:
    repo: str
    path: str
    type: str
    plan_file: str
```

Prefer frozen dataclasses for records that shouldn't mutate.

## Code organization and object boundaries

- Group stateless functions by module around the capability they provide, the same way related methods would be grouped on a class. For example, path construction for configuration files belongs in a config/path module rather than scattered as ad hoc string assembly at call sites.
- Prefer small modules with cohesive tools over broad utility modules. A module should have a clear noun or capability: config paths, manifest parsing, GitHub PR lookup, workflow output formatting.
- Use `Path` composition for filesystem logic; avoid manually assembling paths with plain strings.
- If an object holds state and has defined ways that state can change or be updated, model it as a class. This assumes there is meaningful behavior around the state, not just storage.
- If an object is primarily behavior or orchestration rather than value storage, name and treat it as a service. Services may depend on other services and should be instantiated through dependency injection rather than hidden global construction.
- If multiple implementations can provide the same behavior, put them behind an interface. In Python, prefer `typing.Protocol` for structural interfaces; use an abstract base class only when inheritance or shared base behavior is required.

## Error handling

```python
try:
    result = do_work(path)
except FileNotFoundError:
    logger.error("File not found: %s", path)
    raise SystemExit(1)
except ValueError as exc:
    logger.error("Invalid input: %s", exc)
    raise SystemExit(2)
```

Wrap exceptions with context. Fail fast. Never swallow exceptions silently.

## Naming

| Category | Convention |
|----------|-----------|
| Modules, functions, variables | `snake_case` |
| Classes | `PascalCase` |
| Constants | `UPPER_CASE` |
| Private module helpers | `_leading_underscore` (not exported) |
| Public API | no underscore prefix |

Private helpers (underscore prefix) are an implementation detail of their module — do not export them from a shared library.
