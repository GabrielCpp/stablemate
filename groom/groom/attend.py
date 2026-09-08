"""Dispatch an attendant to a run that stopped — parked on a gate, or dead.

groom already learns both facts and does nothing with either. A run announces its
own block (``/push/blocked`` → :func:`groom.app._poll_gate_soon`, or the native
ingest's ``newly_blocked``) and its own ending (``/push/exited``, or an ``ENDED`` /
``DIED`` alert), and every one of those paths currently terminates in a browser
toast and a page to a channel nobody is reading. This module puts an actor on that
edge.

**Why groom and not a workflow.** A run cannot patch the code it is executing, and a
run that died cannot be investigated by the process that died. The attendant has to
be outside every run it serves, and groom is the only thing that already watches all
of them.

**No new loop.** Everything here is called from an existing announcement path.
groom's rule — *the pushes are hints that trigger an immediate poll, and the periodic
poll is the reconciler* — is inherited whole: an announcement that never lands is
healed one reconciling tick later, so the attendant needs no timer of its own.

**groom never answers a gate itself.** It dispatches; the attendant it dispatches
uses the control CLI, and is bound by the rule that terminating a run or discarding
its checkpoint still needs an operator to say so explicitly.

Two modes, configured, off by default:

- ``GROOM_ATTEND=headless`` spawns ``claude -p`` with the job on stdin, in the run's
  own workspace.
- ``GROOM_ATTEND=session`` spawns nothing and publishes the job instead, for an
  interactive session to claim from ``GET /api/attend/queue`` — one fleet-wide
  endpoint rather than one poll loop per run id.
"""

from __future__ import annotations

import logging
import os
import signal
import subprocess
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from workhorse import inbox
from workhorse._vendor.stablemate_core.discovery import base_library_dir
from workhorse.config_run import AgentResilience
from workhorse.runner.process import ProcessSupervisor

logger = logging.getLogger(__name__)

#: The three modes ``GROOM_ATTEND`` selects between. ``off`` is the default and is
#: not a degraded state: an unconfigured groom is exactly the dashboard it was.
OFF, SESSION, HEADLESS = "off", "session", "headless"

#: The library prompt the headless dispatch carries, relative to the base library.
PROMPT_SUBPATH = Path("library/prompts/stablemate/attend-gate.md")

#: What a gate's own ``kind`` must be for the attendant to touch it. A ``machine``
#: wait is a measurement, not a human failing to answer — a 40-hour one is normal —
#: and dispatching an agent at it would interrupt the thing it is waiting for.
ATTENDABLE_KIND = "operator"

_INBOX_FILE = "inbox.jsonl"


def mode() -> str:
    """Read per call, like :mod:`groom.notify`, so a test can set it without reimport."""
    value = os.environ.get("GROOM_ATTEND", OFF).strip().lower()
    return value if value in (SESSION, HEADLESS) else OFF


def deny_patterns() -> tuple[str, ...]:
    """Substrings that veto a dispatch, matched against the gate path and question.

    Some gates are genuinely not an agent's to answer, and the tree says so at the
    site: a red PR that cannot be pushed is an infrastructure or credential wall, not
    a question an agent clears by trying harder. Comma-separated,
    ``GROOM_ATTEND_DENY``.
    """
    raw = os.environ.get("GROOM_ATTEND_DENY", "")
    return tuple(part.strip().lower() for part in raw.split(",") if part.strip())


def _budget() -> tuple[int, float]:
    """(spawns allowed, window seconds) per run — the bound on a gate nobody can clear.

    Without it, a gate the attendant declines and re-announces is an unbounded
    sequence of agent turns against a question that is not going to move.
    """
    count = int(os.environ.get("GROOM_ATTEND_MAX", "3") or "3")
    window = float(os.environ.get("GROOM_ATTEND_WINDOW_MIN", "60") or "60") * 60
    return count, window


def _timeout_s() -> float:
    return float(os.environ.get("GROOM_ATTEND_TIMEOUT_MIN", "60") or "60") * 60


