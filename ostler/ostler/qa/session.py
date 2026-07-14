"""QA session state: NDJSON run log + capture store + daemon PID registry.

The session file (`qa-session.json`) is the mutable side-car written by
`ostler qa start/step/stop`; it stores runtime state (captures, PIDs) that must
survive across separate CLI invocations within the same run.

The run log (`qa-run.ndjson`) is append-only and never rewritten by ostler.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

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
        return s

    @classmethod
    def create(
        cls,
        spec_dir: Path,
        run_id: str,
        story: str,
        env: dict[str, str],
    ) -> "QaSession":
        """Create a fresh session file; raise if one is already open."""
        s = cls(spec_dir)
        if s._session_path.is_file():
            raise FileExistsError(
                f"A QA session is already open at {s._session_path}. "
                "Run `ostler qa stop` first."
            )
        s.qa_dir.mkdir(parents=True, exist_ok=True)
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
        }
        s._save()
        return s

    def _save(self) -> None:
        self._session_path.write_text(
            json.dumps(self._data, indent=2) + "\n", encoding="utf-8"
        )

    # -- append-only log -----------------------------------------------------

    def _append(self, record: dict[str, Any]) -> None:
        record["ts"] = _now()
        # Strip private in-memory keys before writing to the append-only log.
        log_record = {k: v for k, v in record.items() if not k.startswith("_")}
        with self._log_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(log_record) + "\n")

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
        self, name: str, cmd: str, *, ready_check: str | None = None
    ) -> int:
        """Launch a daemon subprocess, store its PID, write daemon_start record.

        stdout/stderr are tee'd to ``qa/daemon-<name>.log``.
        If *ready_check* is an HTTP URL, ostler polls it (GET, up to 30 s).
        Returns the PID.
        """
        log_file = self.qa_dir / f"daemon-{name}.log"
        with log_file.open("wb") as lf:
            proc = subprocess.Popen(
                cmd,
                shell=True,  # noqa: S603 — agent-controlled command, explicit user intent
                stdout=lf,
                stderr=subprocess.STDOUT,
                start_new_session=True,
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
                "cmd": cmd,
                "log_file": str(log_file),
                "ready_check": ready_check,
            }
        )
        if ready_check:
            _poll_ready(ready_check, timeout=30)
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
        expanded_cmd = _expand(cmd, self.captures, self.env)

        stdout_raw, stderr_raw, exit_code = _run_command(expanded_cmd)
        http_status: int | None = _extract_http_status(stdout_raw)

        # Write sidecar
        abs_out: str | None = None
        if out_path:
            resolved = _resolve_out(out_path, self.spec_dir)
            resolved.parent.mkdir(parents=True, exist_ok=True)
            resolved.write_bytes(stdout_raw)
            abs_out = str(resolved)

        # Apply jq captures
        captured: dict[str, str] = {}
        if captures:
            try:
                data = json.loads(stdout_raw.decode("utf-8", errors="replace"))
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
            "cmd": expanded_cmd,
            "exit_code": exit_code,
        }
        if http_status is not None:
            record["http_status"] = http_status
        if abs_out:
            record["stdout_file"] = abs_out
        if captured:
            record["captured"] = captured
        if stderr_raw:
            record["stderr"] = stderr_raw.decode("utf-8", errors="replace")[:2000]

        # Keep decoded stdout in-memory for inline assertion checks (not written to log).
        # Stored under a private key so _append can strip it.
        record["_stdout"] = stdout_raw.decode("utf-8", errors="replace")

        self._append(record)

        if not allow_fail and exit_code != 0:
            raise RuntimeError(
                f"step '{step_id}' exited {exit_code}: "
                + stdout_raw.decode("utf-8", errors="replace")[:500]
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
            json.dumps(raw_result, indent=2) + "\n", encoding="utf-8"
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
        }
        # Attach summary fields from raw result
        for key in ("match_count", "count", "value", "expected"):
            if key in raw_result:
                record[key] = raw_result[key]

        self._append(record)
        return passed, record

    # -- stop ----------------------------------------------------------------

    def close(self) -> dict[str, Any]:
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


def _run_command(cmd: str) -> tuple[bytes, bytes, int]:
    result = subprocess.run(
        cmd,
        shell=True,  # noqa: S603 — agent-authored command, explicit user intent
        capture_output=True,
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


def _expand(template: str, captures: dict[str, str], env: dict[str, str]) -> str:
    """Expand ``{{key}}`` and ``{{env.name}}`` substitutions in a command string."""
    import re

    def _sub(m: re.Match) -> str:
        token = m.group(1).strip()
        if token.startswith("env."):
            return env.get(token[4:], "")
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
    if p.is_absolute():
        return p
    return spec_dir / p


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
        try:
            os.kill(pid, sig)
        except ProcessLookupError:
            return 0
        deadline = time.monotonic() + grace_seconds
        while time.monotonic() < deadline:
            try:
                os.kill(pid, 0)  # check still alive
            except ProcessLookupError:
                return -sig
            time.sleep(0.05)
    try:
        os.kill(pid, signal.SIGKILL)
        return -signal.SIGKILL
    except ProcessLookupError:
        return 0


def _poll_ready(url: str, timeout: int = 30) -> None:
    """Poll *url* until HTTP 200 or *timeout* seconds elapse."""
    import urllib.error
    import urllib.request

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as resp:  # noqa: S310
                if resp.status == 200:
                    return
        except (urllib.error.URLError, OSError):
            pass
        time.sleep(1)
    raise TimeoutError(f"daemon ready_check timed out after {timeout}s: {url}")


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
    import urllib.error
    import urllib.request

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
    import urllib.error
    import urllib.request

    try:
        with urllib.request.urlopen(url, timeout=5) as resp:  # noqa: S310
            data = json.loads(resp.read())
            events = data if isinstance(data, list) else data.get("events", [])
            count = len(events)
    except (urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
        return False, {"error": str(exc)}
    return count == 1, {"count": count, "expected": 1}
