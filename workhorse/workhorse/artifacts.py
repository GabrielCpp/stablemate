from __future__ import annotations
import json
import os
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from workhorse import gitstate, otel, turnkey
from workhorse.records import (
    Checkpoint,
    LaunchRecord,
    NodeEvent,
    NodePhase,
    PyflowCheckpoint,
    RepoObservation,
    RunRecord,
    parse_checkpoint,
    parse_run_record,
)


def _observe_repo() -> RepoObservation | None:
    """The run's working tree right now, or None when there was nothing to observe.

    None rather than a zeroed record on purpose: an absent observation is honest about a
    cwd that is not a repository (or a caller — a test, a library embedder — that never
    bound one), whereas ``dirty: false`` there is a claim nobody made.
    """
    state = gitstate.current_state()
    if not state.observed:
        return None
    return RepoObservation(
        path=state.path, head=state.head, branch=state.branch, dirty=state.dirty
    )


def _clear_stale_run(run_dir: Path) -> None:
    """Empty a stable run dir that a *previous* run left behind, before reusing it.

    A params-derived run id is deterministic (see :mod:`workhorse.rundir`), so re-running
    the same command lands on the same directory. That is the whole point when the previous
    run is resumable — but when it finished, the caller starts fresh *in that same dir*, and
    the previous run's per-node subdirectories are then this run's artifacts as far as
    anything reading the directory can tell.

    Deleting only the checkpoint and the event log — which is what this used to do — is the
    worst of the two halves: it destroys the record that an earlier run existed while
    keeping that run's evidence, unlabelled. A link-shortener benchmark run demonstrated it
    exactly: a re-run that passed every story and never entered ``flag_qa_failure`` or
    ``flag_epic_blocked`` shipped a run dir containing both nodes' output, left by the
    failed run before it. Its 57 events mention neither. A post-mortem over that directory
    reports a clean run as having flagged a QA failure and blocked an epic, and the reader
    has nothing on disk to catch it with.

    So the fresh start empties the directory. Preserving the old run for comparison is a
    real want, but it is not this function's: every location inside ``runs_dir`` is matched
    by ``glob("*")``, so an archive dir here would be counted as a run by anything
    aggregating the tree — including the benchmark harness's reliability figures. Whoever
    wants the old bytes copies them aside *before* launching, where the intent is explicit.

    Fail-soft, because a run must not die over housekeeping: if the tree cannot be removed,
    fall back to unlinking the two files that would actively corrupt this run — a stale
    checkpoint (an interruption before this run's first checkpoint would otherwise resurrect
    the old one on the next auto-resume) and a stale event log (whose seq numbering restarts
    at 0 here, so the two runs' events would interleave).
    """
    if not run_dir.exists():
        return
    try:
        shutil.rmtree(run_dir)
    except OSError:
        (run_dir / ArtifactWriter.CHECKPOINT_FILE).unlink(missing_ok=True)
        (run_dir / ArtifactWriter.EVENTS_FILE).unlink(missing_ok=True)


