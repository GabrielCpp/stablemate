"""Ostler's side of the QA harness boundary: where it lives, and how to ask it to describe.

The harness itself (`harness/ostler_qa.py`) is stdlib-only and never imports ostler, because
it runs under the *project's* interpreter. This module is the mirror image — the ostler-side
knowledge of how to reach it, shared by the loader that validates a plan and the driver that
executes one, so the two can never disagree about which interpreter a plan is read under.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

HARNESS_DIR = Path(__file__).resolve().parent / "harness"


def load_harness_module(name: str) -> ModuleType:
    """Import a harness module into *ostler's* interpreter, by path.

    The harness is not a package — it is a directory ostler puts on the subprocess's
    `PYTHONPATH`, so `import ostler.qa.harness.x` is not a thing. Loading by path is how the
    ostler side reads a definition the harness owns without either one importing the other,
    which is what keeps a scan run under QA identical to a scan run under `vet`.
    """
    source = HARNESS_DIR / f"{name}.py"
    key = f"ostler_harness_{name}"
    cached = sys.modules.get(key)
    if cached is not None:
        return cached
    spec = importlib.util.spec_from_file_location(key, source)
    if spec is None or spec.loader is None:  # pragma: no cover - a corrupt installation
        raise ImportError(f"harness module {name!r} is not installed at {source}")
    module = importlib.util.module_from_spec(spec)
    # Registered *before* execution, and kept: a module body that reads its own
    # `sys.modules` entry — `@dataclass` does, to resolve annotations — raises
    # `AttributeError` on `None` otherwise, and every caller wants the same object anyway.
    sys.modules[key] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        del sys.modules[key]
        raise
    return module

#: How long one scenario may run before the driver kills its process group. A scenario can
#: raise this for itself with ``@scenario(timeout=…)``.
DEFAULT_SCENARIO_TIMEOUT = 300.0

#: `describe` imports the plan module and prints its declarations. It is meant to be nearly
#: instantaneous — a plan that takes longer than this is doing real work at import time,
#: which is the one thing the format forbids, and the timeout is how that gets said out loud
#: instead of turning every `validate` into a run.
DESCRIBE_TIMEOUT = 60.0


def default_interpreter(root: Path) -> Path:
    """The interpreter a plan is read and run under when it names none.

    A project venv if there is one, ostler's own otherwise. Deliberately a single fixed
    lookup rather than a search: a plan that resolves differently on two machines fails in
    the least debuggable way there is, and `interpreter=` exists to say so explicitly.
    """
    venv = root / ".venv" / "bin" / "python"
    return venv if venv.is_file() else Path(sys.executable)


def harness_argv(interpreter: Path, *args: str) -> list[str]:
    return [str(interpreter), "-m", "ostler_qa", *args]


def harness_env(base: dict[str, str] | None = None) -> dict[str, str]:
    """`base` with the harness on `PYTHONPATH`, which is the whole of its installation."""
    env = dict(base or {})
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = f"{HARNESS_DIR}:{existing}" if existing else str(HARNESS_DIR)
    # A plan module lives in the spec directory, which is documentation under version
    # control — so importing it writes a `__pycache__/` next to `plan.md` that nothing
    # cleans up and the next `git add` sweeps in.
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def describe(module: Path, root: Path, interpreter: Path | None = None) -> tuple[dict[str, Any] | None, list[str]]:
    """Import the plan module in a subprocess and return the declaration set it prints.

    A plan that will not import is a plan that cannot run, and saying so here — with the
    traceback — is the static check the YAML format could never offer: an `ImportError` used
    to surface an hour into a run, as a driver failure against a story that was fine.
    """
    interpreter = interpreter or default_interpreter(root)
    if not interpreter.exists():
        return None, [f"plan interpreter does not exist: {interpreter}"]
    try:
        done = subprocess.run(  # noqa: S603 — fixed argv, interpreter resolved above
            harness_argv(interpreter, "describe", str(module)),
            cwd=root,
            env=harness_env({"PATH": "/usr/bin:/bin:/usr/local/bin"}),
            capture_output=True,
            text=True,
            timeout=DESCRIBE_TIMEOUT,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return None, [
            f"describing {module.name} took longer than {DESCRIBE_TIMEOUT:g}s — a QA plan "
            "must declare at import time and do its work inside a scenario"
        ]
    if done.returncode != 0:
        detail = (done.stderr or done.stdout).strip()[-2000:]
        return None, [f"plan module failed to import:\n{detail}"]
    try:
        data = json.loads(done.stdout)
    except json.JSONDecodeError as exc:
        return None, [f"describe did not print JSON ({exc}): {done.stdout.strip()[:500]}"]
    if not isinstance(data, dict):
        return None, ["describe must print a JSON object"]
    return data, []
