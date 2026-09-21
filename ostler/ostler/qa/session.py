"""QA session state: NDJSON run log + capture store + daemon PID registry."""

from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import time
import urllib.error
import urllib.request
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ostler.qa.harness_host import load_harness_module
from ostler.qa.manifest import RunManifest

QA_DIRNAME = "qa"
SESSION_FILE = "qa-session.json"
RUN_LOG = "qa-run.ndjson"

RESERVED_LABELS = frozenset({QA_DIRNAME, "steps", "asserts", "traces", "videos", "screenshots"})

_LABEL_RE = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9._-]*\Z")

_MECHS = {"live", "fixture"}


@dataclass(frozen=True)
class _DaemonTiming:
    poll_s: float = 1.0
    settle_s: float = 2.0
    interrupt_grace_s: float = 2.0
    terminate_grace_s: float = 1.0


_DAEMON_TIMING = _DaemonTiming()


class ScratchLabelError(ValueError):
    """A dry run was asked for under a name that cannot be a scratch directory."""


def scratch_dirname(label: str) -> str:
    """The spec-relative ledger directory for a dry run called ``label``: ``qa/<label>``."""
    name = label.strip()
    if not name:
        raise ScratchLabelError("a dry-run label cannot be empty")
    if name in RESERVED_LABELS:
        hint = (
            " — the scored ledger is what you get by omitting the flag"
            if name == QA_DIRNAME
            else f" — the scored run writes {QA_DIRNAME}/{name}/ itself"
        )
        raise ScratchLabelError(f"`{name}` is a reserved directory name{hint}")
    if not _LABEL_RE.match(name):
        raise ScratchLabelError(
            f"`{label}` is not a dry-run label. A label is one path component of letters, "
            "digits, `.`, `_` and `-` — not a path: it always resolves to "
            f"{QA_DIRNAME}/<label>/ inside the spec directory."
        )
    return f"{QA_DIRNAME}/{name}"




def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _spec_dir_from(spec_arg: str | None, root: Path) -> Path:
    if not spec_arg:
        raise ValueError("--spec is required when no session is open")
    p = Path(spec_arg)
    return p if p.is_absolute() else root / p




