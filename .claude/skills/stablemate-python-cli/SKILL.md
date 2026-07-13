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
