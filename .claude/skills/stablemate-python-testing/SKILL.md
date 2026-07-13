---
name: stablemate-python-testing
description: "Generic pytest patterns — fixtures, parametrize, subprocess testing, parallel safety. Applies to test files."
metadata:
  generated_by: farrier
  source: library/skills/stacks/python/python-testing/SKILL.md
  resolve: "farrier source .claude/skills/stablemate-python-testing/SKILL.md"
  do_not_edit: "generated — run the `resolve` command below for this machine's editable source path, edit that, then `make agent-install` to regenerate"
---

# Python Testing — pytest Patterns

---

## Framework

- **pytest ≥ 8.0** — plain `assert`, not `self.assertEqual`.
- **pytest-xdist** for parallel execution (`pytest -n auto` or `pytest.ini` `addopts = -n auto`).
- Tests must be parallel-safe: no shared state, no hardcoded ports, no inter-test file conflicts.

## Naming

- Test functions: `test_<description>` — descriptive, reads like a sentence.
- Test files: `test_<module>.py` co-located with source, or `tests/<module>/test_<subject>.py`.
- Group related tests with comments, not subclasses.

## Fixtures — hermetic sandboxes

```python
import pytest
from pathlib import Path

def test_processes_file(tmp_path: Path) -> None:
    """Each test gets its own tmp_path — never share a directory between tests."""
    input_file = tmp_path / "input.json"
    input_file.write_text('{"key": "value"}', encoding="utf-8")
    result = process(input_file)
    assert result["key"] == "value"
```

- `tmp_path` — unique per test, auto-cleaned; prefer over `tempfile.mkdtemp()`
- `monkeypatch` — set env vars, patch builtins, replace attributes without global mutation
- `capsys` — capture stdout/stderr without redirecting `sys.stdout`

## Parametrize — no copy-paste test variants

```python
@pytest.mark.parametrize("input,expected", [
    ("valid",   {"status": "ok"}),
    ("empty",   {"status": "error", "reason": "empty input"}),
    ("missing", {"status": "error", "reason": "not found"}),
])
def test_parse(input: str, expected: dict) -> None:
    assert parse(input) == expected
```

## Subprocess script testing

Invoke scripts through their entry point with `sys.executable` — not `python3`:

```python
import json
import os
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"

def test_script_happy_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Seed inputs
    (tmp_path / "input.json").write_text('{"key": "val"}', encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(SCRIPTS / "my-script.py"), "input.json"],
        capture_output=True,
        text=True,
        cwd=str(tmp_path),
        env={**os.environ, "AGENT_REPO_DIR": str(tmp_path)},
    )

    assert result.returncode == 0, f"stderr: {result.stderr}"
    output = json.loads(result.stdout)
    assert output["status"] == "valid"
```

Use `sys.executable` — the same interpreter running the test runs the script, ensuring shared dependencies are available.

## Mocking external calls

```python
from unittest.mock import patch, MagicMock

def test_with_mocked_api(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("mymodule.requests.get", lambda url: MagicMock(json=lambda: {"ok": True}))
    result = fetch_data("https://example.com")
    assert result["ok"] is True
```

Prefer `monkeypatch` over `@patch` for test-scoped mutations — it auto-reverts at test teardown.

## Markers

```python
@pytest.mark.slow
def test_full_pipeline_takes_seconds() -> None: ...

@pytest.mark.integration
def test_requires_running_server() -> None: ...
```

Default suite excludes slow/integration: `pytest -m "not slow and not integration"`.

## conftest.py — shared fixtures

```python
# tests/conftest.py
import pytest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"

@pytest.fixture
def seeded_workspace(tmp_path: Path) -> Path:
    """Workspace with one repo and one service marker."""
    repo = tmp_path / "myrepo"
    (repo / "cmd" / "svc").mkdir(parents=True)
    (repo / "cmd" / "svc" / "main.go").write_text("package main")
    return tmp_path
```

Keep conftest fixtures small and composable — avoid a monolithic fixture that seeds everything.

## Assertions

```python
# Preferred — plain assert with message
assert result["status"] == "valid", f"unexpected status: {result}"

# Preferred — check subset of dict
assert {"status": "valid"}.items() <= result.items()

# Avoid — unittest style in pytest context
self.assertEqual(result["status"], "valid")
```

## Coverage

Test the **contract** (inputs → outputs), not implementation details. If renaming a private variable breaks a test, the test is wrong.