class QaSession:
    """Thin wrapper around the on-disk session + log files."""

    def __init__(self, spec_dir: Path, qa_dirname: str = QA_DIRNAME) -> None:
        self.spec_dir = spec_dir
        self.qa_dirname = qa_dirname
        self.qa_dir = spec_dir / qa_dirname
        self._session_path = self.qa_dir / SESSION_FILE
        self._log_path = self.qa_dir / RUN_LOG
        self._data: dict[str, Any] = {}
        self._secret_values: dict[str, str] = {}
        self._manifest: RunManifest | None = None
        self._daemon_procs: dict[int, subprocess.Popen[bytes]] = {}


    @classmethod
    def open(cls, spec_dir: Path, qa_dirname: str = QA_DIRNAME) -> "QaSession":
        """Load an existing session; raise if none exists."""
        s = cls(spec_dir, qa_dirname)
        if not s._session_path.is_file():
            raise FileNotFoundError(
                f"No open QA session at {s._session_path}. Run `ostler qa start` first."
            )
        s._data = json.loads(s._session_path.read_text(encoding="utf-8"))
        s._manifest = RunManifest(spec_dir, str(s._data["run_id"]), qa_dirname)
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
        qa_dirname: str = QA_DIRNAME,
    ) -> "QaSession":
        """Create a fresh session file; raise if one is already open."""
        s = cls(spec_dir, qa_dirname)
        if s._session_path.is_file():
            raise FileExistsError(
                f"A QA session is already open at {s._session_path}. "
                "Run `ostler qa stop` first."
            )
        s.qa_dir.mkdir(parents=True, exist_ok=True)
        (s.qa_dir / "steps").mkdir(exist_ok=True)
        (s.qa_dir / "asserts").mkdir(exist_ok=True)
        s._data = {
            "run_id": run_id,
            "story": story,
            "env": env,
            "captures": {},
            "daemons": [],
            "step_count": 0,
            "assert_count": 0,
            "pass_count": 0,
            "fail_count": 0,
            "started_monotonic": time.monotonic(),
            "started_wall": time.time(),
        }
        s._secret_values = secret_values or {}
        s._manifest = RunManifest(spec_dir, run_id, qa_dirname)
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


    def _append(self, record: dict[str, Any]) -> None:
        record["ts"] = _now()
        record["offset_ms"] = round(
            (time.monotonic() - self._data.get("started_monotonic", time.monotonic())) * 1000
        )
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
            self._manifest = RunManifest(self.spec_dir, self.run_id, self.qa_dirname)
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
            self._manifest = RunManifest(self.spec_dir, self.run_id, self.qa_dirname)
        self._manifest.register(self._log_path, kind="run-ledger")


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
    def secret_values(self) -> dict[str, str]:
        """The secrets this run injects, for a driver that has its own output to redact."""
        return dict(self._secret_values)

    @property
    def started_wall(self) -> float:
        """When this session began, as a POSIX timestamp; 0.0 for a session written before the field existed, which reads as "everything on disk is mine" — the old behaviour."""
        return float(self._data.get("started_wall") or 0.0)

    def command_env(self) -> dict[str, str]:
        """The environment a plan's `cmd` and `background:` daemons run under."""
        return {**os.environ, "QA_DIR": str(self.qa_dir), **self._secret_values}

    @property
    def captures(self) -> dict[str, str]:
        return self._data.get("captures", {})

    def get_capture(self, key: str) -> str:
        return self._data.get("captures", {}).get(key, "")

    def set_capture(self, key: str, value: str) -> None:
        self._data.setdefault("captures", {})[key] = value


    def write_session_start(self) -> None:
        self._append(
            {
                "kind": "session_start",
                "run_id": self.run_id,
                "story": self.story,
                "env": self.env,
            }
        )


    def start_daemon(
        self,
        name: str,
        argv: Sequence[str],
        *,
        ready_check: str | Mapping[str, Any] | None = None,
        timeout: float = 30,
        cwd: Path | None = None,
    ) -> int:
        """Launch a daemon subprocess, store its PID, write daemon_start record."""
        argv = list(argv)
        if not argv:
            raise ValueError(f"daemon '{name}' declares an empty argv")
        log_file = self.qa_dir / f"daemon-{name}.log"
        with log_file.open("wb") as lf:
            proc = subprocess.Popen(  # noqa: S603 — argv from the plan, and no shell
                argv,
                stdout=lf,
                stderr=subprocess.STDOUT,
                start_new_session=True,
                cwd=cwd or self.spec_dir,
                env=self.command_env(),
            )
        pid = proc.pid
        self._daemon_procs[pid] = proc
        self._data.setdefault("daemons", []).append(
            {"name": name, "pid": pid, "argv": argv, "log_file": str(log_file)}
        )
        self._save()
        self._append(
            {
                "kind": "daemon_start",
                "name": name,
                "pid": pid,
                "argv": [_redact(part, self._secret_values.values()) for part in argv],
                "log_file": str(log_file),
                "ready_check": ready_check,
            }
        )
        if ready_check:
            _poll_ready(
                ready_check,
                timeout=timeout,
                proc=proc,
                log_file=log_file,
            )
        return pid

    def stop_daemon(self, name: str, *, reason: str | None = None) -> int | None:
        """Kill the running daemon called *name*, drop it from the session, write `daemon_stop`."""
        daemons = self._data.get("daemons", [])
        index = next((i for i, d in enumerate(daemons) if d["name"] == name), None)
        if index is None:
            raise ValueError(f"no running daemon named {name!r}")
        entry = daemons.pop(index)
        exit_code = _kill_pid(entry["pid"])
        proc = self._daemon_procs.pop(entry["pid"], None)
        if proc is not None:
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass
        self._save()
        record: dict[str, Any] = {
            "kind": "daemon_stop",
            "name": name,
            "pid": entry["pid"],
            "exit_code": exit_code,
        }
        if reason:
            record["reason"] = reason
        self._append(record)
        return exit_code

    def stop_all_daemons(self) -> None:
        """Kill all running daemons and write daemon_stop records."""
        for d in list(self._data.get("daemons", [])):
            self.stop_daemon(d["name"])
        self._data["daemons"] = []
        self._save()


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
        """Execute *cmd* in a subprocess and append a ``step`` record."""
        if mechanism not in _MECHS:
            raise ValueError(
                f"mechanism must be one of {sorted(_MECHS)}, got '{mechanism}'"
            )

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
                env=self.command_env(),
            )
            timed_out = False
        except subprocess.TimeoutExpired as exc:
            stdout_raw = _as_bytes(exc.stdout)
            stderr_raw = _as_bytes(exc.stderr)
            exit_code = 124
            timed_out = True
        resolved_out: Path | None = _resolve_out(out_path, self.spec_dir, self.qa_dir) if out_path else None
        out_kept: bool = False
        if resolved_out is not None:
            resolved_out.parent.mkdir(parents=True, exist_ok=True)
            if not stdout_raw and _adoptable(resolved_out, self.started_wall):
                stdout_raw = resolved_out.read_bytes()
                out_kept = True

        http_status: int | None = _extract_http_status(stdout_raw)
        body_raw = _without_http_status(stdout_raw) if http_status is not None else stdout_raw
        if http_status is None:
            http_status = _status_from_header_dump(stdout_raw)
        stdout_safe = _redact_bytes(body_raw, self._secret_values.values())
        stderr_safe = _redact_bytes(stderr_raw, self._secret_values.values())

        abs_out: str | None = None
        if resolved_out is not None:
            if not out_kept:
                resolved_out.write_bytes(stdout_safe)
            abs_out = str(resolved_out)
            self.register_artifact(
                resolved_out, kind="command-output", scenario=scenario, target=driver
            )

        captured: dict[str, str] = {}
        if captures:
            try:
                data = json.loads(body_raw.decode("utf-8", errors="replace"))
            except (json.JSONDecodeError, ValueError):
                data = None
            for key, json_path in captures:
                value = _extract_path(data, json_path)
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

        record["_stdout"] = stdout_safe.decode("utf-8", errors="replace")
        record["_stdout_actual"] = body_raw.decode("utf-8", errors="replace")

        self._append(record)

        if not allow_fail and exit_code != 0:
            raise RuntimeError(
                f"step '{step_id}' exited {exit_code}: "
                + stdout_safe.decode("utf-8", errors="replace")[:500]
            )
        return record


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
        declared: tuple[str, Mapping[str, Any]] | None = None,
        sentinel: bool = False,
        step: tuple[str, str] | None = None,
    ) -> tuple[bool, dict[str, Any]]:
        """Execute a named check, write raw result, append assert record."""
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
            "check": declared[0] if declared else check_type,
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
        if sentinel:
            record["sentinel"] = True
        if step:
            record["step"], record["step_label"] = step
        if declared:
            record["check_args"] = dict(declared[1])
        for key in ("match_count", "count", "value", "expected"):
            if key in raw_result:
                record[key] = raw_result[key]

        self._append(record)
        return passed, record


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
        try:
            self._session_path.unlink()
        except FileNotFoundError:
            pass
        return summary




