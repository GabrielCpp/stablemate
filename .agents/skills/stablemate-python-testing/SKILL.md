---
name: stablemate-python-testing
description: "Generic pytest patterns: hermetic fixtures, parametrize, subprocess script testing, mocking external calls, markers, conftest.py, assertions, coverage, parallel safety, and doubles that subclass the port so `ty check` catches a fake that has drifted. The concrete mechanics behind testing-design for this stack. Load when writing or reviewing pytest tests, building a fixture or a test double for a port, or testing a script that runs as a subprocess."
metadata:
  name: python-testing
  generated_by: farrier
  source: library/skills/stacks/python/python-testing/SKILL.md
  resolve: "farrier source .agents/skills/stablemate-python-testing/SKILL.md"
  do_not_edit: "generated — run the `resolve` command below for this machine's editable source path, edit that, then `make agent-install` to regenerate"
  tags: [python, backend, tests]
---

# Python Testing — pytest Patterns

---

## Framework

- **pytest ≥ 8.0** — plain `assert`, not `self.assertEqual`.
- **pytest-xdist** for parallel execution (`pytest -n auto` or `pytest.ini` `addopts = -n auto`).
- Tests must be parallel-safe. The section *Flaky shapes* below lists what to search for.

## Naming

- Test functions: `test_<description>` — descriptive, reads like a sentence.
- Test files: `<module>_test.py` co-located with source, or `tests/<module>/<subject>_test.py`.
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
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"

def test_script_happy_path(tmp_path: Path) -> None:
    # Seed inputs
    (tmp_path / "input.json").write_text('{"key": "val"}', encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(SCRIPTS / "my-script.py"), "--repo-dir", str(tmp_path), "input.json"],
        capture_output=True,
        text=True,
        cwd=str(tmp_path),
    )

    assert result.returncode == 0, f"stderr: {result.stderr}"
    output = json.loads(result.stdout)
    assert output["status"] == "valid"
```

Use `sys.executable` — the same interpreter running the test runs the script, ensuring shared dependencies are available.

**State the inputs on the command line, not in `env`.** A path handed over as an environment
variable is invisible to the caller and unreachable from the CLI, so the test and the real
invocation drift apart with nothing comparing them. In a workflow distribution this is more
than a preference — reading the environment under `workhorse_workflows/` is prohibited
outright (`make check-no-env`), so a test that seeds `AGENT_REPO_DIR` exercises a path the
code no longer takes.

## Mocking external calls

```python
from unittest.mock import patch, MagicMock

def test_with_mocked_api(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("mymodule.requests.get", lambda url: MagicMock(json=lambda: {"ok": True}))
    result = fetch_data("https://example.com")
    assert result["ok"] is True
```

Prefer `monkeypatch` over `@patch` for test-scoped mutations — it auto-reverts at test teardown.

## A double **is** the port, it does not merely look like one

Test files are type-checked to the same bar as source (`ty check`, zero findings — see
`python-cli`), and this is where that bites first. A fake that is structurally similar to the
collaborator it replaces stops being assignable the moment the real one changes — which is
precisely when a stale fake is worth hearing about, because until then it kept passing while
testing something that no longer exists.

```python
# No — a look-alike. It passes today, and goes on passing after the port grows a method.
class FakeTelemetry:
    def turn_heartbeat(self, node_id, idle_s, elapsed_s): ...

# Yes — a real one. Subclass the port (or its null implementation) and give a body only to
# what this test reads; everything else stays the no-op it is in production.
class FakeTelemetry(NullTelemetry):
    def __init__(self) -> None:
        self.beats: list[tuple[str, float, float]] = []

    def turn_heartbeat(self, node_id: str, idle_s: float, elapsed_s: float) -> None:
        self.beats.append((node_id, idle_s, elapsed_s))
```

Two details worth knowing before the checker teaches them the slow way:

- **Protocol conformance is by parameter *name*, not just position.** A `lambda *a: ...` never
  satisfies a Protocol whose `__call__` names its parameters — write a named function with the
  same parameter names.
- **Subclass the null implementation, not the abstract port,** when the port has more members
  than the test cares about. It is the difference between a fake with a dozen `...` bodies and
  one that states only the two signals under test.

### Don't assign over a method — patch it or declare it

```python
registry.directory = lambda: Path(tmp)                  # no: unchecked, and it outlives the test

with patch.object(module, "rmtree", refuse): ...        # yes: reverted on the way out
class RegistryAt(Registry):                             # yes: a declared field the reader can see
    at: Path | None = None
    def directory(self) -> Path:
        return self.at if self.at is not None else super().directory()
```

An instance attribute shadowing a method is invisible to both the reader and the checker, and on
a module-level object it leaks into every test that runs after the one that set it.

## Flaky shapes: what to search for

testing-design §15 names eight shapes that tie a verdict to something outside the test. These are
their pytest spellings. A hit is a place to read, and the counter-case column says when to leave it.

| Row | Search the tests for | Harmless when | Write instead |
| --- | --- | --- | --- |
| 15.1 | `inspect.getsource(`, or `read_text()` on a path built from a product module's `__file__` | The file sits under `tests/` | Call the function and assert on its result |
| 15.2 | `git` in a `subprocess` call whose `cwd` is not under `tmp_path`, or a `REPO_ROOT` the test walks | Never | `git init` inside `tmp_path` |
| 15.3 | `time.sleep(` or `asyncio.sleep(` followed by an `assert` | The sleep is inside a fake the test releases | Poll the condition, or wait on a `threading.Event`, with a deadline of 30 s or more |
| 15.4 | `time.monotonic()` or `time.time()` read twice and compared, or `timeout=` under 5 on a `join`, `wait` or `communicate` | The call is expected to time out | Inject the clock as a parameter |
| 15.5 | A number passed to `bind(`, `listen(` or `port=`, or `"/tmp/` and `tempfile.gettempdir()` with a fixed name | The literal is only text in a URL nothing opens | Bind port `0` and read `getsockname()[1]`, and put paths under `tmp_path` |
| 15.6 | `Path.home()`, `expanduser`, a cache-dir call, or `os.environ[...] =`, `.update(`, `.pop(` | The dict is a copy handed to a child process | An autouse fixture that sets `HOME` and `XDG_*` to `tmp_path`, and `monkeypatch.setenv` |
| 15.7 | `Popen(`, `Thread(` or `create_task(` with no `kill` or `join` in a fixture teardown or a `finally` | A `with` block owns it | A fixture that yields the process and ends its group after the `yield` |
| 15.8 | `scope="session"` or `scope="module"` on a fixture that returns a list, dict or object, or `lru_cache` in the product | The value is frozen | Function scope, or `cache_clear()` in an autouse fixture |

`inspect.getsource` reads the file from disk by the line numbers of the loaded module. After an edit
to that file it returns another function's text, with no error.

The hunt run of §15 in pytest: `pytest -n auto` with the `pytest-randomly` plugin, on a `git worktree` at a pinned commit,
repeated, while a second suite runs beside it. `pytest --lf` then reruns the changed verdicts alone.

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
