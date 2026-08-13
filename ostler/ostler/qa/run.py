"""Orchestrate all `ostler qa` subcommands.

See QA-RUN.md for full design. This module translates parsed CLI args into
session operations and produces human-readable / JSON output.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


from ostler.qa.session import QaSession, RUN_LOG
from ostler.qa.plan import load_plan, resolve_spec_dir, validate_v2
from ostler.qa.v2 import run_plan as run_v2_plan


def _raise_keyboard_interrupt(signum: int, frame: Any) -> None:
    """SIGTERM's default action kills the process immediately, bypassing any
    `finally` block — unlike SIGINT, which Python turns into a catchable
    `KeyboardInterrupt`. Installing this handler makes a SIGTERM (e.g. from a
    caller's process-group kill on Ctrl+C, such as workhorse's agent-interrupt
    cleanup) behave the same as a direct Ctrl+C, so `cmd_run`'s `finally` still
    runs and background daemons still get stopped instead of orphaned.
    """
    raise KeyboardInterrupt


@dataclass
class QaOutcome:
    ok: bool
    message: str
    data: dict[str, Any] = field(default_factory=dict)
    status: str = ""

    def __post_init__(self) -> None:
        if not self.status:
            self.status = "passed" if self.ok else "failed"
        self.data.setdefault("status", self.status)


# ---------------------------------------------------------------------------
# start
# ---------------------------------------------------------------------------

DaemonSpec = tuple[str, Sequence[str], str | Mapping[str, Any] | None]
"""A background daemon to start: its name, its argv, and how to tell it is ready.

