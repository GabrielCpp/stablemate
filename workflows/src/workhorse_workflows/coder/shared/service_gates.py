"""Each service's declared gate commands, in order, and running them."""
from __future__ import annotations

import logging
import os
import subprocess
import threading
import time
from pathlib import Path
from typing import IO

from workhorse_workflows.coder.shared.blueprint import blueprint
from workhorse_workflows.coder.shared.contract import normalize_service_path
from workhorse_workflows.coder.shared.schemas.dev import GateList, GateOutcome
from workhorse_workflows.kit import find_repo_root, resolve_workspace
from workhorse_workflows.kit.manifest import read_manifest
from workhorse_workflows.kit.tools import kill_group, spawn_grouped

MAX_GATE_OUTPUT = 4000

GATE_SILENCE = 600

_KEPT_OUTPUT = 64_000


class _Listener:
    """What a gate command wrote and when it last wrote anything, so its limit measures silence rather than work."""

    def __init__(self) -> None:
        self._last = time.monotonic()
        self._lock = threading.Lock()
        self.output = bytearray()

    def drain(self, stream: IO[bytes]) -> None:
        with stream:
            self._read(stream.fileno())

    def _read(self, fd: int) -> None:
        for chunk in iter(lambda: os.read(fd, 4096), b""):
            with self._lock:
                self._last = time.monotonic()
                self.output.extend(chunk)
                del self.output[:-_KEPT_OUTPUT]

    def remaining(self, silence: float) -> float:
        with self._lock:
            return max(silence - (time.monotonic() - self._last), 0.0)


