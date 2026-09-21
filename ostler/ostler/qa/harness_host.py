"""Ostler's side of the QA harness boundary: where it lives, and how to ask it to describe."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

HARNESS_DIR = Path(__file__).resolve().parent / "harness"


def load_harness_module(name: str) -> ModuleType:
    """Import a harness module into *ostler's* interpreter, by path."""
    source = HARNESS_DIR / f"{name}.py"
    key = f"ostler_harness_{name}"
    cached = sys.modules.get(key)
    if cached is not None:
        return cached
    spec = importlib.util.spec_from_file_location(key, source)
    if spec is None or spec.loader is None:  # pragma: no cover - a corrupt installation
        raise ImportError(f"harness module {name!r} is not installed at {source}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[key] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        del sys.modules[key]
        raise
    return module

DEFAULT_SCENARIO_TIMEOUT = 300.0

DESCRIBE_TIMEOUT = 60.0

MINIMAL_PATH = os.pathsep.join(
    part for part in os.defpath.split(os.pathsep) if part and part != os.curdir
)


def default_interpreter(root: Path) -> Path:
    """The interpreter a plan is read and run under when it names none."""
    venv = root / ".venv" / "bin" / "python"
    return venv if venv.is_file() else Path(sys.executable)


def harness_argv(interpreter: Path, *args: str) -> list[str]:
    return [str(interpreter), "-m", "ostler_qa", *args]


def harness_env(base: dict[str, str] | None = None) -> dict[str, str]:
    """`base` with the harness on `PYTHONPATH`, which is the whole of its installation."""
    env = dict(base or {})
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = (
        f"{HARNESS_DIR}{os.pathsep}{existing}" if existing else str(HARNESS_DIR)
    )
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def describe(module: Path, root: Path, interpreter: Path | None = None) -> tuple[dict[str, Any] | None, list[str]]:
    """Import the plan module in a subprocess and return the declaration set it prints."""
    interpreter = interpreter or default_interpreter(root)
    if not interpreter.exists():
        return None, [f"plan interpreter does not exist: {interpreter}"]
    try:
        done = subprocess.run(  # noqa: S603 — fixed argv, interpreter resolved above
            harness_argv(interpreter, "describe", str(module)),
            cwd=root,
            env=harness_env({"PATH": MINIMAL_PATH}),
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
