#!/usr/bin/env python3
"""Run one service's lint command and report whether it is clean — the deterministic
half of the coder's lint gate (the agent's own `make lint` done-criterion is the other).

Command resolution (the "convention + override" the gate is built on):
  1. An explicit per-service override in the orchestrating repo's agents.yml, under
     `lint:` or `workflow.lint:` as a `{service-or-dir: command}` map — wins when present.
  2. Otherwise the convention: `make lint` in the service cwd, IF that Makefile defines a
     `lint` target (probed with `make -n lint`).
  3. Otherwise nothing to run → `skipped` (opt-in: a service adopts the gate by adding a
     `lint` target or an agents.yml entry; a service without one is never falsely failed).

This keeps the gate zero-config for services that follow the `make lint` convention (groom
does: ruff + the dependency-free HTML a11y scan) while letting any service override the
command. It is run per service in the dev loop (failure → rework) and again at QA time.

Args: <cwd> [service]
  cwd      the service repo directory to lint in (dispatch entry's current_layer.cwd)
  service  the service name, for the agents.yml override lookup (optional)
Outputs JSON: {"lint_status": "clean"|"dirty"|"skipped", "lint_command": "...",
               "lint_output": "<captured, tail-truncated>", "reason": "..."}
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from workhorse.scriptutil import find_repo_root

# Cap the captured output threaded into the fix agent's context — the tail carries the
# findings; the head is usually the command echo.
MAX_OUTPUT = 4000
LINT_TIMEOUT = 300


def emit(**kwargs: str) -> None:
    payload = {"lint_status": "skipped", "lint_command": "", "lint_output": "", "reason": ""}
    payload.update(kwargs)
    print(json.dumps(payload))
    sys.exit(0)


def _agents_yml_override(service: str, cwd: Path) -> str:
    """An explicit lint command for this service from the orchestrating repo's agents.yml."""
    if not service:
        return ""
    try:
        import yaml  # lazy: only when a lookup is actually needed
    except ImportError:
        return ""
    cfg_path = find_repo_root() / "agents.yml"
    if not cfg_path.exists():
        return ""
    try:
        cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        return ""
    lint_map = cfg.get("lint") or (cfg.get("workflow") or {}).get("lint") or {}
    if not isinstance(lint_map, dict):
        return ""
    # Match by service name, then by the cwd's basename (the dir form).
    return str(lint_map.get(service) or lint_map.get(cwd.name) or "").strip()


def _has_make_lint(cwd: Path) -> bool:
    if not (cwd / "Makefile").exists() and not (cwd / "makefile").exists():
        return False
    try:
        probe = subprocess.run(
            ["make", "-n", "lint"], cwd=cwd, capture_output=True, text=True, timeout=30
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return probe.returncode == 0


def main() -> None:
    if len(sys.argv) < 2 or not sys.argv[1]:
        emit(lint_status="skipped", reason="no cwd given")
    cwd = Path(sys.argv[1]).expanduser()
    service = sys.argv[2] if len(sys.argv) > 2 else ""
    if not cwd.is_dir():
        emit(lint_status="skipped", reason=f"cwd does not exist: {cwd}")

    command = _agents_yml_override(service, cwd)
    if not command:
        if _has_make_lint(cwd):
            command = "make lint"
        else:
            emit(lint_status="skipped",
                 reason=f"no lint override and no `make lint` target in {cwd}")

    try:
        result = subprocess.run(
            command, cwd=cwd, shell=True, capture_output=True, text=True, timeout=LINT_TIMEOUT
        )
    except subprocess.TimeoutExpired:
        emit(lint_status="dirty", lint_command=command,
             lint_output=f"lint timed out after {LINT_TIMEOUT}s", reason="timeout")
    except OSError as exc:
        emit(lint_status="skipped", lint_command=command,
             lint_output=str(exc), reason="lint command could not be launched")

    output = (result.stdout + result.stderr).strip()
    if len(output) > MAX_OUTPUT:
        output = "…(truncated)…\n" + output[-MAX_OUTPUT:]
    if result.returncode == 0:
        emit(lint_status="clean", lint_command=command, reason="lint passed")
    emit(lint_status="dirty", lint_command=command, lint_output=output,
         reason=f"lint exited {result.returncode}")


if __name__ == "__main__":
    main()