class ArtifactWriter:
    CHECKPOINT_FILE = "checkpoint.json"
    # Append-only, per-node event log (enter/done/terminal) with timestamps.
    # Unlike checkpoint.json (overwritten every step), this preserves the full
    # node-visit history so spend/output can be attributed to individual nodes.
    EVENTS_FILE = "events.jsonl"
    # Per-visit copies of what a node was given and what it answered. One directory per
    # agent-node visit, named by the visit key, so lap 5's prompt still exists when lap 5
    # turns out to be the one that went wrong.
    TURNS_DIR = "turns"

    def __init__(self, workflow_name: str, runs_dir: Path, run_id: str | None = None) -> None:
        # A fixed run_id (e.g. the program name, used by --auto) gives a single
        # stable run dir that is resumed in place across restarts; otherwise a
        # timestamped+random id makes a fresh, unique dir per invocation.
        if run_id is None:
            run_id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:4]
        self.run_dir = runs_dir / f"{workflow_name}-{run_id}"
        self._turns_root = self.run_dir
        _clear_stale_run(self.run_dir)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self._started_at = datetime.now(timezone.utc).isoformat()
        self._workflow_name = workflow_name
        self._run_id = run_id
        # Monotonic checkpoint sequence. Each write_state_checkpoint bumps it; a node's
        # completion marker records the seq it ran under, so resume can tell "this
        # node finished under the current checkpoint" (fast-forward) from "stale
        # artifact from an earlier loop visit" (must re-run).
        self._seq = 0
        self._repo_start = _observe_repo()
        # Set by `record_profile` once the driver knows which one the CLI selected; the
        # run dir exists before that, so the first write of run.json carries neither.
        self._profile = ""
        self._profile_config: dict[str, Any] = {}
        self._write_run_json(terminal=None)

    @property
    def run_id(self) -> str:
        return self._run_id

    @property
    def started_at(self) -> str:
        """ISO-8601 UTC start time. For a resumed run this is the ORIGINAL
        start restored from run.json, so wall-clock budgets survive --resume."""
        return self._started_at

    @classmethod
    def resume(cls, run_dir: Path) -> "ArtifactWriter":
        """Re-bind to an existing run directory (for checkpoint resume) without
        creating a new run or clobbering its step artifacts."""
        self = cls.__new__(cls)
        self.run_dir = run_dir
        self._turns_root = run_dir
        try:
            record = parse_run_record((run_dir / "run.json").read_text())
        # As with the checkpoint below: a missing file and an unparseable one are the two
        # ways a stale run dir disappoints us, and both mean "nothing recorded here".
        except (OSError, ValidationError):
            record = RunRecord()
        self._workflow_name = record.workflow or run_dir.name
        self._run_id = record.run_id or run_dir.name
        self._started_at = record.started_at or datetime.now(timezone.utc).isoformat()
        # Continue the checkpoint sequence from where it left off so new checkpoints
        # don't collide with the completion markers already on disk.
        self._seq = 0
        try:
            self._seq = parse_checkpoint((run_dir / cls.CHECKPOINT_FILE).read_text()).seq
        # `validate_json` reports malformed JSON as a ValidationError too, so the two
        # ways a stale run dir can disappoint us are the two caught here.
        except (OSError, ValidationError):
            pass
        # What the run started from is the previous process's observation, kept rather
        # than re-taken: a resume days later sees whatever the tree is *now*, which is a
        # different fact and belongs to this generation's spans. A run dir written before
        # this existed has none, and observing then is the honest fallback.
        self._repo_start = record.repo_start or _observe_repo()
        # Carried rather than cleared: the resuming process states its own profile through
        # `record_profile`, and one that states none has not *unset* the run's — it is
        # resuming the run as it was, which is exactly what re-writing this file empty
        # would erase.
        self._profile = record.profile
        self._profile_config = dict(record.profile_config)
        # Re-mark the run as in-progress (terminal=None) until it finishes.
        self._write_run_json(terminal=None)
        return self

    @classmethod
    def at(cls, run_dir: Path, workflow_name: str, run_id: str) -> "ArtifactWriter":
        """Create a FRESH writer rooted directly at ``run_dir`` (no
        ``runs_dir/<name>-<id>`` derivation). Used for a flow's nested scope, which
        lives under the parent run's node dir. Mirrors ``__init__``'s fresh-start
        hygiene — which means emptying the scope, not just dropping its checkpoint and
        event log.

        The difference matters more here than it does for a top-level run dir, because a
        flow node inside a loop re-enters this scope *within a single run*: the coder graph
        hands off to `Qa` once per story, onto the same ``<run>/qa/_flow``. Leaving the
        previous story's per-node output in place means the second story's flow starts
        holding the first story's answers — and :meth:`read_output` is a bare file-existence
        check whose contract is "None when it has not run". A state that asks for a node
        this pass never reached gets the previous story's value and cannot tell.
        """
        self = cls.__new__(cls)
        self.run_dir = run_dir
        self._turns_root = run_dir
        _clear_stale_run(run_dir)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self._started_at = datetime.now(timezone.utc).isoformat()
        self._workflow_name = workflow_name
        self._run_id = run_id
        self._seq = 0
        self._repo_start = _observe_repo()
        self._profile = ""
        self._profile_config = {}
        self._write_run_json(terminal=None)
        return self

    def subscope(
        self, node_id: str, flow_name: str, *, resume: bool = False
    ) -> "ArtifactWriter":
        """Writer for a flow invoked at ``node_id``, rooted under this run's node dir
        (``<run>/<node_id>/_flow``).

        ``resume`` MUST come from the engine's "are we re-entering this exact node
        after a kill?" signal — NOT from "does a checkpoint happen to exist". A flow
        that ran to completion ALSO leaves a checkpoint behind, so keying resume on
        mere checkpoint presence makes a SECOND invocation of the same flow node (a
        loop body calling a flow) fast-forward through the prior run's completion and
        silently skip the whole flow. So: resume in place ONLY for a genuine
        mid-flow resume; every fresh (re-)entry starts the child clean, which is what
        lets a flow inside a loop run again each iteration."""
        sub_dir = self.run_dir / node_id / "_flow"
        if resume and (sub_dir / self.CHECKPOINT_FILE).exists():
            child = ArtifactWriter.resume(sub_dir)
        else:
            child = ArtifactWriter.at(sub_dir, flow_name, node_id)
        # The visit archive stays at the top of the run, because re-entering this scope
        # empties it (see :meth:`at`) — a per-story flow would otherwise delete the
        # previous story's visits, which are the ones being kept for later.
        child._turns_root = self._turns_root
        return child

    def write_state_checkpoint(
        self,
        state: str,
        params: dict[str, Any],
        *,
        inputs: dict[str, Any],
        flow: str | None = None,
        ctx: Any = None,
        waiting_on: str | None = None,
    ) -> int:
        """Checkpoint a Python state machine: the state to (re-)enter and its arguments.

        The YAML engine's checkpoint is ``(current_id, context)`` — a node plus the
        whole ambient bag. This one is ``(state, params)``, which is the point: a flat
        dict of the next state's own named arguments, small enough to read and edit by
        hand at hour 30 of a stuck run.

        ``inputs`` and ``ctx`` ride along because resume must reconstruct the instance
        without re-running ``setup()`` — the tier table says ``self.ctx`` is written
        once, and a resume that called ``setup()`` again would be writing it twice.
        ``flow`` names the workflow *class*, so a bare ``--resume-latest`` re-enters the
        flow that wrote the checkpoint rather than the distribution's default one.

        ``waiting_on`` is what an ``Await`` is blocked on, written **before** the wait
        begins so "blocked on a human at <path>" is on disk whether or not this process
        survives the wait.

        ``engine: "pyflow"`` is a fail-closed discriminator: the two engines share a
        runs directory and a ``--resume-latest``, and neither can make sense of the
        other's checkpoint. Better to refuse than to misread.
        """
        self._seq += 1
        self._write_checkpoint(
            PyflowCheckpoint(
                workflow=self._workflow_name,
                run_id=self._run_id,
                flow=flow,
                state=state,
                params=params,
                waiting_on=waiting_on,
                inputs=inputs,
                ctx=ctx,
                seq=self._seq,
                updated_at=datetime.now(timezone.utc).isoformat(),
            )
        )
        self._append_event(node_id=state, phase="enter", waiting_on=waiting_on)
        return self._seq

    def _write_checkpoint(self, checkpoint: Checkpoint) -> None:
        """Put the checkpoint on disk in one indivisible step. Write-then-rename, so a
        kill mid-write leaves the previous checkpoint intact rather than half of this
        one — the resume path must never meet a truncated file."""
        path = self.run_dir / self.CHECKPOINT_FILE
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(checkpoint.model_dump_json(indent=2))
        tmp.replace(path)  # atomic rename on the same filesystem

    def record_node(self, node_id: str, phase: NodePhase, **fields: Any) -> None:
        """Public entry to the append-only event log.

        A state machine checkpoints per *state* and runs several nodes inside one, so
        its node entries need a way in that is not a checkpoint write. (The retired
        YAML engine never needed this: a node visit there was always bracketed by a
        checkpoint and a done marker, so appending was those two calls' side effect.)
        """
        self._append_event(node_id=node_id, phase=phase, **fields)

    def read_output(self, node_id: str) -> dict[str, Any] | None:
        """A node's recorded ``output.json``, or None when it has not run.

        Distinguishing "absent" from "empty" is the caller's job and matters: the
        template helper this replaces returned ``""`` for both.
        """
        path = self.run_dir / node_id / "output.json"
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text())
        except json.JSONDecodeError:
            return None
        return data if isinstance(data, dict) else {"value": data}

    def _append_event(self, node_id: str, phase: NodePhase, **fields: Any) -> None:
        """Append one timestamped line to the per-node event log. Best-effort:
        instrumentation must never crash a run, so I/O errors are swallowed.
        Extra ``fields`` (e.g. a resolved model name, passed by the runner) ride along
        top-level on the record, which is why ``NodeEvent`` allows them."""
        event = NodeEvent(
            ts=datetime.now(timezone.utc).isoformat(),
            seq=self._seq,
            node=node_id,
            phase=phase,
            **fields,
        )
        try:
            with (self.run_dir / self.EVENTS_FILE).open("a") as f:
                f.write(event.model_dump_json() + "\n")
        except OSError:
            pass
        # Mirror the record to the OTel exporter — this is the one choke point
        # every enter/done/terminal already funnels through (root run and nested
        # flow scopes alike), so node spans need no other hook. A no-op when
        # telemetry is off; never raises (see workhorse/otel.py).
        otel.record_event(event)

    def read_events(self) -> list[NodeEvent]:
        """Read the append-only event log in order (empty if absent/unwritten).
        Consumers (e.g. a cost-per-node scorecard) join these node windows against
        timestamped provider spend and git commits.

        A line that will not parse is skipped rather than raised on: this reads an
        append-only log that a kill can leave half-written, and a reader of
        instrumentation must not be the thing that fails."""
        path = self.run_dir / self.EVENTS_FILE
        if not path.exists():
            return []
        events: list[NodeEvent] = []
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                events.append(NodeEvent.model_validate_json(line))
            except ValidationError:
                continue
        return events

    def _write_done(self, node_id: str, next_node: str | None) -> None:
        """Mark ``node_id`` complete under the current checkpoint seq, recording the
        node to advance to. Resume matches this seq against the checkpoint's to know
        the node truly finished under that checkpoint (vs. a stale prior-visit run)."""
        (self.run_dir / node_id).mkdir(exist_ok=True)
        (self.run_dir / node_id / "done.json").write_text(
            json.dumps({"seq": self._seq, "next": next_node}, indent=2)
        )
        self._append_event(node_id=node_id, phase="done", next=next_node)

    def read_done(self, node_id: str) -> dict[str, Any] | None:
        path = self.run_dir / node_id / "done.json"
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text())
        except json.JSONDecodeError:
            return None

    def read_context_after(self, node_id: str) -> dict[str, Any] | None:
        path = self.run_dir / node_id / "context_after.json"
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text())
        except json.JSONDecodeError:
            return None

    def read_checkpoint(self) -> Checkpoint | None:
        """The run's checkpoint, or None when it has not written one yet. Raises
        ``ValidationError`` on a file that is neither engine's checkpoint — callers
        already on a failure path catch it; callers about to resume must not."""
        path = self.run_dir / self.CHECKPOINT_FILE
        if not path.exists():
            return None
        return parse_checkpoint(path.read_text())

    @staticmethod
    def _write_unlinked(path: Path, text: str) -> None:
        """Replace ``path``'s contents without writing through any link to it.

        The visit archive hardlinks these files, so a plain ``write_text`` would truncate
        the previous visit's kept copy through the shared inode — every archived prompt
        would end up holding the latest visit's text, which is the exact loss the archive
        exists to prevent.
        """
        path.unlink(missing_ok=True)
        path.write_text(text)

    def visit_dir(self, node_id: str) -> Path | None:
        """Where this visit of ``node_id`` keeps its own copy, or None when there is no
        visit to name.

        Guarded on the node because :mod:`workhorse.turnkey` names *agent* visits: a
        plain call node writing a step while the last agent visit is still the current
        key would otherwise file its output under that other node's visit.
        """
        key = turnkey.current()
        if key is None or key.node != node_id:
            return None
        return self._turns_root / self.TURNS_DIR / key.slug

    def _keep_visit_copy(self, node_id: str, written: list[Path]) -> None:
        """Copy this visit's artifacts into ``turns/<visit>/``.

        Hardlinked where the filesystem allows, so the second copy of a megabyte of
        rendered prompt usually costs an inode. The per-node directory these come from
        keeps its meaning of *latest visit* and its readers — this is additive.

        Best-effort throughout: keeping a record of a node must never be the thing that
        fails the node.
        """
        target = self.visit_dir(node_id)
        if target is None:
            return
        try:
            target.mkdir(parents=True, exist_ok=True)
            for src in written:
                dst = target / src.name
                dst.unlink(missing_ok=True)
                try:
                    os.link(src, dst)
                except OSError:
                    shutil.copyfile(src, dst)
        except OSError:
            pass

    def write_step(
        self,
        node_id: str,
        prompt: str,
        output: dict[str, Any],
        context_after: dict[str, Any],
        next_node: str | None = None,
    ) -> None:
        step_dir = self.run_dir / node_id
        step_dir.mkdir(exist_ok=True)
        self._write_unlinked(step_dir / "prompt.md", prompt)
        self._write_unlinked(step_dir / "output.json", json.dumps(output, indent=2))
        self._write_unlinked(step_dir / "context_after.json", json.dumps(context_after, indent=2))
        self._keep_visit_copy(
            node_id,
            [step_dir / "prompt.md", step_dir / "output.json", step_dir / "context_after.json"],
        )
        self._write_done(node_id, next_node)

    def write_branch(
        self,
        node_id: str,
        path: str,
        value: Any,
        next_node: str,
    ) -> None:
        step_dir = self.run_dir / node_id
        step_dir.mkdir(exist_ok=True)
        self._write_unlinked(
            step_dir / "branch.json",
            json.dumps({"path": path, "value": value, "next": next_node}, indent=2),
        )
        self._keep_visit_copy(node_id, [step_dir / "branch.json"])
        self._write_done(node_id, next_node)

    def record_interrupt(self, node_id: str, error: str) -> None:
        """Record that an operator interrupt (Ctrl-C) stopped the run while
        ``node_id`` was in flight.

        Without this an interrupted run is indistinguishable on disk from a wedged
        one: the node's ``enter`` event never gets its matching ``done``, and
        ``run.json`` stays exactly as it looks mid-node. Reading a multi-hour gap in
        ``events.jsonl`` then means going to the backend CLI's own session transcript
        to find out whether a human stopped it — the one place the fact was recorded.
        So the stop is written where the run's own history is: an ``error`` phase
        event closing that node's window, plus ``interrupted_at``/``error`` on
        ``run.json``.

        Deliberately NOT ``finish()``: a non-null ``terminal`` means "this run is
        over" to ``_auto_resolve``/``_find_latest_resumable``, and an interrupted run
        is precisely the one that must still auto-resume in place. ``resume()``
        rewrites ``run.json`` without the stamp, so it clears itself when the run
        picks back up.
        """
        self._append_event(node_id=node_id, phase="error", error=error)
        self._write_run_json(terminal=None, error=error)

    def record_profile(self, profile: str, tables: dict[str, Any] | None = None) -> None:
        """Record which config profile this run's models come from, and what it held.

        Written to ``run.json`` rather than to the checkpoint, because it is not state the
        run resumes *into*: the profile is re-read from the config file every turn, so a
        copy the run consulted would be the one thing an operator's edit could not reach.
        What the record buys is the two things the live re-read cannot give — a resume
        that knows which profile the run was launched under, and, weeks later, the model
        set as it stood at the start rather than as the file reads today.
        """
        self._profile = profile
        self._profile_config = dict(tables or {})
        self._write_run_json(terminal=None)

    def record_launch(self, argv: list[str], resume_argv: list[str], cwd: str) -> None:
        """Record how *this process* was launched, in ``launch.json`` beside ``run.json``.

        A run that is SIGKILL'd — OOM, a harness sweep, a hard crash — cannot report its
        own death, so it is noticed from outside by something that outlives it. That
        watcher could already tell the run was dead and that the checkpoint was intact;
        what the directory never said was the command. This is the command.

        Its own file rather than a ``run.json`` field because the two have different
        lifetimes: ``run.json`` is rewritten on every profile record, interrupt and
        terminal, while this is written once per process and read after that process is
        gone. Keeping it out of the churn means the record a watcher needs is not being
        rewritten at the moment the run dies.

        Best-effort, like every other record here: a directory that cannot be written is
        a run that is worse off unwatched, not a run that should stop.
        """
        record = LaunchRecord(
            argv=list(argv),
            resume_argv=list(resume_argv),
            cwd=cwd,
            program=resume_argv[0] if resume_argv else "",
            pid=os.getpid(),
            started_at=datetime.now(timezone.utc).isoformat(),
            resume_generation=turnkey.read_generation(self.run_dir),
            # The one fact a host-side reader cannot recover from the record itself: in a
            # container every path in it is namespace-local and re-spawning it on the host
            # runs something else, or nothing.
            container=Path("/.dockerenv").exists(),
        )
        try:
            (self.run_dir / "launch.json").write_text(record.model_dump_json(indent=2))
        except OSError:
            pass

    def finish(self, terminal: str) -> None:
        (self.run_dir / "context.json").write_text("{}")  # overwritten by controller
        self._write_run_json(terminal=terminal)
        self._append_event(node_id="<run>", phase="terminal", terminal=terminal)

    def write_final_context(self, context: dict[str, Any]) -> None:
        (self.run_dir / "context.json").write_text(json.dumps(context, indent=2))

    def _write_run_json(self, terminal: str | None, error: str | None = None) -> None:
        now = datetime.now(timezone.utc).isoformat()
        record = RunRecord(
            workflow=self._workflow_name,
            run_id=self._run_id,
            started_at=self._started_at,
            ended_at=now if terminal else None,
            terminal=terminal,
            interrupted_at=now if error and not terminal else None,
            error=error,
            pid=os.getpid(),
            repo_start=self._repo_start,
            # Observed only at a terminal. Every other write of this file happens on a
            # path where the run is still going, and an "end" recorded there would be
            # overwritten by the next one anyway — a walk of the tree per transition
            # bought nothing.
            repo_end=_observe_repo() if terminal else None,
            profile=self._profile,
            profile_config=self._profile_config,
        )
        (self.run_dir / "run.json").write_text(record.model_dump_json(indent=2))
