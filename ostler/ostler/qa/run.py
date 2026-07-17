"""Orchestrate all `ostler qa` subcommands.

See QA-RUN.md for full design. This module translates parsed CLI args into
session operations and produces human-readable / JSON output.
"""

from __future__ import annotations

import json
import os
import signal
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from ostler.qa.session import QaSession, RUN_LOG, _expand
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


def cmd_start(
    run_id: str,
    story: str,
    spec_dir: Path,
    *,
    env: dict[str, str] | None = None,
    daemons: list[tuple[str, str, str | None]] | None = None,
    secret_values: dict[str, str] | None = None,
) -> QaOutcome:
    """Open a new QA session and optionally start background daemons.

    *daemons*: list of (name, cmd, ready_check_url) tuples.
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
    for name, cmd, ready_check in daemons or []:
        try:
            pid = session.start_daemon(name, cmd, ready_check=ready_check)
            pids[name] = pid
        except (OSError, TimeoutError) as exc:
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
    """Validate a qa-plan.yml file without executing it."""
    root = (root or Path.cwd()).resolve()
    resolved_plan = plan_file if plan_file.is_absolute() else root / plan_file
    if not resolved_plan.is_file():
        return QaOutcome(
            ok=False,
            message=f"plan file not found: {resolved_plan}",
            status="invalid",
        )

    try:
        plan = yaml.safe_load(resolved_plan.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        return QaOutcome(ok=False, message=f"YAML parse error: {exc}", status="invalid")

    resolved_spec = resolve_spec_dir(resolved_plan, spec_dir, root)
    if isinstance(plan, dict) and plan.get("version") == 2:
        document, load_problems = load_plan(resolved_plan, resolved_spec, root)
        problems = load_problems or validate_v2(document)  # type: ignore[arg-type]
    else:
        problems = _validate_plan(plan, resolved_spec)
        problems.extend(_validate_v1_files(plan, resolved_plan, resolved_spec))
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
    root: Path,
) -> QaOutcome:
    """Execute a qa-plan.yml in batch mode.

    The plan is validated first, then executed: start → steps+asserts → stop.
    Returns PASS/FAIL verdict.
    """
    # Validate first
    resolved_plan = plan_file if plan_file.is_absolute() else root / plan_file
    resolved_spec = resolve_spec_dir(resolved_plan, spec_dir, root)
    validate_result = cmd_validate(resolved_plan, resolved_spec, root=root)
    if not validate_result.ok:
        return validate_result

    try:
        plan = yaml.safe_load(resolved_plan.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        return QaOutcome(ok=False, message=f"YAML parse error: {exc}", status="invalid")

    if plan.get("version") == 2:
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
        )
        return QaOutcome(
            ok=status == "passed",
            message=message,
            data=data,
            status=status,
        )

    # Resolve spec_dir from plan or argument
    spec_dir = resolved_spec

    run_id = str(plan.get("run_id", ""))
    story = str(plan.get("story", ""))
    env = {k: str(v) for k, v in plan.get("env", {}).items()}
    secret_values: dict[str, str] = {}
    for name, declaration in plan.get("secrets", {}).items():
        env_name = declaration["from_env"]
        if env_name not in os.environ:
            return QaOutcome(
                ok=False,
                message=f"QA run blocked: secret '{name}' requires {env_name}",
                status="blocked",
            )
        secret_values[name] = os.environ[env_name]
    variables = {
        f"input.{name}": str((spec_dir / str(path)).resolve())
        for name, path in plan.get("inputs", {}).items()
    }
    background = plan.get("background", [])

    # Wipe the qa/ directory for a clean run: removes the stale session file,
    # the previous run log, and all captured evidence from prior executions.
    # A fresh qa/ is created immediately after so subsequent mkdir calls are no-ops.
    qa_dir = spec_dir / "qa"
    if qa_dir.exists():
        import shutil

        shutil.rmtree(qa_dir)
    qa_dir.mkdir(parents=True, exist_ok=True)
    (spec_dir / "qa-evidence.json").unlink(missing_ok=True)

    # Build daemon list
    daemons = [
        (
            d["name"],
            _expand(
                d["cmd"],
                {},
                env,
                variables=variables,
                secrets=secret_values,
                run_id=run_id,
                story=story,
            ),
            d.get("ready_check"),
        )
        for d in background
    ]

    start_result = cmd_start(
        run_id,
        story,
        spec_dir,
        env=env,
        daemons=daemons,
        secret_values=secret_values,
    )
    if not start_result.ok:
        return start_result

    try:
        session = QaSession.open(spec_dir)
    except FileNotFoundError as exc:
        return QaOutcome(ok=False, message=str(exc))
    session.configure_secrets(secret_values)

    overall_pass = True
    prev_sigterm = signal.signal(signal.SIGTERM, _raise_keyboard_interrupt)
    summary: dict[str, Any] = {}
    try:
        for step in plan.get("steps", []):
            step_id = str(step.get("id", ""))
            label = str(step.get("label", ""))
            mechanism = str(step.get("mechanism", ""))
            raw_cmd = str(step.get("cmd", ""))
            out = step.get("out")
            capture_map: list[tuple[str, str]] = [
                (k, v) for k, v in (step.get("capture") or {}).items()
            ]

            # Run the step
            try:
                record = session.run_step(
                    step_id,
                    label,
                    mechanism,
                    raw_cmd,
                    captures=capture_map,
                    out_path=str(out) if out else None,
                    allow_fail=True,
                    timeout=float(step.get("timeout", 60)),
                    cwd=root,
                    variables=variables,
                )
            except (ValueError, RuntimeError) as exc:
                overall_pass = False
                print(f"[ERROR] step '{step_id}': {exc}", file=sys.stderr)
                if stop_on_fail:
                    break
                continue

            step_failed = record.get("exit_code", 0) != 0

            # Run inline assertions
            inline_passed = _run_inline_asserts(session, step, record, root)
            if not inline_passed:
                overall_pass = False
                if stop_on_fail:
                    break
            elif step_failed:
                overall_pass = False
                if stop_on_fail:
                    break
    finally:
        # Always stop daemons and write the closing summary here — even if the loop
        # above was interrupted (Ctrl+C/SIGTERM, now normalized to KeyboardInterrupt
        # by the handler above) or raised an unexpected exception. An orphaned
        # background daemon (screen recorder, event tail) left running in its own
        # detached process group is worse than an early, clean stop.
        signal.signal(signal.SIGTERM, prev_sigterm)
        summary = session.close(status="passed" if overall_pass else "failed")
        session.finalize_log_artifact()
    fail_count = summary.get("fail_count", 0)
    step_count = summary.get("step_count", 0)
    pass_count = summary.get("pass_count", 0)

    final_ok = overall_pass and fail_count == 0
    verdict = "PASS" if final_ok else "FAIL"
    return QaOutcome(
        ok=final_ok,
        message=f"QA run {verdict}: {pass_count} asserts passed, "
        f"{fail_count} failed, {step_count} steps",
        data=summary,
        status="passed" if final_ok else "failed",
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


def _validate_plan(plan: Any, spec_dir: Path | None) -> list[str]:
    if not isinstance(plan, dict):
        return ["plan must be a YAML mapping"]
    problems: list[str] = []
    if not plan.get("run_id"):
        problems.append("'run_id' is required and must be non-empty")
    if not plan.get("story"):
        problems.append("'story' is required and must be non-empty")

    valid_mechs = {"live", "synthetic", "fixture"}
    seen_captures: set[str] = set()
    version = plan.get("version", 1)
    if version != 1:
        problems.append("'version' must be 1 for a command steps plan")
    steps = plan.get("steps", [])
    if not isinstance(steps, list):
        problems.append("'steps' must be a list")
        return problems

    import re

    _ENTROPY_RE = re.compile(
        r"\$\(date\b"  # $(date ...)
        r"|\$RANDOM\b"  # $RANDOM
        r"|\$\(uuidgen\b"  # $(uuidgen)
        r"|\$\(openssl\s+rand"  # $(openssl rand ...)
        r"|\$\(python.*uuid"  # $(python -c '...uuid...')
    )

    seen_steps: set[str] = set()
    for i, step in enumerate(steps):
        if not isinstance(step, dict):
            problems.append(f"steps[{i}] must be a mapping")
            continue
        label = f"steps[{i}] (id={step.get('id', '?')})"
        if not step.get("id"):
            problems.append(f"{label}: 'id' is required")
        elif step["id"] in seen_steps:
            problems.append(f"{label}: duplicate step id '{step['id']}'")
        seen_steps.add(str(step.get("id", "")))
        if not step.get("mechanism"):
            problems.append(
                f"{label}: 'mechanism' is required (live | synthetic | fixture)"
            )
        elif step["mechanism"] not in valid_mechs:
            problems.append(f"{label}: mechanism must be one of {sorted(valid_mechs)}")
        if not step.get("cmd"):
            problems.append(f"{label}: 'cmd' is required")
        timeout = step.get("timeout", 60)
        if not isinstance(timeout, (int, float)) or timeout <= 0:
            problems.append(f"{label}: timeout must be positive")
        # Forward-reference check for {{key}} in cmd
        mech = step.get("mechanism", "")
        cmd_str = str(step.get("cmd", ""))
        refs = re.findall(r"\{\{([^}]+)\}\}", cmd_str)
        for ref in refs:
            ref = ref.strip()
            if ref.startswith(("env.", "input.", "secret.")) or ref in ("run_id", "story"):
                continue
            if ref not in seen_captures:
                problems.append(
                    f"{label}: cmd references '{{{{{{ref}}}}}}'  which is not yet captured "
                    f"by any prior step"
                )
        # Detect time/entropy shell expressions in non-fixture steps.
        # Expressions like $(date +%s), $RANDOM, $(uuidgen) generate a different
        # value on every execution. If the same value is needed across multiple
        # steps (a device ID used in both login and logout, a seed token in a
        # payload and a correlation query), it must come from a 'fixture' step with
        # a capture: block — not re-generated inline. This is a hard error because
        # the login/logout using different $(date +%s) device IDs creates two
        # independent sessions: the logout never closes the session the login opened.
        if mech != "fixture" and _ENTROPY_RE.search(cmd_str):
            problems.append(
                f"{label}: cmd contains a time/entropy expression ($(date), $RANDOM, "
                f"$(uuidgen), etc.) in a '{mech}' step. These re-evaluate on every "
                f"execution — if this value must be stable across multiple steps, "
                f"generate it once in a 'fixture' step with a capture: block and "
                f"reference it as {{{{key}}}} here. Example:\n"
                f"    - id: gen-device-id\\n"
                f"      mechanism: fixture\\n"
                f'      cmd: printf \'{{{{"device_id":"prefix-%s"}}}}\' "$(date +%s)"\\n'
                f"      capture:\\n"
                f"        device_id: $.device_id"
            )
        # Validate out: path is under spec_dir (no traversal)
        out = step.get("out")
        if out and spec_dir:
            out_path = spec_dir / str(out)
            try:
                out_path.resolve().relative_to(spec_dir.resolve())
            except ValueError:
                problems.append(f"{label}: 'out' path escapes spec_dir: {out!r}")
        # Collect captures
        for cap_key in step.get("capture") or {}:
            seen_captures.add(cap_key)
    return problems


def _validate_v1_files(plan: Any, plan_file: Path, spec_dir: Path) -> list[str]:
    if not isinstance(plan, dict):
        return []
    problems: list[str] = []
    if plan_file.is_relative_to(spec_dir / "qa"):
        problems.append("qa-plan.yml cannot live under disposable qa/")
    inputs = plan.get("inputs", {})
    if not isinstance(inputs, dict):
        problems.append("'inputs' must be a mapping")
    else:
        for name, raw in inputs.items():
            path = (spec_dir / str(raw)).resolve()
            if not path.is_relative_to(spec_dir.resolve()):
                problems.append(f"input '{name}' escapes spec_dir")
            elif path.is_relative_to((spec_dir / "qa").resolve()):
                problems.append(f"input '{name}' is under disposable qa/")
            elif not path.is_file():
                problems.append(f"input '{name}' does not exist: {raw}")
    secrets = plan.get("secrets", {})
    if not isinstance(secrets, dict):
        problems.append("'secrets' must be a mapping")
    else:
        for name, declaration in secrets.items():
            if not isinstance(declaration, dict) or set(declaration) != {"from_env"}:
                problems.append(f"secret '{name}' must contain only 'from_env'")
    return problems


def _run_inline_asserts(
    session: QaSession,
    step: dict,
    record: dict,
    root: Path,
) -> bool:
    """Run inline assertion keys on a step.  Returns True if all pass."""
    step_id = str(step.get("id", "unknown"))

    # Prefer the in-memory stdout (available during `ostler qa run`).
    # Fall back to reading from stdout_file when replaying records from disk.
    stdout_text: str = record.get("_stdout", "")
    if not stdout_text:
        stdout_file = record.get("stdout_file")
        if stdout_file:
            try:
                stdout_text = Path(stdout_file).read_text(
                    encoding="utf-8", errors="replace"
                )
            except OSError:
                pass

    all_pass = True

    # assert_contains: step stdout contains the literal string
    if "assert_contains" in step:
        needle = _expand(str(step["assert_contains"]), session.captures, session.env)
        passed = needle in stdout_text
        _id = f"{step_id}_assert_contains"
        _, _ = session.run_assert(
            _id,
            f"stdout contains {needle!r}",
            "field_equal",
            {"a": needle if passed else "NOT_FOUND", "b": needle},
            root=root,
        )
        if not passed:
            all_pass = False

    # expect_http: last stdout line is the expected HTTP status code
    if "expect_http" in step:
        expected = int(step["expect_http"])
        actual = record.get("http_status")
        passed = actual == expected
        _id = f"{step_id}_expect_http"
        _, _ = session.run_assert(
            _id,
            f"HTTP status == {expected}",
            "http_status",
            {"expected": expected, "actual": actual},
            root=root,
        )
        if not passed:
            all_pass = False

    # assert_count: stdout parsed as JSON array has exactly N elements
    if "assert_count" in step:
        expected_count = int(step["assert_count"])
        try:
            items = json.loads(stdout_text)
            actual_count = len(items) if isinstance(items, list) else -1
        except (json.JSONDecodeError, ValueError):
            actual_count = -1
        passed = actual_count == expected_count
        _id = f"{step_id}_assert_count"
        _, _ = session.run_assert(
            _id,
            f"event count == {expected_count}",
            "field_equal",
            {"a": str(actual_count), "b": str(expected_count)},
            root=root,
        )
        if not passed:
            all_pass = False

    # cloudwatch_confirm: run filter-log-events
    if "cloudwatch_confirm" in step:
        cw = step["cloudwatch_confirm"]
        params = {
            "log_group": cw.get("log_group", ""),
            "filter": _expand(str(cw.get("filter", "")), session.captures, session.env),
            "window_seconds": int(cw.get("window_seconds", 3600)),
            "min_matches": int(cw.get("min_matches", 1)),
        }
        _id = f"{step_id}_cloudwatch"
        passed, _ = session.run_assert(
            _id,
            f"CloudWatch confirms {params['filter']!r} in {params['log_group']}",
            "cloudwatch_filter",
            params,
            root=root,
        )
        if not passed:
            all_pass = False

    return all_pass
