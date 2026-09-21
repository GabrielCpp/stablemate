"""Dispatch an attendant to a run that stopped — parked on a gate, or dead."""

from __future__ import annotations

import json
import logging
import os
import signal
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from workhorse import inbox
from workhorse._vendor.stablemate_core import config as core_config
from workhorse.config_run import AgentResilience
from workhorse.runner.process import ProcessSupervisor

from groom import attend_transcript, gates, store

logger = logging.getLogger(__name__)

OFF, SESSION, HEADLESS = "off", "session", "headless"

PROMPT_PATH = Path(__file__).parent / "prompts" / "attend-gate.md"

ATTENDABLE_KIND = "operator"

_INBOX_FILE = "inbox.jsonl"


_SETTINGS_CACHE: tuple[str, float, core_config.AttendSettings] | None = None


def settings() -> core_config.AttendSettings:
    """The effective ``[groom.attend]`` settings: config first, then env, then default."""
    global _SETTINGS_CACHE
    try:
        path = core_config.config_path()
        stamp = path.stat().st_mtime if path.exists() else 0.0
        key = str(path)
    except OSError:
        path, stamp, key = None, 0.0, ""
    cached = _SETTINGS_CACHE
    if cached is not None and cached[0] == key and cached[1] == stamp:
        return cached[2]
    try:
        resolved = core_config.resolve_attend_settings()
    except Exception:
        logger.warning("attend: could not read %s — treating attend as off", key or "the config")
        resolved = core_config.AttendSettings(mode=OFF)
    _SETTINGS_CACHE = (key, stamp, resolved)
    return resolved


def forget_settings() -> None:
    """Drop the cache — for a test, and for a write that must be visible immediately."""
    global _SETTINGS_CACHE
    _SETTINGS_CACHE = None


def mode() -> str:
    value = settings().mode
    return value if value in (SESSION, HEADLESS) else OFF


def deny_patterns() -> tuple[str, ...]:
    """Substrings that veto a dispatch, matched against the gate path and question."""
    return settings().deny


@dataclass(frozen=True)
class AttendJob:
    """One stopped run, and everything an attendant needs to start on it."""

    job_id: str
    run_id: str
    kind: str
    workflow: str
    run_dir: str
    workspace: str
    created_at: float
    gate_path: str = ""
    question: str = ""
    failure_class: str = ""
    node: str = ""
    detail: str = ""

    def as_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "run_id": self.run_id,
            "kind": self.kind,
            "workflow": self.workflow,
            "run_dir": self.run_dir,
            "workspace": self.workspace,
            "created_at": self.created_at,
            "gate_path": self.gate_path,
            "question": self.gate_body() if self.kind == "gate" else self.question,
            "failure_class": self.failure_class,
            "node": self.node,
            "detail": self.detail,
        }

    def reason(self) -> str:
        """One line saying why this dispatch happened, for the row and the pane."""
        if self.kind == "gate":
            return f"parked on {self.gate_path or 'an operator gate'}"
        return f"died: {self.failure_class or 'no failure handoff recorded'}"

    def gate_body(self) -> str:
        """The same complete latest question set that the dashboard displays."""
        return gates.extract_question(self.question) or "(the run's questions listing is authoritative)"

    def facts(self) -> str:
        """The stopped run's facts and its latest questions or failure details."""
        lines = [
            "## The run that stopped",
            "",
            f"- kind: {self.kind}",
            f"- run_id: {self.run_id}",
            f"- workflow: {self.workflow}",
            f"- run_dir: {self.run_dir}",
            f"- workspace: {self.workspace}",
        ]
        if self.kind == "gate":
            lines += [f"- gate_path: {self.gate_path}", "", "## Latest questions from the workflow", "",
                      self.gate_body()]
        else:
            lines += [
                f"- failure_class: {self.failure_class or '(none recorded)'}",
                f"- node: {self.node or '(unknown)'}",
                "",
                "## What the run left behind",
                "",
                self.detail or "(no failure handoff — read checkpoint.json and events.jsonl)",
            ]
        return "\n".join(lines)

    def prompt(self) -> str:
        """The library prompt, then the job."""
        return f"{_doctrine()}\n\n---\n\n{self.facts()}\n"


def _doctrine() -> str:
    """The attendant prompt shipped with groom, or a refusal that names its absence."""
    try:
        return PROMPT_PATH.read_text()
    except OSError:
        return (
            "The attendant prompt is missing from this groom install "
            f"({PROMPT_PATH} is unreadable). Do not attempt the repair — record what "
            "you were handed in the run's inbox.jsonl and stop."
        )


class Spawner(Protocol):
    """How a job reaches an attendant."""

    def __call__(self, job: AttendJob) -> None: ...


def _mints_session(cli: str) -> bool:
    """Whether this CLI takes ``--session-id``."""
    return Path(cli).name.startswith("claude")


