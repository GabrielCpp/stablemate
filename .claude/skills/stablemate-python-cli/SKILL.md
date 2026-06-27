---
name: stablemate-python-cli
description: "Generic Python CLI conventions — Python 3.12+, type hints, logging, subprocess, pathlib, exit codes. Applies to all Python files."
metadata:
  generated_by: farrier
  source: library/skills/python/python-cli/SKILL.md
  do_not_edit: "edit the source in the central prompt library and re-run `make agent-install` to regenerate"
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

## Filesystem — `pathlib.Path` over `os.path`

```python
from pathlib import Path

root = Path(__file__).resolve().parent
config = root / "config.json"
data = config.read_text(encoding="utf-8")
```

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

## Structured data — dataclasses or TypedDict over raw dicts

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