@dataclass(frozen=True)
class AttendJob:
    """One stopped run, and everything an attendant needs to start on it.

    ``kind`` is the whole branch: a **gate** is reloaded and answered (in that order
    — an answer written before a cutting reload lets the run resume on the old code,
    which is the failure that looks like success), while a **death** has no socket
    left to talk to and is patched and resumed from its checkpoint.
    """

    job_id: str
    run_id: str
    kind: str  # "gate" | "death"
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
            "question": self.question,
            "failure_class": self.failure_class,
            "node": self.node,
            "detail": self.detail,
        }

    def facts(self) -> str:
        """The job as the attendant reads it: named facts, and the gate body verbatim.

        The question is passed **unparsed**. Three incompatible gate formats are in the
        tree — composed escalations, hand-written f-strings, raw validator dumps — and
        the only thing that covers all of them is handing the text over intact.
        """
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
            lines += [f"- gate_path: {self.gate_path}", "", "## The gate, verbatim", "",
                      self.question or "(the run's questions listing is authoritative)"]
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
        """The library prompt, then the job. Doctrine first so the facts land inside it."""
        return f"{_doctrine()}\n\n---\n\n{self.facts()}\n"


def _strip_frontmatter(text: str) -> str:
    """Drop a slash-command's YAML header — it addresses the command loader, not a turn."""
    if not text.startswith("---\n"):
        return text
    end = text.find("\n---\n", 3)
    return text[end + 5 :] if end != -1 else text


def _doctrine() -> str:
    """The attendant prompt from the base library, or a refusal that names its absence.

    Failing soft here would be the worst option available: a spawned agent with the
    facts and none of the rules is exactly the attendant that answers a gate to make a
    run move. So the fallback text tells it to stop rather than to improvise.
    """
    base = base_library_dir()
    if base is not None:
        path = base / PROMPT_SUBPATH
        if path.is_file():
            return _strip_frontmatter(path.read_text())
    return (
        "The attendant prompt is not installed on this machine "
        f"({PROMPT_SUBPATH} is absent from the base library). Do not attempt the "
        "repair — record what you were handed in the run's inbox.jsonl and stop."
    )


class Spawner(Protocol):
    """How a job reaches an attendant. A port so a test needs no agent and no process."""

    def __call__(self, job: AttendJob) -> None: ...


def spawn_headless(job: AttendJob) -> None:
    """``claude -p`` on the job, in the run's workspace, as its own process group.

    Spawned through workhorse's :class:`ProcessSupervisor` rather than a bare
    ``Popen``: it aligns the child's ``$PWD`` with its ``cwd`` (an agent CLI that
    trusts ``PWD`` otherwise works in groom's directory instead of the run's) and it
    rides out the exec window of a CLI rewriting itself mid-update.

    The prompt goes on **stdin**, not ``argv`` — a gate body is a document.
    """
    cli = os.environ.get("GROOM_ATTEND_CLI", "claude")
    cmd = [cli, "-p", "--dangerously-skip-permissions",
           "--output-format", "stream-json", "--verbose"]
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
    _reap_after(proc, job, _timeout_s())


def _reap_after(proc: subprocess.Popen, job: AttendJob, timeout: float) -> None:
    """Kill the attendant's whole process group if it outlives its window.

    The spawn budget bounds how *often* an attendant is dispatched, which is not the
    same bound: one agent that hangs holds the run's workspace open indefinitely, and
    nothing else here would ever notice. The group — ``start_new_session`` made one —
    is what gets signalled, because an agent CLI's own children are the part that
    lingers. A daemon thread rather than an asyncio task: it must not keep groom's
    loop alive, and it must work when the dispatch came from a rules tick.
    """

    def _wait() -> None:
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            logger.warning(
                "attend: attendant for %s outlived %.0fs — killing its group", job.run_id, timeout
            )
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except OSError:
                proc.kill()

    threading.Thread(target=_wait, name=f"attend-reap-{job.run_id}", daemon=True).start()


