"""QA session state: NDJSON run log + capture store + daemon PID registry.

The session file (`qa-session.json`) is the mutable side-car written by
`ostler qa start/step/stop`; it stores runtime state (captures, PIDs) that must
survive across separate CLI invocations within the same run.

The run log (`qa-run.ndjson`) is append-only and never rewritten by ostler.
"""

from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import time
import urllib.error
import urllib.request
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ostler.qa.manifest import RunManifest

SESSION_FILE = "qa-session.json"
RUN_LOG = "qa-run.ndjson"

_MECHS = {"live", "synthetic", "fixture"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _spec_dir_from(spec_arg: str | None, root: Path) -> Path:
    if not spec_arg:
        raise ValueError("--spec is required when no session is open")
    p = Path(spec_arg)
    return p if p.is_absolute() else root / p


# ---------------------------------------------------------------------------
# Public session operations
# ---------------------------------------------------------------------------


class QaSession:
    """Thin wrapper around the on-disk session + log files."""

    def __init__(self, spec_dir: Path) -> None:
        self.spec_dir = spec_dir
        self.qa_dir = spec_dir / "qa"
        self._session_path = self.qa_dir / SESSION_FILE
        self._log_path = self.qa_dir / RUN_LOG
        self._data: dict[str, Any] = {}
        self._secret_values: dict[str, str] = {}
        self._manifest: RunManifest | None = None

    # -- load / save ---------------------------------------------------------

    @classmethod
    def open(cls, spec_dir: Path) -> "QaSession":
        """Load an existing session; raise if none exists."""
        s = cls(spec_dir)
        if not s._session_path.is_file():
            raise FileNotFoundError(
                f"No open QA session at {s._session_path}. Run `ostler qa start` first."
            )
        s._data = json.loads(s._session_path.read_text(encoding="utf-8"))
        s._manifest = RunManifest(spec_dir, str(s._data["run_id"]))
        if s._manifest.path.is_file():
            try:
                s._manifest.data = json.loads(s._manifest.path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                pass
        return s

    @classmethod
    def create(
        cls,
        spec_dir: Path,
        run_id: str,
        story: str,
        env: dict[str, str],
        *,
        secret_values: dict[str, str] | None = None,
    ) -> "QaSession":
        """Create a fresh session file; raise if one is already open."""
        s = cls(spec_dir)
        if s._session_path.is_file():
            raise FileExistsError(
                f"A QA session is already open at {s._session_path}. "
                "Run `ostler qa stop` first."
            )
        s.qa_dir.mkdir(parents=True, exist_ok=True)
        # `steps/` and `asserts/` up front, not on first use. ostler writes into both itself
        # — the `out:` sidecar and every assertion result — and creates each parent as it
        # goes, so it never needed them early for its own sake. But `qa/steps/` is also a
        # layout ostler *publishes*: plans are written to redirect into it directly, with a
        # `curl -o …/qa/steps/create-fixture.json` that runs before ostler has written any
        # sidecar and so before anything has made the directory. curl cannot create it and
        # exits 23, the capture that step was to feed comes back empty, and the request that
        # reads the capture goes somewhere unrelated and gets a plausible wrong answer — a
        # 404 that reads as a product defect rather than as a missing directory. It bites
        # only the first run against a fresh spec dir, which is the run least likely to be
        # believed. Publishing the layout means creating it.
        (s.qa_dir / "steps").mkdir(exist_ok=True)
        (s.qa_dir / "asserts").mkdir(exist_ok=True)
        s._data = {
            "run_id": run_id,
            "story": story,
            "env": env,
            "captures": {},  # key → captured string value from step --capture
            "daemons": [],  # [{name, pid, cmd, log_file}]
            "step_count": 0,
            "assert_count": 0,
            "pass_count": 0,
            "fail_count": 0,
            "started_monotonic": time.monotonic(),
        }
        s._secret_values = secret_values or {}
        s._manifest = RunManifest(spec_dir, run_id)
        s._manifest.write()
        s._save()
        return s

    def configure_secrets(self, secret_values: dict[str, str]) -> None:
        """Attach runtime-only secret values without persisting them to session state."""
        self._secret_values = secret_values

    def expand(self, template: str, variables: dict[str, str] | None = None) -> str:
        return _expand(
            template,
            self.captures,
            self.env,
            variables=variables,
            secrets=self._secret_values,
            run_id=self.run_id,
            story=self.story,
        )

    def symbolic_driver_value(
        self, template: str, variables: dict[str, str] | None = None
    ) -> str:
        for name in self._secret_values:
            template = template.replace(
                f"{{{{secret.{name}}}}}", f"${{OSTLER_SECRET_{name.upper()}}}"
            )
        return _expand(
            template,
            self.captures,
            self.env,
            variables=variables,
            secrets={},
            run_id=self.run_id,
            story=self.story,
        )

    def driver_secret_env(self) -> dict[str, str]:
        return {
            f"OSTLER_SECRET_{name.upper()}": value
            for name, value in self._secret_values.items()
        }

    def _save(self) -> None:
        self._session_path.write_text(
            json.dumps(self._data, indent=2) + "\n", encoding="utf-8"
        )

    # -- append-only log -----------------------------------------------------

    def _append(self, record: dict[str, Any]) -> None:
        record["ts"] = _now()
        record["offset_ms"] = round(
            (time.monotonic() - self._data.get("started_monotonic", time.monotonic())) * 1000
        )
        # Strip private in-memory keys before writing to the append-only log.
        log_record = {
            k: _redact_value(v, self._secret_values.values())
            for k, v in record.items()
            if not k.startswith("_")
        }
        with self._log_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(log_record) + "\n")
            fh.flush()
            os.fsync(fh.fileno())

    def append(self, record: dict[str, Any]) -> None:
        """Append a driver-produced action, recording, or artifact record."""
        self._append(record)

    def offset_ms(self) -> int:
        return round(
            (time.monotonic() - self._data.get("started_monotonic", time.monotonic())) * 1000
        )

    def register_artifact(
        self,
        path: Path,
        *,
        kind: str,
        scenario: str = "",
        target: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if self._manifest is None:
            self._manifest = RunManifest(self.spec_dir, self.run_id)
        entry = self._manifest.register(
            path,
            kind=kind,
            scenario=scenario,
            target=target,
            metadata=metadata,
        )
        self._append({"kind": "artifact", **entry})
        return entry

    def finalize_log_artifact(self) -> None:
        """Hash the closed ledger without appending after its terminal record."""
        if self._manifest is None:
            self._manifest = RunManifest(self.spec_dir, self.run_id)
        self._manifest.register(self._log_path, kind="run-ledger")

    # -- public accessors ----------------------------------------------------

    @property
    def run_id(self) -> str:
        return self._data["run_id"]

    @property
    def story(self) -> str:
        return self._data["story"]

    @property
    def env(self) -> dict[str, str]:
        return self._data.get("env", {})

    @property
    def captures(self) -> dict[str, str]:
        return self._data.get("captures", {})

    def get_capture(self, key: str) -> str:
        return self._data.get("captures", {}).get(key, "")

    def set_capture(self, key: str, value: str) -> None:
        self._data.setdefault("captures", {})[key] = value

    # -- session_start -------------------------------------------------------

    def write_session_start(self) -> None:
        self._append(
            {
                "kind": "session_start",
                "run_id": self.run_id,
                "story": self.story,
                "env": self.env,
            }
        )

    # -- daemon management ---------------------------------------------------

    def start_daemon(
        self,
        name: str,
        cmd: str,
        *,
        ready_check: str | Mapping[str, Any] | None = None,
        timeout: float = 30,
        cwd: Path | None = None,
    ) -> int:
        """Launch a daemon subprocess, store its PID, write daemon_start record.

        stdout/stderr are tee'd to ``qa/daemon-<name>.log``.
        If *ready_check* is given, ostler polls it before returning — an HTTP URL for a
        200, or a ``{cmd, assert_contains}`` mapping for a command whose stdout says so
        (see `_poll_ready`). Returns the PID.
        """
        log_file = self.qa_dir / f"daemon-{name}.log"
        with log_file.open("wb") as lf:
            proc = subprocess.Popen(
                cmd,
                shell=True,  # noqa: S603 — agent-controlled command, explicit user intent
                executable="/bin/bash",
                stdout=lf,
                stderr=subprocess.STDOUT,
                start_new_session=True,
                cwd=cwd or self.spec_dir,
            )
        pid = proc.pid
        self._data.setdefault("daemons", []).append(
            {"name": name, "pid": pid, "cmd": cmd, "log_file": str(log_file)}
        )
        self._save()
        self._append(
            {
                "kind": "daemon_start",
                "name": name,
                "pid": pid,
                "cmd": _redact(cmd, self._secret_values.values()),
                "log_file": str(log_file),
                "ready_check": ready_check,
            }
        )
        if ready_check:
            # The same cwd the daemon got: a check like `curl … | grep` is as likely to be
            # written relative to the service's directory as its start command is. `proc`
            # and the log go too, so a daemon that dies on startup is reported as dead with
            # what it printed, rather than as a service that took too long — see `_poll_ready`.
            _poll_ready(
                ready_check,
                timeout=timeout,
                cwd=cwd or self.spec_dir,
                proc=proc,
                log_file=log_file,
            )
        return pid

    def stop_all_daemons(self) -> None:
        """Kill all running daemons and write daemon_stop records."""
        for d in self._data.get("daemons", []):
            pid, name = d["pid"], d["name"]
            exit_code = _kill_pid(pid)
            self._append(
                {
                    "kind": "daemon_stop",
                    "name": name,
                    "pid": pid,
                    "exit_code": exit_code,
                }
            )
        self._data["daemons"] = []
        self._save()

    # -- step ----------------------------------------------------------------

    def run_step(
        self,
        step_id: str,
        label: str,
        mechanism: str,
        cmd: str,
        *,
        captures: list[tuple[str, str]] | None = None,
        out_path: str | None = None,
        allow_fail: bool = False,
        timeout: float | None = None,
        cwd: Path | None = None,
        variables: dict[str, str] | None = None,
        scenario: str = "",
        driver: str = "command",
        action: int | None = None,
        covers: list[str] | None = None,
    ) -> dict[str, Any]:
        """Execute *cmd* in a subprocess and append a ``step`` record.

        *captures*: list of (key, jq_path) — extract from stdout JSON.
        *out_path*: write stdout verbatim to this path as a sidecar file.
        Returns the record dict.
        """
        if mechanism not in _MECHS:
            raise ValueError(
                f"mechanism must be one of {sorted(_MECHS)}, got '{mechanism}'"
            )

        # Substitute {{key}} from capture store
        expanded_cmd = _expand(
            cmd,
            self.captures,
            self.env,
            variables=variables,
            secrets=self._secret_values,
            run_id=self.run_id,
            story=self.story,
        )

        try:
            stdout_raw, stderr_raw, exit_code = _run_command(
                expanded_cmd,
                timeout=timeout,
                cwd=cwd or self.spec_dir,
                env={**os.environ, **self._secret_values},
            )
            timed_out = False
        except subprocess.TimeoutExpired as exc:
            stdout_raw = _as_bytes(exc.stdout)
            stderr_raw = _as_bytes(exc.stderr)
            exit_code = 124
            timed_out = True
        # A step whose cmd redirects its own stdout — `curl -w '%{http_code}' … > qa/steps/x.txt`,
        # or an `-o`/`-D` aimed at the path it also declares as `out:` — leaves nothing on the
        # pipe, and two things then went wrong at once, both reading as product defects. The
        # sidecar write landed 0 bytes on top of the bytes the command had just produced, so the
        # assertion re-reading that file compared a status code against an empty string. And the
        # in-band `%{http_code}` parse saw an empty capture, so `expect_http` compared None to
        # 200. One run reported three acceptance criteria broken while its own ledger recorded
        # the correct 404/201/302 for every request.
        #
        # `qa/` is wiped at session start, so a non-empty file at that path is this run's own
        # output and can only have come from this command. The command redirected its stdout
        # there, which makes that file the step's stdout: read it back and treat it as such,
        # rather than overwrite it with the emptiness the redirect left behind.
        resolved_out: Path | None = _resolve_out(out_path, self.spec_dir) if out_path else None
        out_kept: bool = False
        if resolved_out is not None:
            resolved_out.parent.mkdir(parents=True, exist_ok=True)
            if not stdout_raw and resolved_out.is_file() and resolved_out.stat().st_size:
                stdout_raw = resolved_out.read_bytes()
                out_kept = True

        http_status: int | None = _extract_http_status(stdout_raw)
        body_raw = _without_http_status(stdout_raw) if http_status is not None else stdout_raw
        if http_status is None:
            http_status = _status_from_header_dump(stdout_raw)
        stdout_safe = _redact_bytes(body_raw, self._secret_values.values())
        stderr_safe = _redact_bytes(stderr_raw, self._secret_values.values())

        # Write sidecar
        abs_out: str | None = None
        if resolved_out is not None:
            if not out_kept:
                resolved_out.write_bytes(stdout_safe)
            abs_out = str(resolved_out)
            self.register_artifact(
                resolved_out, kind="command-output", scenario=scenario, target=driver
            )

        # Apply jq captures
        captured: dict[str, str] = {}
        if captures:
            try:
                data = json.loads(body_raw.decode("utf-8", errors="replace"))
            except (json.JSONDecodeError, ValueError):
                data = None
            for key, jq_path in captures:
                value = _jq_extract(data, jq_path)
                if value is not None:
                    self.set_capture(key, value)
                    captured[key] = value
        if captures:
            self._save()

        self._data["step_count"] = self._data.get("step_count", 0) + 1
        record: dict[str, Any] = {
            "kind": "step",
            "id": step_id,
            "label": label,
            "mechanism": mechanism,
            "cmd": cmd,
            "exit_code": exit_code,
            "driver": driver,
        }
        if scenario:
            record["scenario"] = scenario
        if action is not None:
            record["action"] = action
        if covers:
            record["covers"] = covers
        if timed_out:
            record["timed_out"] = True
        if http_status is not None:
            record["http_status"] = http_status
        if abs_out:
            record["stdout_file"] = abs_out
        if out_kept:
            record["stdout_file_written_by_cmd"] = True
        if captured:
            record["captured"] = captured
        if stderr_safe:
            record["stderr"] = stderr_safe.decode("utf-8", errors="replace")[:2000]

        # Keep decoded stdout in-memory for inline assertion checks (not written to log).
        # Stored under a private key so _append can strip it.
        record["_stdout"] = stdout_safe.decode("utf-8", errors="replace")
        record["_stdout_actual"] = body_raw.decode("utf-8", errors="replace")

        self._append(record)

        if not allow_fail and exit_code != 0:
            raise RuntimeError(
                f"step '{step_id}' exited {exit_code}: "
                + stdout_safe.decode("utf-8", errors="replace")[:500]
            )
        return record

    # -- assert --------------------------------------------------------------

    def run_assert(
        self,
        assert_id: str,
        label: str,
        check_type: str,
        params: dict[str, Any],
        *,
        root: Path,
        scenario: str = "",
        driver: str = "command",
        action: int | None = None,
        covers: list[str] | None = None,
    ) -> tuple[bool, dict[str, Any]]:
        """Execute a named check, write raw result, append assert record.

        Returns (passed, record).
        """
        raw_out_path = self.qa_dir / "asserts" / f"{assert_id}.json"
        raw_out_path.parent.mkdir(parents=True, exist_ok=True)

        passed, raw_result = _execute_check(
            check_type, params, self.captures, self.env, root
        )

        raw_out_path.write_text(
            json.dumps(_redact_value(raw_result, self._secret_values.values()), indent=2)
            + "\n",
            encoding="utf-8",
        )
        self.register_artifact(
            raw_out_path, kind="assertion-result", scenario=scenario, target=driver
        )

        self._data["assert_count"] = self._data.get("assert_count", 0) + 1
        if passed:
            self._data["pass_count"] = self._data.get("pass_count", 0) + 1
        else:
            self._data["fail_count"] = self._data.get("fail_count", 0) + 1
        self._save()

        record: dict[str, Any] = {
            "kind": "assert",
            "id": assert_id,
            "label": label,
            "check": check_type,
            "params": params,
            "raw_result_file": str(raw_out_path),
            "result": "PASS" if passed else "FAIL",
            "driver": driver,
        }
        if scenario:
            record["scenario"] = scenario
        if action is not None:
            record["action"] = action
        if covers:
            record["covers"] = covers
        # Attach summary fields from raw result
        for key in ("match_count", "count", "value", "expected"):
            if key in raw_result:
                record[key] = raw_result[key]

        self._append(record)
        return passed, record

    # -- stop ----------------------------------------------------------------

    def close(self, *, status: str | None = None) -> dict[str, Any]:
        """Write session_stop summary, clean up session file, return summary."""
        self.stop_all_daemons()
        summary = {
            "kind": "session_stop",
            "run_id": self.run_id,
            "step_count": self._data.get("step_count", 0),
            "assert_count": self._data.get("assert_count", 0),
            "pass_count": self._data.get("pass_count", 0),
            "fail_count": self._data.get("fail_count", 0),
        }
        summary["status"] = status or (
            "passed" if summary["fail_count"] == 0 else "failed"
        )
        self._append(summary)
        # Remove the mutable session file so a new start can proceed
        try:
            self._session_path.unlink()
        except FileNotFoundError:
            pass
        return summary


# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------


def _run_command(
    cmd: str,
    *,
    timeout: float | None = None,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
) -> tuple[bytes, bytes, int]:
    result = subprocess.run(
        cmd,
        shell=True,  # noqa: S603 — agent-authored command, explicit user intent
        executable="/bin/bash",
        capture_output=True,
        timeout=timeout,
        cwd=cwd,
        env=env,
        start_new_session=True,
    )
    return result.stdout, result.stderr, result.returncode


def _extract_http_status(stdout: bytes) -> int | None:
    """Detect a trailing ``\\n<http_code>`` appended by curl ``-w '\\n%{http_code}'``."""
    try:
        text = stdout.decode("utf-8", errors="replace").rstrip("\n")
        last_line = text.rsplit("\n", 1)[-1].strip()
        if last_line.isdigit() and 100 <= int(last_line) <= 599:
            return int(last_line)
    except (ValueError, IndexError):
        pass
    return None


_HTTP_STATUS_LINE = re.compile(r"^HTTP/\d(?:\.\d)?\s+(\d{3})\b", re.MULTILINE)


def _status_from_header_dump(stdout: bytes) -> int | None:
    """Read the status out of a curl ``-D`` header dump.

    ``-w '\\n%{http_code}'`` is one of two ways a plan hands ostler a status code, and it
    was the only one ostler could read. The other is ``-D <file>``, which writes the whole
    response head — status line included — and is what an agent reaches for when it wants
    the headers for anything else as well. A plan that used it got ``http_status = None``
    and an ``expect_http`` failure comparing None to 201, while the step's own sibling
    assertion pulled the same number out of the same file with ``head -1 | awk '{print $2}'``.
    A run then reports acceptance criteria broken over a status ostler is holding in its hand,
    which is the most expensive kind of wrong answer this runner can give.

    Only consulted when the write-out convention found nothing, so a body that happens to
    begin with ``HTTP/`` can't displace a real trailing code. The *last* status line wins:
    a redirect chain (``-L``) dumps every hop, and the final response is the one the
    expectation is about. Unlike the trailing-code form there is nothing to strip from the
    body afterwards — the status line is part of the head the step asked to keep.
    """
    text = stdout.decode("utf-8", errors="replace")
    matches = _HTTP_STATUS_LINE.findall(text)
    if not matches:
        return None
    code = int(matches[-1])
    return code if 100 <= code <= 599 else None


def _expand(
    template: str,
    captures: dict[str, str],
    env: dict[str, str],
    *,
    variables: dict[str, str] | None = None,
    secrets: dict[str, str] | None = None,
    run_id: str = "",
    story: str = "",
) -> str:
    """Expand ``{{key}}`` and ``{{env.name}}`` substitutions in a command string."""

    def _sub(m: re.Match) -> str:
        token = m.group(1).strip()
        if token.startswith("env."):
            return env.get(token[4:], "")
        if token.startswith("input."):
            return (variables or {}).get(token, "")
        if token.startswith("secret."):
            return (secrets or {}).get(token[7:], "")
        if token == "run_id":
            return run_id
        if token == "story":
            return story
        return captures.get(token, m.group(0))

    return re.sub(r"\{\{([^}]+)\}\}", _sub, template)


def _jq_extract(data: Any, path: str) -> str | None:
    """Extract a value using a simple ``$.<key>`` or ``$.<key>.<key>`` path."""
    if data is None:
        return None
    path = path.lstrip("$").lstrip(".")
    parts = path.split(".")
    cur: Any = data
    for part in parts:
        if not part:
            continue
        if isinstance(cur, dict):
            cur = cur.get(part)
        else:
            return None
        if cur is None:
            return None
    return str(cur) if cur is not None else None


def _resolve_out(out_path: str, spec_dir: Path) -> Path:
    p = Path(out_path)
    resolved = (p if p.is_absolute() else spec_dir / p).resolve()
    try:
        resolved.relative_to(spec_dir.resolve())
    except ValueError as exc:
        raise ValueError(f"output path escapes spec directory: {out_path}") from exc
    return resolved


def _signal_group(pid: int, sig: int) -> bool:
    """Signal ``pid``'s process group; False once the group has nothing left to signal.

    ``ProcessLookupError`` is the portable "it's gone", but it is not the only one.
    On macOS/BSD, a group whose members have all exited but not yet been reaped is
    still a group — ``killpg`` answers **EPERM**, not ESRCH, because a zombie has no
    credentials to check the signal against. Linux answers ESRCH (or succeeds), which
    is why a `ProcessLookupError`-only guard passes there and, here, escaped out of
    teardown and failed the whole QA run over a daemon that had already stopped.

    Reading EPERM as "gone" is the safe direction: these are processes this session
    itself spawned, so the alternative reading — someone else's process group reusing
    the pid — is one we could not signal anyway.
    """
    try:
        os.killpg(pid, sig)
    except (ProcessLookupError, PermissionError):
        return False
    return True


def _kill_pid(pid: int) -> int:
    """Escalate SIGINT -> SIGTERM -> SIGKILL; return the effective signal (negated,
    like subprocess) that actually stopped the process.

    SIGINT — the same signal a terminal Ctrl+C sends — is tried first and given a
    real grace window. Well-behaved daemons (scrcpy/ffmpeg finalizing a recording,
    eventbridge-tail flushing its queue) treat SIGINT as "stop and clean up", not
    "die immediately" the way a fast SIGKILL would. SIGTERM and SIGKILL remain as
    escalating fallbacks for a daemon that doesn't respond to SIGINT.
    """
    for sig, grace_seconds in ((signal.SIGINT, 2.0), (signal.SIGTERM, 1.0)):
        if not _signal_group(pid, sig):
            return 0
        deadline = time.monotonic() + grace_seconds
        while time.monotonic() < deadline:
            if not _signal_group(pid, 0):  # check still alive
                return -sig
            time.sleep(0.05)
    if _signal_group(pid, signal.SIGKILL):
        return -signal.SIGKILL
    return 0


def _ready_via_url(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=2) as resp:  # noqa: S310
            return bool(resp.status == 200)
    except (urllib.error.URLError, OSError):
        return False


def _ready_via_cmd(check: Mapping[str, Any], cwd: Path | None) -> bool:
    """Run the check command; ready when it exits 0 and its stdout carries the needle."""
    try:
        done = subprocess.run(  # noqa: S602 — agent-controlled command, explicit user intent
            str(check["cmd"]),
            shell=True,
            executable="/bin/bash",
            capture_output=True,
            timeout=float(check.get("timeout", 10)),
            cwd=cwd,
        )
    except (subprocess.SubprocessError, OSError):
        return False
    if done.returncode != 0:
        return False
    needle = check.get("assert_contains")
    if needle in (None, ""):
        return True
    return str(needle) in done.stdout.decode("utf-8", "replace")


def _log_tail(log_file: Path | None, lines: int = 15) -> str:
    """The last few lines the daemon printed, for pasting into a failure message.

    Best-effort by construction: a daemon that died before its first write leaves an empty
    or absent file, and that is not itself an error worth raising over the failure being
    reported.
    """
    if log_file is None:
        return ""
    try:
        text = log_file.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return ""
    if not text:
        return ""
    return "\n".join(text.splitlines()[-lines:])


def _poll_ready(
    check: str | Mapping[str, Any],
    timeout: float = 30,
    *,
    cwd: Path | None = None,
    proc: subprocess.Popen | None = None,
    log_file: Path | None = None,
) -> None:
    """Poll a daemon's readiness check until it succeeds or *timeout* seconds elapse.

    Two forms, because a URL cannot express every service's notion of "up". A **string**
    is polled for HTTP 200, which is the original contract and covers a health endpoint.
    A **mapping** — `{cmd, assert_contains}`, the plan's own vocabulary for asserting on a
    command's stdout — runs the command instead, and is ready when it exits 0 and its
    output carries the needle.

    The command form is not a convenience. A service whose only route is a `POST` has no
    URL that answers 200 to a `GET`, so the string form cannot probe it at all; the plan
    that surfaced this had to readiness-check with `curl -X POST … -w '%{http_code}'`
    against `assert_contains: 201`. Worse, the mapping used to reach `urlopen` intact,
    which set `.timeout` on it and raised `'dict' object has no attribute 'timeout'` —
    an `AttributeError`, so it escaped the `URLError`/`OSError` guard here and surfaced
    at the top of the run as `0 scenarios` with the cause discarded. The plan validated
    and the reviewer approved it, so the coder loop re-planned a correct plan until its
    rework guard ran out.

    *proc* and *log_file* are what makes a failure here readable. A daemon that cannot start
    at all — the port is taken, the binary does not compile, a migration failed — exits
    within a second, and polling a dead process for the remaining 29 is both a waste and a
    lie: "ready_check timed out" describes a service that was slow, not one that was never
    there. So the loop watches the process too, and reports the exit code and the tail of
    its log the moment it is gone. The case that prompted this reported only ``timed out
    after 30s`` while ``listen tcp :8080: bind: address already in use`` sat unread in the
    daemon log; the agent handling the failure had to go find it, and a gate deciding
    whether to retry could not see it at all. The same tail is attached on a genuine
    timeout, where a daemon still running but not yet answering has usually said why.

    A non-zero exit outranks a *passing* check, which is the subtle half. A readiness probe
    asks "is something answering on this port", never "is it mine" — so when a previous
    run's server is still bound, the daemon that just died on `address already in use`
    leaves an orphan answering `201` and the whole suite runs green against a binary that
    is not the code under test. That is worse than any false failure, because it is silent:
    the observed run recorded ``passed`` with zero runner errors while its own daemon had
    exited one second in. Exit **0** is treated the other way and does not stop the poll —
    that is how a launcher hands off to the service it spawned, so it stays a valid path to
    ready.
    """
    if not isinstance(check, str) and not str(check.get("cmd", "")).strip():
        # Fail on the shape, not by polling it until the timeout: a mapping with no command
        # is never going to become ready, and "timed out after 30s" would hide why.
        raise ValueError(f"daemon ready_check mapping needs a 'cmd': {dict(check)}")
    described = check if isinstance(check, str) else check.get("cmd", check)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        ready = (
            _ready_via_url(check)
            if isinstance(check, str)
            else _ready_via_cmd(check, cwd)
        )
        code = proc.poll() if proc is not None else None
        # A crash outranks a passing check, and that order is the whole point — see the
        # docstring. Exit 0 does not: it is how a launcher hands off, so keep polling.
        if code not in (None, 0):
            raise _daemon_died(code, described, log_file, ready=ready)
        if ready:
            return
        time.sleep(1)
    tail = _log_tail(log_file)
    raise TimeoutError(
        f"daemon ready_check timed out after {timeout}s: {described}"
        + (f"\n--- last lines of {log_file}:\n{tail}" if tail else "")
    )


def _daemon_died(
    code: int | None, described: Any, log_file: Path | None, *, ready: bool
) -> RuntimeError:
    what = (
        "daemon exited with code {code}, but its ready_check passes anyway — something "
        "other than this run's daemon is answering it (a stale server on the same port, "
        "say), and the scenarios below would have tested that instead"
        if ready
        else "daemon exited with code {code} before its ready_check passed"
    ).format(code=code)
    tail = _log_tail(log_file)
    return RuntimeError(
        f"{what}: {described}"
        + (f"\n--- last lines of {log_file}:\n{tail}" if tail else "")
    )


def _without_http_status(stdout: bytes) -> bytes:
    text = stdout.decode("utf-8", errors="replace").rstrip("\n")
    return text.rsplit("\n", 1)[0].encode() if "\n" in text else b""


def _as_bytes(value: bytes | str | None) -> bytes:
    if value is None:
        return b""
    return value if isinstance(value, bytes) else value.encode()


def _redact(text: str, values: Any) -> str:
    for value in sorted((str(v) for v in values if v), key=len, reverse=True):
        text = text.replace(value, "[REDACTED]")
    return text


def _redact_bytes(value: bytes, values: Any) -> bytes:
    return _redact(value.decode("utf-8", errors="replace"), values).encode()


def _redact_value(value: Any, values: Any) -> Any:
    if isinstance(value, str):
        return _redact(value, values)
    if isinstance(value, dict):
        return {key: _redact_value(item, values) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact_value(item, values) for item in value]
    return value


# ---------------------------------------------------------------------------
# Check implementations
# ---------------------------------------------------------------------------


def _execute_check(
    check_type: str,
    params: dict[str, Any],
    captures: dict[str, str],
    env: dict[str, str],
    root: Path,
) -> tuple[bool, dict[str, Any]]:
    """Dispatch to a check implementation; return (passed, raw_result)."""
    if check_type == "cloudwatch_filter":
        return _check_cloudwatch(params, env)
    if check_type == "event_present":
        return _check_event_present(params, captures)
    if check_type == "field_equal":
        return _check_field_equal(params, captures)
    if check_type == "http_status":
        return _check_http_status(params, captures)
    if check_type == "no_duplicate":
        return _check_no_duplicate(params, captures)
    return False, {"error": f"unknown check type '{check_type}'"}


def _check_cloudwatch(params: dict, env: dict[str, str]) -> tuple[bool, dict]:
    log_group = params.get("log_group", "")
    filter_pattern = params.get("filter", "")
    window = int(params.get("window_seconds", 3600))
    min_matches = int(params.get("min_matches", 1))
    aws_profile = env.get("aws_profile", "")
    region = env.get("region", "us-east-1")
    end_ms = int(time.time() * 1000)
    start_ms = end_ms - window * 1000
    cmd = (
        f"aws logs filter-log-events "
        f"--log-group-name '{log_group}' "
        f"--filter-pattern '{filter_pattern}' "
        f"--start-time {start_ms} --end-time {end_ms} "
        f"--region {region}"
    )
    if aws_profile:
        cmd = f"AWS_PROFILE={aws_profile} " + cmd
    stdout, _, exit_code = _run_command(cmd)
    if exit_code != 0:
        return False, {
            "exit_code": exit_code,
            "error": stdout.decode("utf-8", errors="replace")[:500],
        }
    try:
        data = json.loads(stdout)
        events = data.get("events", [])
        match_count = len(events)
    except (json.JSONDecodeError, ValueError):
        return False, {
            "parse_error": True,
            "raw": stdout.decode("utf-8", errors="replace")[:500],
        }
    passed = match_count >= min_matches
    return passed, {
        "match_count": match_count,
        "min_matches": min_matches,
        "events_sample": events[:3],
    }


def _check_event_present(params: dict, captures: dict[str, str]) -> tuple[bool, dict]:
    url = _expand(params.get("url", ""), captures, {})
    timeout = int(params.get("timeout_seconds", 10))

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=3) as resp:  # noqa: S310
                data = json.loads(resp.read())
                events = data if isinstance(data, list) else data.get("events", [])
                if events:
                    return True, {"count": len(events)}
        except (urllib.error.URLError, OSError, json.JSONDecodeError):
            pass
        time.sleep(1)
    return False, {"count": 0, "url": url, "timeout": timeout}


def _check_field_equal(params: dict, captures: dict[str, str]) -> tuple[bool, dict]:
    a_key = params.get("a", "")
    b_key = params.get("b", "")
    a_val = _expand(a_key, captures, {})
    b_val = _expand(b_key, captures, {})
    passed = a_val == b_val
    return passed, {"a": a_val, "b": b_val, "equal": passed}


def _check_http_status(params: dict, captures: dict[str, str]) -> tuple[bool, dict]:
    expected = int(params.get("expected", 200))
    actual_raw = _expand(str(params.get("actual", "")), captures, {})
    try:
        actual = int(actual_raw)
    except (ValueError, TypeError):
        return False, {"error": f"could not parse actual http_status: {actual_raw!r}"}
    return actual == expected, {"expected": expected, "actual": actual}


def _check_no_duplicate(params: dict, captures: dict[str, str]) -> tuple[bool, dict]:
    url = _expand(params.get("url", ""), captures, {})

    try:
        with urllib.request.urlopen(url, timeout=5) as resp:  # noqa: S310
            data = json.loads(resp.read())
            events = data if isinstance(data, list) else data.get("events", [])
            count = len(events)
    except (urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
        return False, {"error": str(exc)}
    return count == 1, {"count": count, "expected": 1}
