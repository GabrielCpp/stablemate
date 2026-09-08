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

- ``headless`` spawns ``claude -p`` with the job on stdin, in the run's own
  workspace, and **owns that process**: it mints the session id up front, writes a
  row before the first byte of output, waits on the process in a thread of its own,
  and flips the row when it exits. There is no poller and no reaper here.
- ``session`` spawns nothing and publishes the job instead, for an interactive
  session to claim from ``GET /api/attend/queue`` — one fleet-wide endpoint rather
  than one poll loop per run id. A session job gets no row and no transcript: what
  it did is in the operator's own terminal.

The setting lives in ``[groom.attend]`` of the unified home config, so a toggle in
the dashboard takes effect on the next dispatch with nothing restarted. The
``GROOM_ATTEND*`` environment variables still work, and are read only where the
config says nothing.
"""

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

from groom import attend_transcript, store

logger = logging.getLogger(__name__)

#: The three modes ``GROOM_ATTEND`` selects between. ``off`` is the default and is
#: not a degraded state: an unconfigured groom is exactly the dashboard it was.
OFF, SESSION, HEADLESS = "off", "session", "headless"

#: The doctrine the headless dispatch carries, shipped as groom's own package data.
#: It is groom-specific — nothing but the attendant reads it — so it travels in the
#: wheel rather than in the shared base library, and is present wherever groom is.
PROMPT_PATH = Path(__file__).parent / "prompts" / "attend-gate.md"

#: What a gate's own ``kind`` must be for the attendant to touch it. A ``machine``
#: wait is a measurement, not a human failing to answer — a 40-hour one is normal —
#: and dispatching an agent at it would interrupt the thing it is waiting for.
ATTENDABLE_KIND = "operator"

_INBOX_FILE = "inbox.jsonl"


#: The last config file we resolved settings from, as ``(path, mtime, settings)``.
#: Resolution parses TOML, and dispatch asks for the settings on every announcement
#: on every rules tick — so the answer is cached, and the mtime is what invalidates
#: it. A toggle in the dashboard rewrites the file, which moves the mtime, which is
#: why nothing has to be restarted and nothing has to be signalled.
_SETTINGS_CACHE: tuple[str, float, core_config.AttendSettings] | None = None


def settings() -> core_config.AttendSettings:
    """The effective ``[groom.attend]`` settings: config first, then env, then default.

    Read per call rather than at import, like :mod:`groom.notify`, so a test can set
    either source without reimporting the module.
    """
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
        # A config groom cannot read is not a reason to stop being a dashboard. Off is
        # the safe reading of an unreadable setting: it dispatches nothing.
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
    """Substrings that veto a dispatch, matched against the gate path and question.

    Some gates are genuinely not an agent's to answer, and the tree says so at the
    site: a red PR that cannot be pushed is an infrastructure or credential wall, not
    a question an agent clears by trying harder.
    """
    return settings().deny


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

    def reason(self) -> str:
        """One line saying why this dispatch happened, for the row and the pane.

        The pane lists attendances stripped of their context — a season of them, read
        back at once — so each row has to carry the *because* with it. A gate's is its
        own path, a death's is the class the driver recorded.
        """
        if self.kind == "gate":
            return f"parked on {self.gate_path or 'an operator gate'}"
        return f"died: {self.failure_class or 'no failure handoff recorded'}"

    def gate_body(self) -> str:
        """The gate as it is on disk, falling back to what the caller passed down.

        The ``question`` handed in is the **dashboard's preview**, not the gate:
        :func:`groom.gates.extract_question` keeps only the ``## Questions from the
        agent`` section and truncates it to 4000 characters. That is the right shape for
        a row in a table and the wrong shape for the only copy an attendant ever gets —
        a 20KB adjudication arrives cut mid-word with most of its findings missing, and
        an attendant cannot fix a finding it was never shown.

        So the file wins when it can be read, and the preview is the fallback for a gate
        that has since been answered or moved. This is also what the restart path has
        always done (:func:`_job_from_row` re-reads the file), and the two disagreeing
        meant a resurrected attendant saw more than the one it replaced.
        """
        if self.gate_path:
            try:
                text = Path(self.gate_path).read_text(errors="replace").strip()
            except OSError:
                text = ""
            if text:
                return text
        return self.question or "(the run's questions listing is authoritative)"

    def facts(self) -> str:
        """The job as the attendant reads it: named facts, and the gate body verbatim.

        The gate is passed **unparsed**. Three incompatible gate formats are in the
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
        """The library prompt, then the job. Doctrine first so the facts land inside it."""
        return f"{_doctrine()}\n\n---\n\n{self.facts()}\n"


def _doctrine() -> str:
    """The attendant prompt shipped with groom, or a refusal that names its absence.

    It ships in the package, so the fallback covers a mangled install rather than an
    unconfigured machine. Failing soft would be the worst option available: a spawned
    agent with the facts and none of the rules is exactly the attendant that answers a
    gate to make a run move. So the fallback text tells it to stop, not to improvise.
    """
    try:
        return PROMPT_PATH.read_text()
    except OSError:
        return (
            "The attendant prompt is missing from this groom install "
            f"({PROMPT_PATH} is unreadable). Do not attempt the repair — record what "
            "you were handed in the run's inbox.jsonl and stop."
        )


class Spawner(Protocol):
    """How a job reaches an attendant. A port so a test needs no agent and no process."""

    def __call__(self, job: AttendJob) -> None: ...