def _launch(job: AttendJob, session_id: str) -> subprocess.Popen[str]:
    """``claude -p`` on the job, in the run's workspace, as its own process group."""
    cli = settings().cli
    cmd = [cli, "-p", "--dangerously-skip-permissions",
           "--output-format", "stream-json", "--verbose"]
    if session_id:
        cmd += ["--session-id", session_id]
    cwd = job.workspace or job.run_dir or os.getcwd()
    supervisor = ProcessSupervisor()
    proc = supervisor.spawn(
        cmd,
        f"attend:{job.run_id}",
        resilience=AgentResilience(),
        cwd=cwd,
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
        text=True,
    )
    if proc.stdin is not None:
        proc.stdin.write(job.prompt())
        proc.stdin.close()
    return proc


def _first_status(path: str) -> str:
    """The gate file's first ``STATUS:`` line — the only one anything reads or writes."""
    try:
        text = Path(path).read_text(errors="replace")
    except OSError:
        return ""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.upper().startswith("STATUS:"):
            return stripped.split(":", 1)[1].strip()
    return ""


def _released_state(job: AttendJob) -> str:
    """What the run looked like when the attendant let go of it."""
    if job.kind == "gate" and job.gate_path:
        return _first_status(job.gate_path)
    if job.run_dir:
        try:
            data = json.loads((Path(job.run_dir) / "checkpoint.json").read_text())
        except (OSError, ValueError):
            return ""
        if isinstance(data, dict):
            return str(data.get("state") or "")
    return ""


def _own(job: AttendJob, proc: subprocess.Popen[str], session_id: str) -> None:
    """Wait on the attendant, bring its transcript home, and flip its row."""

    def _wait() -> None:
        code: int | None = None
        try:
            code = proc.wait()
        except Exception:
            logger.exception("attend: lost the attendant for %s", job.run_id)
        if session_id:
            attend_transcript.copy_session(session_id)
        store.attend_finish(
            job.job_id, exit_code=code, released_state=_released_state(job)
        )
        release(job.run_id)

    threading.Thread(target=_wait, name=f"attend-own-{job.run_id}", daemon=True).start()


def spawn_headless(job: AttendJob) -> None:
    """Dispatch a fresh attendant at this job and record the attempt as it starts."""
    session_id = str(uuid.uuid4()) if _mints_session(settings().cli) else ""
    proc = _launch(job, session_id)
    store.attend_start(
        job.job_id,
        run_id=job.run_id,
        workflow=job.workflow,
        run_dir=job.run_dir,
        workspace=job.workspace,
        kind=job.kind,
        reason=job.reason(),
        node=job.node,
        gate_path=job.gate_path,
        session_id=session_id,
        pid=proc.pid,
        started_at=job.created_at,
    )
    _own(job, proc, session_id)


def stop(job_id: str) -> bool:
    """Kill a running attendant and hand the run back."""
    row = store.attend_get(job_id)
    if row is None or row.get("status") != store.ATTEND_RUNNING:
        return False
    pid = row.get("pid")
    if isinstance(pid, int) and pid > 0:
        for sig in (signal.SIGTERM, signal.SIGKILL):
            try:
                os.killpg(pid, sig)
            except OSError:
                break
            time.sleep(0.2)
    for session_id in row.get("session_ids") or []:
        attend_transcript.copy_session(str(session_id))
    store.attend_finish(job_id, exit_code=None, released_state="stopped")
    release(str(row.get("run_id") or ""))
    return True


def _alive(pid: Any) -> bool:
    """Whether that pid is still a process."""
    if not isinstance(pid, int) or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def recover_orphans() -> int:
    """Restart every attendant groom was holding when it died."""
    spawning = mode() == HEADLESS
    restarted = 0
    for row in store.attend_orphans():
        job_id = str(row.get("job_id") or "")
        if not job_id or _alive(row.get("pid")):
            continue
        if not spawning:
            store.attend_finish(job_id, exit_code=None, released_state="lost")
            continue
        job = _job_from_row(row)
        session_id = str(uuid.uuid4()) if _mints_session(settings().cli) else ""
        try:
            proc = _launch(job, session_id)
        except Exception:
            logger.exception("attend: could not restart the attendant for %s", job.run_id)
            store.attend_finish(job_id, exit_code=None, released_state="lost")
            continue
        store.attend_append_session(job_id, session_id, pid=proc.pid)
        _LEDGER.by_run[job.run_id] = job_id
        _own(job, proc, session_id)
        restarted += 1
    return restarted