@dataclass
class _Ledger:
    """Everything the module remembers between announcements, in one object.

    A dataclass rather than three module globals because the three fields have an
    invariant between them — a job in ``by_run`` is in ``jobs``, and a job that was
    dispatched spent a slot — and a test that resets one and not the others would be
    testing a state the running process never reaches. :func:`reset` clears all three.
    """

    #: job_id → job, the fleet-wide outstanding set `GET /api/attend/queue` renders.
    jobs: dict[str, AttendJob] = field(default_factory=dict)
    #: run_id → job_id. One in-flight attendant per run, always: a second one would
    #: be two agents patching the same tree against the same checkpoint.
    by_run: dict[str, str] = field(default_factory=dict)
    #: run_id → dispatch timestamps inside the rolling window.
    spawns: dict[str, deque[float]] = field(default_factory=dict)


_LEDGER = _Ledger()


def reset() -> None:
    """Forget every outstanding job and spent slot — for tests, and a fresh process."""
    _LEDGER.jobs.clear()
    _LEDGER.by_run.clear()
    _LEDGER.spawns.clear()


def queue() -> list[dict]:
    """Every outstanding job, oldest first. The fleet-wide view a session polls."""
    return [job.as_dict() for job in sorted(_LEDGER.jobs.values(), key=lambda j: j.created_at)]


def release(run_id: str) -> None:
    """Drop this run's outstanding job — its gate cleared, or it is running again.

    The dedupe is structural rather than timed: a job lives exactly as long as the
    stop that caused it, so the next announcement of a *new* stop dispatches, and a
    re-render of the same one does not.
    """
    job_id = _LEDGER.by_run.pop(run_id, "")
    if job_id:
        _LEDGER.jobs.pop(job_id, None)


def _spend(run_id: str, now: float) -> bool:
    """Take a slot from this run's rolling budget, or report that there is none left."""
    count, window = _budget()
    spent = _LEDGER.spawns.setdefault(run_id, deque())
    while spent and (now - spent[0]) > window:
        spent.popleft()
    if len(spent) >= count:
        return False
    spent.append(now)
    return True


def _dispatch(job: AttendJob, spawner: Spawner | None) -> AttendJob | None:
    """Publish the job, and in headless mode hand it to a process. Never raises.

    A dispatch that fails is a dashboard that keeps working: the rules loop this is
    reached from is wrapped for the same reason — the watch on a stalled run must not
    itself be able to stall.
    """
    _LEDGER.jobs[job.job_id] = job
    _LEDGER.by_run[job.run_id] = job.job_id
    if mode() == HEADLESS:
        try:
            (spawner or spawn_headless)(job)
        except Exception:
            logger.exception("attend: could not spawn an attendant for %s", job.run_id)
    return job


def _blocked(run_id: str, now: float) -> bool:
    """Whether anything already outstanding or already spent forbids this dispatch."""
    if mode() == OFF or run_id in _LEDGER.by_run:
        return True
    return not _spend(run_id, now)


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
    """A run just parked on a gate that is new to its row. Returns the job, or None.

    The caller passes gates it computed as *fresh* against the run's own ``questions``
    listing, which is the authority on what it is blocked on — so there is no hash to
    invent and no gate age to compute. A gate already known to the row is not fresh; a
    re-armed one is.
    """
    now = now if now is not None else time.time()
    if kind and kind != ATTENDABLE_KIND:
        return None
    haystack = f"{gate_path}\n{question}".lower()
    if any(pattern in haystack for pattern in deny_patterns()):
        return None
    if _blocked(run_id, now):
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
    """``(failure_class, node, body)`` from the run's own handoff entry, if it wrote one.

    This half of the attendant has the machine-readable class the gates lack: the
    driver's ``kind="failure"`` entry names what broke and where, so the route is read
    rather than inferred from prose. A SIGKILL leaves no entry at all, and the empty
    answer is what sends the attendant to ``checkpoint.json`` and ``events.jsonl``.
    Reads the run dir, not the socket, which is the only reason it works on a corpse.
    """
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
    """A run ended without reaching its own end. Returns the job, or None.

    The caller decides that it *is* a death — the two endings that are not are
    excluded there, where the exit code and the terminal live: ``RELOAD_EXIT_CODE``
    is the supervisor restarting on purpose, and an interrupt is a person already
    deciding.
    """
    now = now if now is not None else time.time()
    if _blocked(run_id, now):
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