def _run_until_silent(command: str, where: Path) -> tuple[int | None, str]:
    """Run *command* until it exits, or kill it after `GATE_SILENCE` seconds without a byte of output; the exit code is None when killed."""
    process = spawn_grouped(
        command,
        cwd=where,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    listener = _Listener()
    assert process.stdout is not None
    reader = threading.Thread(target=listener.drain, args=(process.stdout,), daemon=True)
    reader.start()
    exit_code: int | None = None
    while exit_code is None:
        try:
            exit_code = process.wait(timeout=max(listener.remaining(GATE_SILENCE), 0.05))
        except subprocess.TimeoutExpired:
            if listener.remaining(GATE_SILENCE) > 0:
                continue
            kill_group(process)
            process.wait()
            break
    reader.join(timeout=5)
    return exit_code, listener.output.decode("utf-8", errors="replace")

GATE_ORDER = ("lint", "test")


def _services_config(repo_dir: str = "") -> dict[str, dict]:
    """The orchestrating repo's `services:` block — what each service type declares."""
    manifest = read_manifest(find_repo_root(repo_dir))
    if manifest is None:
        return {}
    return {
        key: entry.model_dump(exclude_unset=True) for key, entry in manifest.services.items()
    }


def service_keys(service: str = "", service_type: str = "") -> list[str]:
    """The `services:` keys this layer answers to, narrowest first."""
    path = service.partition("::")[2]
    keys: list[str] = []
    for key in (service, path, Path(path).name if path else "", service_type):
        candidate = key.strip().strip("/")
        if candidate and candidate not in keys:
            keys.append(candidate)
    return keys


def service_declaration(
    service: str = "", service_type: str = "", repo_dir: str = "", checkout: str = ""
) -> dict:
    """One service's declared block, looked up by its path, then by service name, then by type, in the run's repo and then in the service's own *checkout*, whose entries win."""
    block = _services_config(repo_dir)
    if checkout:
        block = {**block, **_services_config(checkout)}
    path = service.partition("::")[2]
    if path.strip():
        wanted = normalize_service_path(path)
        for entry in block.values():
            if normalize_service_path(entry.get("path")) == wanted:
                return entry
    for key in service_keys(service, service_type):
        entry = block.get(key)
        if isinstance(entry, dict):
            return entry
    return {}


def service_dir(cwd: str | Path, service: str = "") -> Path:
    """Where one service's declared commands run: its own directory, not its repo's."""
    root = Path(cwd).expanduser()
    path = service.partition("::")[2].strip().strip("/")
    if not path or path == ".":
        return root
    candidate = root / path
    return candidate if candidate.is_dir() else root


def _lint_override(service: str, cwd: Path, repo_dir: str = "") -> str:
    """The legacy `lint:` map — an explicit lint command keyed by service or directory."""
    if not service:
        return ""
    manifest = read_manifest(find_repo_root(repo_dir))
    if manifest is None:
        return ""
    return (manifest.lint.get(service) or manifest.lint.get(cwd.name) or "").strip()


def _has_make_target(cwd: Path, target: str) -> bool:
    """Whether this service's Makefile defines `target`."""
    if not (cwd / "Makefile").exists() and not (cwd / "makefile").exists():
        return False
    try:
        probe = subprocess.run(
            ["make", "-n", target], cwd=cwd, capture_output=True, text=True, timeout=30
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return probe.returncode == 0


def gate_command(
    gate: str, service: str, service_type: str, cwd: Path, repo_dir: str = "", checkout: str = ""
) -> str:
    """The command this service declares for one gate, or `""` when it declares none."""
    declared = service_declaration(service, service_type, repo_dir, checkout).get(gate)
    if isinstance(declared, str) and declared.strip():
        return declared.strip()
    if gate == "lint":
        legacy = _lint_override(service, cwd, repo_dir)
        if legacy:
            return legacy
    if _has_make_target(cwd, gate):
        return f"make {gate}"
    return ""


@blueprint.node
def declared_gates(
    logger: logging.Logger,
    cwd: str = "",
    service: str = "",
    service_type: str = "",
    repo_dir: str = "",
) -> GateList:
    """Which gates will run after the turn about to be taken — for the turn to be told."""
    if not cwd or not Path(cwd).expanduser().is_dir():
        return GateList()
    where = service_dir(cwd, service)
    commands = {
        gate: gate_command(gate, service, service_type, where, repo_dir, cwd)
        for gate in GATE_ORDER
    }
    declared = {gate: cmd for gate, cmd in commands.items() if cmd}
    if not declared:
        logger.info("%s declares no gate command — nothing will be run after the turn", service)
        return GateList(text="(nothing declared)")
    root = Path(cwd).expanduser()
    at = "" if where == root else f" (run in `{where.relative_to(root)}/`)"
    return GateList(
        gates=list(declared),
        commands=list(declared.values()),
        text=", ".join(f"{gate}: `{cmd}`" for gate, cmd in declared.items()) + at,
    )


@blueprint.node
def declared_services(
    logger: logging.Logger, repo_dir: str = "", workspace: str = ""
) -> GateList:
    """The services each repo declares, as `name` at `path` — for the planner."""
    repos = resolve_workspace(workspace, repo_dir)
    lines = []
    for name, info in sorted(repos.items()):
        services = info.get("services")
        if not isinstance(services, dict) or not services:
            continue
        listed = ", ".join(
            f"`{service}` at `{normalize_service_path(entry.get('path') if isinstance(entry, dict) else '')}`"
            for service, entry in services.items()
        )
        lines.append(f"- **{name}** (`{info.get('path', '')}`): {listed}")
    if not lines:
        logger.info("no repo in this workspace declares services")
        return GateList()
    return GateList(text="\n".join(lines))


@blueprint.node
def run_gate(
    logger: logging.Logger,
    cwd: str = "",
    service: str = "",
    gate: str = "lint",
    service_type: str = "",
    repo_dir: str = "",
) -> GateOutcome:
    """Run one of a service's declared gate commands and report whether it passed."""
    if not cwd:
        logger.info("no cwd given — skipping the %s gate", gate)
        return GateOutcome(gate=gate, status="skipped", reason="no cwd given")

    if not Path(cwd).expanduser().is_dir():
        logger.warning("cwd does not exist: %s", cwd)
        return GateOutcome(gate=gate, status="skipped", reason=f"cwd does not exist: {cwd}")

    where = service_dir(cwd, service)
    command = gate_command(gate, service, service_type, where, repo_dir, cwd)
    if not command:
        logger.info("%s declares no %s command in %s — skipping", service, gate, where)
        return GateOutcome(
            gate=gate,
            status="skipped",
            reason=f"no {gate} command declared for {service or where.name}",
        )

    try:
        exit_code, output = _run_until_silent(command, where)
    except OSError as exc:
        logger.warning("%s command '%s' could not be launched: %s", gate, command, exc)
        return GateOutcome(
            gate=gate,
            status="skipped",
            command=command,
            output=str(exc),
            reason=f"{gate} command could not be launched",
        )

    if exit_code == 0:
        logger.info("%s clean for %s", gate, where)
        return GateOutcome(
            gate=gate, status="clean", command=command, reason=f"{gate} passed"
        )

    output = output.strip()
    if len(output) > MAX_GATE_OUTPUT:
        output = "…(truncated)…\n" + output[-MAX_GATE_OUTPUT:]
    if exit_code is None:
        silence = f"{gate} reported nothing for {GATE_SILENCE:g}s and was killed"
        logger.warning("%s command '%s' reported nothing for %gs and was killed", gate, command, GATE_SILENCE)
        return GateOutcome(
            gate=gate,
            status="dirty",
            command=command,
            output=f"{output}\n{silence}".strip(),
            reason="timeout",
        )
    logger.warning("%s dirty for %s (exit %s)", gate, where, exit_code)
    return GateOutcome(
        gate=gate,
        status="dirty",
        command=command,
        output=output,
        reason=f"{gate} exited {exit_code}",
    )


__all__ = [
    "declared_gates",
    "declared_services",
    "gate_command",
    "run_gate",
    "service_declaration",
]