def _job_from_row(row: dict[str, Any]) -> AttendJob:
    """Rebuild the job a stored row describes, re-reading whatever went stale."""
    kind = str(row.get("kind") or "gate")
    run_dir = str(row.get("run_dir") or "")
    gate_path = str(row.get("gate_path") or "")
    question = ""
    failure_class, node, detail = "", str(row.get("node") or ""), ""
    if kind == "gate":
        try:
            question = Path(gate_path).read_text(errors="replace") if gate_path else ""
        except OSError:
            question = ""
    else:
        failure_class, found_node, detail = read_failure(run_dir)
        node = found_node or node
    return AttendJob(
        job_id=str(row.get("job_id") or ""),
        run_id=str(row.get("run_id") or ""),
        kind=kind,
        workflow=str(row.get("workflow") or ""),
        run_dir=run_dir,
        workspace=str(row.get("workspace") or ""),
        created_at=float(row.get("started_at") or time.time()),
        gate_path=gate_path,
        question=question,
        failure_class=failure_class,
        node=node,
        detail=detail,
    )


@dataclass
class _Ledger:
    """Everything the module remembers between announcements, in one object."""

    jobs: dict[str, AttendJob] = field(default_factory=dict)
    by_run: dict[str, str] = field(default_factory=dict)


_LEDGER = _Ledger()


def reset() -> None:
    """Forget every outstanding job and spent slot — for tests, and a fresh process."""
    _LEDGER.jobs.clear()
    _LEDGER.by_run.clear()


def queue() -> list[dict]:
    """Every outstanding job, oldest first."""
    return [job.as_dict() for job in sorted(_LEDGER.jobs.values(), key=lambda j: j.created_at)]


def release(run_id: str) -> None:
    """Drop this run's outstanding job — its gate cleared, or it is running again."""
    job_id = _LEDGER.by_run.pop(run_id, "")
    if job_id:
        _LEDGER.jobs.pop(job_id, None)


def _dispatch(job: AttendJob, spawner: Spawner | None) -> AttendJob | None:
    """Publish the job, and in headless mode hand it to a process."""
    _LEDGER.jobs[job.job_id] = job
    _LEDGER.by_run[job.run_id] = job.job_id
    if mode() == HEADLESS:
        try:
            (spawner or spawn_headless)(job)
        except Exception:
            logger.exception("attend: could not spawn an attendant for %s", job.run_id)
    return job


def _blocked(run_id: str) -> bool:
    """Whether an attendant is already on this run — the whole rule, in one place."""
    if mode() == OFF or run_id in _LEDGER.by_run:
        return True
    try:
        return store.attend_running_for_run(run_id) is not None
    except Exception:
        logger.exception("attend: could not read the running row for %s", run_id)
        return True


def attend_gate(
    *,
    run_id: str,
    workflow: str,
    run_dir: str,
    workspace: str,
    gate_path: str,
    question: str,
    kind: str = ATTENDABLE_KIND,
    now: float | None = None,
    spawner: Spawner | None = None,
) -> AttendJob | None:
    """A run just parked on a gate that is new to its row."""
    now = now if now is not None else time.time()
    if kind and kind != ATTENDABLE_KIND:
        return None
    question = gates.extract_question(question)
    haystack = f"{gate_path}\n{question}".lower()
    if any(pattern in haystack for pattern in deny_patterns()):
        return None
    if _blocked(run_id):
        return None
    return _dispatch(
        AttendJob(
            job_id=uuid.uuid4().hex[:12],
            run_id=run_id,
            kind="gate",
            workflow=workflow,
            run_dir=run_dir,
            workspace=workspace,
            created_at=now,
            gate_path=gate_path,
            question=question,
        ),
        spawner,
    )


def read_failure(run_dir: str) -> tuple[str, str, str]:
    """``(failure_class, node, body)`` from the run's own handoff entry, if it wrote one."""
    if not run_dir:
        return "", "", ""
    try:
        messages = inbox.all_messages(Path(run_dir) / _INBOX_FILE)
    except Exception:
        return "", "", ""
    failures = [m for m in messages if getattr(m, "kind", "") == "failure"]
    if not failures:
        return "", "", ""
    body = failures[-1].body
    fields = {}
    for line in body.splitlines():
        key, _, value = line.partition(": ")
        if value:
            fields.setdefault(key.strip(), value.strip())
    return fields.get("failure_class", ""), fields.get("node", ""), body


def attend_death(
    *,
    run_id: str,
    workflow: str,
    run_dir: str,
    workspace: str,
    now: float | None = None,
    spawner: Spawner | None = None,
) -> AttendJob | None:
    """A run ended without reaching its own end."""
    now = now if now is not None else time.time()
    if _blocked(run_id):
        return None
    failure_class, node, body = read_failure(run_dir)
    return _dispatch(
        AttendJob(
            job_id=uuid.uuid4().hex[:12],
            run_id=run_id,
            kind="death",
            workflow=workflow,
            run_dir=run_dir,
            workspace=workspace,
            created_at=now,
            failure_class=failure_class,
            node=node,
            detail=body,
        ),
        spawner,
    )