The argv is a program and its arguments, never a command line — nothing here reaches a
shell. The readiness probe is a URL to poll, a ``{url, method, status}`` mapping for a
service that is not a GET-200 health endpoint, or ``None`` for a daemon nobody waits on.
Named because the CLI builds this list and hands it straight here — spelled out twice, the
two spellings drift and the list stops being assignable for reasons that read as a
type-checker complaint rather than as the API change they are.
"""


def cmd_start(
    run_id: str,
    story: str,
    spec_dir: Path,
    *,
    env: dict[str, str] | None = None,
    daemons: list[DaemonSpec] | None = None,
    secret_values: dict[str, str] | None = None,
) -> QaOutcome:
    """Open a new QA session and optionally start background daemons.

    *daemons*: list of (name, argv, ready_check) tuples, where the readiness check is
    either a URL polled for a 200 or a ``{url, method, status}`` mapping.
    """
    env = env or {}
    try:
        session = QaSession.create(
            spec_dir,
            run_id,
            story,
            env,
            secret_values=secret_values,
        )
    except FileExistsError as exc:
        return QaOutcome(ok=False, message=str(exc))

    session.write_session_start()
    pids: dict[str, int] = {}
    for name, argv, ready_check in daemons or []:
        try:
            pid = session.start_daemon(name, argv, ready_check=ready_check)
            pids[name] = pid
        except (OSError, TimeoutError, ValueError) as exc:
            session.close(status="blocked")
            session.finalize_log_artifact()
            return QaOutcome(
                ok=False,
                message=f"daemon '{name}' ready_check failed: {exc}",
                status="blocked",
            )

    msg = f"QA session started: run_id={run_id}, story={story}"
    if pids:
        msg += f", daemons={list(pids)}"
    return QaOutcome(ok=True, message=msg, data={"run_id": run_id, "pids": pids})


# ---------------------------------------------------------------------------
# step
# ---------------------------------------------------------------------------


def cmd_step(
    spec_dir: Path,
    step_id: str,
    label: str,
    mechanism: str,
    cmd: str,
    *,
    captures: list[tuple[str, str]] | None = None,
    out_path: str | None = None,
    allow_fail: bool = False,
    timeout: float = 60,
) -> QaOutcome:
    """Execute a command and record it in the run log."""
    try:
        session = QaSession.open(spec_dir)
    except FileNotFoundError as exc:
        return QaOutcome(ok=False, message=str(exc))

    try:
        record = session.run_step(
            step_id,
            label,
            mechanism,
            cmd,
            captures=captures,
            out_path=out_path,
            allow_fail=allow_fail,
            timeout=timeout,
            cwd=spec_dir,
        )
        return QaOutcome(ok=True, message=f"step '{step_id}' recorded", data=record)
    except (ValueError, RuntimeError) as exc:
        return QaOutcome(ok=False, message=str(exc))


# ---------------------------------------------------------------------------
# assert
# ---------------------------------------------------------------------------


def cmd_assert(
    spec_dir: Path,
    assert_id: str,
    label: str,
    check_type: str,
    params: dict[str, Any],
    *,
    root: Path,
) -> QaOutcome:
    """Execute a named check and record PASS/FAIL."""
    try:
        session = QaSession.open(spec_dir)
    except FileNotFoundError as exc:
        return QaOutcome(ok=False, message=str(exc))

    passed, record = session.run_assert(assert_id, label, check_type, params, root=root)
    verdict = "PASS" if passed else "FAIL"
    return QaOutcome(ok=passed, message=f"assert '{assert_id}': {verdict}", data=record)


# ---------------------------------------------------------------------------
# stop
# ---------------------------------------------------------------------------


def cmd_stop(spec_dir: Path) -> QaOutcome:
    """Kill daemons and write the session_stop summary."""
    try:
        session = QaSession.open(spec_dir)
    except FileNotFoundError as exc:
        return QaOutcome(ok=False, message=str(exc))

    summary = session.close()
    session.finalize_log_artifact()
    fail_count = summary.get("fail_count", 0)
    verdict = "PASS" if fail_count == 0 else "FAIL"
    return QaOutcome(
        ok=fail_count == 0,
        message=f"QA run complete: {verdict} "
        f"({summary['pass_count']} passed, {fail_count} failed, "
        f"{summary['step_count']} steps)",
        data=summary,
    )


# ---------------------------------------------------------------------------
# report
# ---------------------------------------------------------------------------


def cmd_report(spec_dir: Path) -> QaOutcome:
    """Render a human-readable action ledger from qa-run.ndjson."""
    log_path = spec_dir / "qa" / RUN_LOG
    if not log_path.is_file():
        return QaOutcome(ok=False, message=f"run log not found: {log_path}")

    records = _read_log(log_path)
    lines: list[str] = []
    asserts: list[dict] = []

    for rec in records:
        kind = rec.get("kind", "")
        ts = rec.get("ts", "?")
        if kind == "session_start":
            lines.append(
                f"[{ts}] SESSION START  run_id={rec.get('run_id', '')}  "
                f"story={rec.get('story', '')}"
            )
        elif kind == "daemon_start":
            lines.append(
                f"[{ts}] DAEMON START   {rec.get('name', '')}  pid={rec.get('pid', '')}"
            )
        elif kind == "step":
            mech = f"[{rec.get('mechanism', '?').upper()}]"
            ec = rec.get("exit_code", "?")
            lines.append(
                f"[{ts}] STEP {mech:12s} {rec.get('id', '')}  exit={ec}  "
                f"{rec.get('label', '')}"
            )
        elif kind == "assert":
            result = rec.get("result", "?")
            asserts.append(rec)
            lines.append(
                f"[{ts}] ASSERT         {rec.get('id', '')}  {result}  "
                f"{rec.get('label', '')}"
            )
        elif kind == "daemon_stop":
            lines.append(
                f"[{ts}] DAEMON STOP    {rec.get('name', '')}  pid={rec.get('pid', '')}"
            )
        elif kind == "session_stop":
            p, f = rec.get("pass_count", 0), rec.get("fail_count", 0)
            verdict = "PASS" if f == 0 else "FAIL"
            lines.append(
                f"[{ts}] SESSION STOP   {verdict}  "
                f"{p} passed / {f} failed / {rec.get('step_count', 0)} steps"
            )

    if asserts:
        lines.append("")
        lines.append("Assert summary:")
        for a in asserts:
            result = a.get("result", "?")
            icon = "✓" if result == "PASS" else "✗"
            lines.append(
                f"  {icon} {a.get('id', '')}  [{a.get('check', '')}]  {a.get('label', '')}"
            )

    report = "\n".join(lines)
    print(report)
    return QaOutcome(ok=True, message="", data={"report": report})


# ---------------------------------------------------------------------------
# replay
# ---------------------------------------------------------------------------


def cmd_replay(spec_dir: Path) -> QaOutcome:
    """Emit a shell script of all step commands from qa-run.ndjson."""
    log_path = spec_dir / "qa" / RUN_LOG
    if not log_path.is_file():
        return QaOutcome(ok=False, message=f"run log not found: {log_path}")

    records = _read_log(log_path)
    lines: list[str] = [
        "#!/usr/bin/env bash",
        "# Replay of QA run — generated by `ostler qa replay`",
        "",
    ]

    for rec in records:
        if rec.get("kind") != "step":
            continue
        step_id = rec.get("id", "?")
        label = rec.get("label", "")
        mech = rec.get("mechanism", "?")
        cmd = rec.get("cmd", "")
        captured = rec.get("captured", {})
        lines.append(f"# step: {step_id}  [{mech}]  {label}")
        lines.append(cmd)
        if captured:
            for k, v in captured.items():
                lines.append(f"# captured: {k}={v!r}")
        lines.append("")

    script = "\n".join(lines)
    print(script)
    return QaOutcome(ok=True, message="", data={"script": script})


# ---------------------------------------------------------------------------
# validate
# ---------------------------------------------------------------------------


def cmd_validate(
    plan_file: Path,
    spec_dir: Path | None = None,
    *,
    root: Path | None = None,
) -> QaOutcome:
    """Validate a `qa_plan.py` without executing it."""
    root = (root or Path.cwd()).resolve()
    resolved_plan = plan_file if plan_file.is_absolute() else root / plan_file
    if not resolved_plan.is_file():
        return QaOutcome(
            ok=False,
            message=f"plan file not found: {resolved_plan}",
            status="invalid",
        )

    resolved_spec = resolve_spec_dir(resolved_plan, spec_dir, root)
    document, problems = load_plan(resolved_plan, resolved_spec, root)
    # `load_plan` hands back a document exactly when it found nothing to report, so the
    # deeper validation runs on a document that is there rather than on a `None` the
    # short-circuit happened to skip.
    if document is not None and not problems:
        problems = validate_v2(document)
    if problems:
        msg = "Plan validation failed:\n" + "\n".join(f"  - {p}" for p in problems)
        return QaOutcome(
            ok=False,
            message=msg,
            data={"problems": problems},
            status="invalid",
        )
    return QaOutcome(ok=True, message="Plan is valid.", data={})


# ---------------------------------------------------------------------------
# run (batch)
# ---------------------------------------------------------------------------


def cmd_run(
    plan_file: Path,
    spec_dir: Path | None = None,
    *,
    stop_on_fail: bool = False,
    only: list[str] | None = None,
    out_dir: str = "qa",
    sandboxed: bool = False,
    root: Path,
) -> QaOutcome:
    """Execute a `qa_plan.py` in batch mode.

    The plan is validated first, then executed: start → scenarios → stop. Returns a
    PASS/FAIL verdict.

    ``only`` and ``out_dir`` are the dry run: a subset of the scenarios, written somewhere
    other than ``qa/`` and producing no ``qa-evidence.json``.

    ``sandboxed`` runs each scenario in a container that has no repository on disk, so a
    scenario cannot rerun a unit suite and file the exit code as behavioral evidence.
    """
    resolved_plan = plan_file if plan_file.is_absolute() else root / plan_file
    resolved_spec = resolve_spec_dir(resolved_plan, spec_dir, root)
    validate_result = cmd_validate(resolved_plan, resolved_spec, root=root)
    if not validate_result.ok:
        return validate_result

    document, problems = load_plan(resolved_plan, resolved_spec, root)
    if problems or document is None:
        return QaOutcome(
            ok=False,
            message="Plan loading failed:\n" + "\n".join(problems),
            data={"problems": problems},
            status="invalid",
        )
    status, message, data = run_v2_plan(
        document,
        root=root,
        stop_on_fail=stop_on_fail,
        only=only,
        qa_dirname=out_dir,
        sandboxed=sandboxed,
    )
    return QaOutcome(
        ok=status == "passed",
        message=message,
        data=data,
        status=status,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _read_log(log_path: Path) -> list[dict]:
    records = []
    for line in log_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return records