def _mints_session(cli: str) -> bool:
    """Whether this CLI takes ``--session-id``. Only claude does, by design.

    The feature is claude-only and says so: ``GROOM_ATTEND_CLI`` may point somewhere
    else and that still dispatches, but the row carries no session id and no
    transcript is ever fetched for it — an empty record beats a wrong one.
    """
    return Path(cli).name.startswith("claude")


def _launch(job: AttendJob, session_id: str) -> subprocess.Popen[str]:
    """``claude -p`` on the job, in the run's workspace, as its own process group.

    Spawned through workhorse's :class:`ProcessSupervisor` rather than a bare
    ``Popen``: it aligns the child's ``$PWD`` with its ``cwd`` (an agent CLI that
    trusts ``PWD`` otherwise works in groom's directory instead of the run's) and it
    rides out the exec window of a CLI rewriting itself mid-update.

    The prompt goes on **stdin**, not ``argv`` — a gate body is a document.

    The session id is **minted here and passed in**, not captured from the output.
    Captured, it exists only once the CLI has said something; minted, the row can be
    written before the first byte, which is what makes a groom that dies one second
    after the spawn still know what it spawned.
    """
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
    """What the run looked like when the attendant let go of it.

    This is the column that says whether an attendance *worked*, and it is read at
    exit rather than asserted by the attendant: ``ANSWERED`` on a gate is a pass,
    ``AWAITING_OPERATOR`` is an attendant that read the gate and declined it — which
    is a correct outcome and not a miss. For a death there is no gate to read, so the
    checkpoint's own node is recorded instead.
    """
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
    """Wait on the attendant, bring its transcript home, and flip its row. No deadline.

    The thread that spawned the process is the thread that closes the row — there is
    no poller and no reaper, because there is nothing to poll for: a process has an
    exit code and ``wait`` is how you learn it. A daemon thread rather than an
    asyncio task, so it neither keeps groom's loop alive nor cares whether the
    dispatch came from a request handler or a rules tick.

    An attendant that runs for a day is not a failure; the run it is repairing is
    parked and holding its state, and killing the repair is strictly worse than
    waiting for it. The only way one ends early is the Stop button.
    """

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
    """Kill a running attendant and hand the run back. ``SIGTERM``, then ``SIGKILL``.

    Not a way to abandon a run — a way to take it back: the operator has decided to
    work this one from their own terminal, and two agents in one tree against one
    checkpoint is the thing being prevented. The hard kill is unconditional rather
    than conditional on the term landing, because a half-dead agent CLI still holds
    the workspace, and the whole group is signalled because its children are the part
    that lingers.

    The row is flipped here rather than left to the owning thread: after a groom
    restart there is no owning thread, and a row that stays ``running`` forever is
    exactly the state boot recovery would try to resurrect.
    """
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
    """Whether that pid is still a process. A dead attendant is what boot recovery finds."""
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
    """Restart every attendant groom was holding when it died. Returns how many.

    An attendant is a child of groom, so a groom restart kills it — and claude sends
    no heartbeat, so a row left saying ``running`` is the only trace. The fix is not a
    new entry: this is still the same attendance of the same stopped run, so the row
    is **updated in place** with a fresh session id appended to its ordered list. The
    previous transcript is not fed to the new attempt: it starts clean, finds the
    repair already made if it was, and completes.

    A row whose pid is still alive is left strictly alone — that is a second groom, or
    an attendant that outlived its parent, and either way killing it helps nobody.

    Only ``headless`` restarts anything. In ``session`` mode groom spawns nothing by
    definition, and ``off`` means the operator turned the attendant off while one was
    running — in both, a dead pid is closed rather than resurrected, because a row that
    stayed ``running`` would be a run this groom never attends again.
    """
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
    """Rebuild the job a stored row describes, re-reading whatever went stale.

    The gate body and the failure handoff are deliberately **not** stored: they live
    in the run dir, they may have moved on since the row was written, and the current
    text is the one a restarted attendant should act on.
    """
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
    """Everything the module remembers between announcements, in one object.

    A dataclass rather than two module globals because the two fields have an
    invariant between them — a job in ``by_run`` is in ``jobs`` — and a test that
    resets one and not the other would be testing a state the running process never
    reaches. :func:`reset` clears both.

    This is the **process-local** half of the dedupe, and it is the whole of it for
    ``session`` mode, where nothing is spawned and there is no row. A headless
    dispatch is deduped by the ``running`` row instead, which is what survives a
    groom restart.
    """

    #: job_id → job, the fleet-wide outstanding set `GET /api/attend/queue` renders.
    jobs: dict[str, AttendJob] = field(default_factory=dict)
    #: run_id → job_id. One in-flight attendant per run, always: a second one would
    #: be two agents patching the same tree against the same checkpoint.
    by_run: dict[str, str] = field(default_factory=dict)


_LEDGER = _Ledger()


def reset() -> None:
    """Forget every outstanding job and spent slot — for tests, and a fresh process."""
    _LEDGER.jobs.clear()
    _LEDGER.by_run.clear()


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


def _blocked(run_id: str) -> bool:
    """Whether an attendant is already on this run — the whole rule, in one place.

    One attendant per run, serial. The durable half is the ``running`` row: it is what
    still says *someone is on this* after a groom restart, and it is why a run that is
    still blocked ten ticks later does not accumulate ten claudes. The in-memory half
    covers ``session`` mode, where the job was published and no row exists.
    """
    if mode() == OFF or run_id in _LEDGER.by_run:
        return True
    try:
        return store.attend_running_for_run(run_id) is not None
    except Exception:
        # A store that cannot answer must not become a store that dispatches forever.
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