def _run_command(
    cmd: str,
    *,
    timeout: float | None = None,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
) -> tuple[bytes, bytes, int]:
    result = subprocess.run(
        f"set -o pipefail\n{cmd}",
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
    """Read the status out of a curl ``-D`` header dump."""
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

    def _sub(m: re.Match[str]) -> str:
        token = m.group(1).strip()
        if token.startswith("env."):
            return env.get(token[4:], "")
        if token.startswith("input."):
            return (variables or {}).get(token, "")
        if token == "qa_dir":
            return (variables or {}).get(token, "")
        if token.startswith("secret."):
            return (secrets or {}).get(token[7:], "")
        if token == "run_id":
            return run_id
        if token == "story":
            return story
        return captures.get(token, m.group(0))

    return re.sub(r"\{\{([^}]+)\}\}", _sub, template)


def _extract_path(data: Any, path: str) -> str | None:
    """Extract a capture's value by a document path, as the harness's `resolve_path` walks it."""
    if data is None:
        return None
    try:
        resolved, value = _harness().resolve_path(data, path)
    except ValueError:
        return None
    if not resolved or value is None:
        return None
    if _harness()._is_projection(path) and len(value) == 1:
        value = value[0]
    return str(value) if value is not None else None


def _harness() -> Any:
    """The harness module, loaded on first use — the path grammar lives there, once."""
    return load_harness_module("ostler_qa")


def _adoptable(out_file: Path, started_wall: float) -> bool:
    """Whether a step may treat an already-present `out:` file as its own stdout."""
    if not out_file.is_file() or not out_file.stat().st_size:
        return False
    return out_file.stat().st_mtime >= started_wall - 1.0


def _resolve_out(out_path: str, spec_dir: Path, qa_dir: Path) -> Path:
    """Resolve an action's `out:` against the spec, sending `qa/…` to *this* run's ledger dir."""
    p = Path(out_path)
    if not p.is_absolute() and p.parts and p.parts[0] == QA_DIRNAME:
        p = qa_dir.resolve().joinpath(*p.parts[1:])
    resolved = (p if p.is_absolute() else spec_dir / p).resolve()
    try:
        resolved.relative_to(spec_dir.resolve())
    except ValueError as exc:
        raise ValueError(f"output path escapes spec directory: {out_path}") from exc
    return resolved


def _signal_group(pid: int, sig: int) -> bool:
    """Signal ``pid``'s process group; False once the group has nothing left to signal."""
    try:
        os.killpg(pid, sig)
    except (ProcessLookupError, PermissionError):
        return False
    return True


def _kill_pid(pid: int, *, timing: _DaemonTiming | None = None) -> int:
    """Escalate SIGINT -> SIGTERM -> SIGKILL; return the effective signal (negated, like subprocess) that actually stopped the process."""
    clock = timing or _DAEMON_TIMING
    for sig, grace_seconds in (
        (signal.SIGINT, clock.interrupt_grace_s),
        (signal.SIGTERM, clock.terminate_grace_s),
    ):
        if not _signal_group(pid, sig):
            return 0
        deadline = time.monotonic() + grace_seconds
        while time.monotonic() < deadline:
            if not _signal_group(pid, 0):
                return -sig
            time.sleep(0.05)
    if _signal_group(pid, signal.SIGKILL):
        return -signal.SIGKILL
    return 0


def _ready_via_url(
    url: str, *, method: str = "GET", status: int = 200, timeout: float = 2
) -> bool:
    """One HTTP probe: ready when *url* answers *status* to *method*."""
    request = urllib.request.Request(url, method=method.upper())  # noqa: S310
    try:
        with urllib.request.urlopen(request, timeout=timeout) as resp:  # noqa: S310
            return bool(resp.status == status)
    except urllib.error.HTTPError as exc:
        return bool(exc.code == status)
    except (urllib.error.URLError, OSError):
        return False


def _log_tail(log_file: Path | None, lines: int = 15) -> str:
    """The last few lines the daemon printed, for pasting into a failure message."""
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
    proc: subprocess.Popen | None = None,
    log_file: Path | None = None,
    timing: _DaemonTiming | None = None,
) -> None:
    """Poll a daemon's readiness check until it succeeds or *timeout* seconds elapse."""
    if isinstance(check, str):
        url, method, status = check, "GET", 200
    else:
        raw_url = check.get("url")
        if not isinstance(raw_url, str) or not raw_url.strip():
            raise ValueError(f"daemon ready_check mapping needs a 'url': {dict(check)}")
        url = raw_url
        method = str(check.get("method", "GET"))
        status = int(check.get("status", 200))
    described = url if method == "GET" and status == 200 else f"{method} {url} -> {status}"
    probe_timeout = 2.0 if isinstance(check, str) else float(check.get("timeout", 2))
    clock = timing or _DAEMON_TIMING
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        ready = _ready_via_url(url, method=method, status=status, timeout=probe_timeout)
        code = proc.poll() if proc is not None else None
        if code not in (None, 0):
            raise _daemon_died(code, described, log_file, ready=ready)
        if ready:
            settled = _settled(proc, timeout=clock.settle_s)
            if settled not in (None, 0):
                raise _daemon_died(settled, described, log_file, ready=True)
            return
        time.sleep(clock.poll_s)
    tail = _log_tail(log_file)
    raise TimeoutError(
        f"daemon ready_check timed out after {timeout}s: {described}"
        + (f"\n--- last lines of {log_file}:\n{tail}" if tail else "")
    )


def _settled(proc: subprocess.Popen | None, *, timeout: float) -> int | None:
    """The daemon's exit code if it dies within the settle window, else `None`."""
    if proc is None:
        return None
    try:
        return proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        return None


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
    if check_type == "scenario_check":
        return _check_scenario_verdict(params)
    return False, {"error": f"unknown check type '{check_type}'"}


def _check_scenario_verdict(params: dict) -> tuple[bool, dict]:
    """Record a verdict a `qa.check` in the scenario process already reached."""
    return bool(params.get("passed")), {
        "value": params.get("actual"),
        "expected": params.get("expected"),
    }


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
