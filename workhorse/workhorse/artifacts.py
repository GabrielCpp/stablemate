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
    """The run's working tree right now, or None when there was nothing to observe."""
    state = gitstate.current_state()
    if not state.observed:
        return None
    return RepoObservation(
        path=state.path,
        root=state.root,
        origin=state.origin,
        head=state.head,
        branch=state.branch,
        dirty=state.dirty,
    )


def _process_alive(pid: int) -> bool:
    """Whether ``pid`` is currently a running process on this host."""
    if pid <= 0:
        return False
    try:
        return Path(f"/proc/{pid}").exists()
    except OSError:
        return True


def _clear_stale_run(run_dir: Path) -> None:
    """Empty a stable run dir that a *previous* run left behind, before reusing it."""
    if not run_dir.exists():
        return
    try:
        shutil.rmtree(run_dir)
    except OSError:
        (run_dir / ArtifactWriter.CHECKPOINT_FILE).unlink(missing_ok=True)
        (run_dir / ArtifactWriter.EVENTS_FILE).unlink(missing_ok=True)


def write_unlinked(path: Path, text: str) -> None:
    """Replace ``path``'s contents without writing through any link to it."""
    path.unlink(missing_ok=True)
    path.write_text(text, encoding="utf-8")


class ArtifactWriter:
    CHECKPOINT_FILE = "checkpoint.json"
    EVENTS_FILE = "events.jsonl"
    TURNS_DIR = "turns"

    def __init__(
        self, workflow_name: str, runs_dir: Path, run_id: str | None = None
    ) -> None:
        if run_id is None:
            run_id = (
                datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
                + "-"
                + uuid.uuid4().hex[:4]
            )
        self.run_dir = runs_dir / f"{workflow_name}-{run_id}"
        self._turns_root = self.run_dir
        _clear_stale_run(self.run_dir)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self._started_at = datetime.now(timezone.utc).isoformat()
        self._workflow_name = workflow_name
        self._run_id = run_id
        self._seq = 0
        self._repo_start = _observe_repo()
        self._profile = ""
        self._profile_config: dict[str, Any] = {}
        self._worktree_path = ""
        self._worktree_branch = ""
        self._previous_process_died_at = None
        self._previous_process_pid = None
        self._write_run_json(terminal=None)

    @property
    def run_id(self) -> str:
        return self._run_id

    @property
    def started_at(self) -> str:
        """ISO-8601 UTC start time."""
        return self._started_at

    @property
    def worktree_path(self) -> str:
        """The worktree this run was dispatched into, or "" if it was not."""
        return self._worktree_path

    @property
    def worktree_branch(self) -> str:
        """The branch cut for this run's worktree, or "" if it was not dispatched."""
        return self._worktree_branch

    @classmethod
    def resume(cls, run_dir: Path) -> "ArtifactWriter":
        """Re-bind to an existing run directory (for checkpoint resume) without creating a new run or clobbering its step artifacts."""
        self = cls.__new__(cls)
        self.run_dir = run_dir
        self._turns_root = run_dir
        try:
            record = parse_run_record((run_dir / "run.json").read_text())
        except (OSError, ValidationError):
            record = RunRecord()
        self._workflow_name = record.workflow or run_dir.name
        self._run_id = record.run_id or run_dir.name
        self._started_at = record.started_at or datetime.now(timezone.utc).isoformat()
        self._seq = 0
        try:
            self._seq = parse_checkpoint(
                (run_dir / cls.CHECKPOINT_FILE).read_text()
            ).seq
        except (OSError, ValidationError):
            pass
        self._repo_start = record.repo_start or _observe_repo()
        self._profile = record.profile
        self._profile_config = dict(record.profile_config)
        self._worktree_path = record.worktree_path
        self._worktree_branch = record.worktree_branch
        self._previous_process_died_at = None
        self._previous_process_pid = None
        if (
            record.terminal is None
            and record.pid is not None
            and not _process_alive(record.pid)
        ):
            self._previous_process_died_at = datetime.now(timezone.utc).isoformat()
            self._previous_process_pid = record.pid
        self._write_run_json(terminal=None)
        return self

    @classmethod
    def at(cls, run_dir: Path, workflow_name: str, run_id: str) -> "ArtifactWriter":
        """Create a FRESH writer rooted directly at ``run_dir`` (no ``runs_dir/<name>-<id>`` derivation)."""
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
        self._worktree_path = ""
        self._worktree_branch = ""
        self._previous_process_died_at = None
        self._previous_process_pid = None
        self._write_run_json(terminal=None)
        return self

    def subscope(
        self, node_id: str, flow_name: str, *, resume: bool = False
    ) -> "ArtifactWriter":
        """Writer for a flow invoked at ``node_id``, rooted under this run's node dir (``<run>/<node_id>/_flow``)."""
        sub_dir = self.run_dir / node_id / "_flow"
        if resume and (sub_dir / self.CHECKPOINT_FILE).exists():
            child = ArtifactWriter.resume(sub_dir)
        else:
            child = ArtifactWriter.at(sub_dir, flow_name, node_id)
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
        """Checkpoint a Python state machine: the state to (re-)enter and its arguments."""
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
        """Put the checkpoint on disk in one indivisible step."""
        path = self.run_dir / self.CHECKPOINT_FILE
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(checkpoint.model_dump_json(indent=2))
        tmp.replace(path)

    def record_node(self, node_id: str, phase: NodePhase, **fields: Any) -> None:
        """Public entry to the append-only event log."""
        self._append_event(node_id=node_id, phase=phase, **fields)

    def read_output(self, node_id: str) -> dict[str, Any] | None:
        """A node's recorded ``output.json``, or None when it has not run."""
        path = self.run_dir / node_id / "output.json"
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text())
        except json.JSONDecodeError:
            return None
        return data if isinstance(data, dict) else {"value": data}

    def _append_event(self, node_id: str, phase: NodePhase, **fields: Any) -> None:
        """Append one timestamped line to the per-node event log."""
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
        otel.record_event(event)

    def read_events(self) -> list[NodeEvent]:
        """Read the append-only event log in order (empty if absent/unwritten)."""
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
        """Mark ``node_id`` complete under the current checkpoint seq, recording the node to advance to."""
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
        """The run's checkpoint, or None when it has not written one yet."""
        path = self.run_dir / self.CHECKPOINT_FILE
        if not path.exists():
            return None
        return parse_checkpoint(path.read_text())

    @staticmethod
    def _write_unlinked(path: Path, text: str) -> None:
        write_unlinked(path, text)

    def visit_dir(self, node_id: str) -> Path | None:
        """Where this visit of ``node_id`` keeps its own copy, or None when there is no visit to name."""
        key = turnkey.current()
        if key is None or key.node != node_id:
            return None
        return self._turns_root / self.TURNS_DIR / key.slug

    def _keep_visit_copy(self, node_id: str, written: list[Path]) -> None:
        """Copy this visit's artifacts into ``turns/<visit>/``."""
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
        self._write_unlinked(
            step_dir / "context_after.json", json.dumps(context_after, indent=2)
        )
        self._keep_visit_copy(
            node_id,
            [
                step_dir / "prompt.md",
                step_dir / "output.json",
                step_dir / "context_after.json",
            ],
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
        """Record that an operator interrupt (Ctrl-C) stopped the run while ``node_id`` was in flight."""
        self._append_event(node_id=node_id, phase="error", error=error)
        self._write_run_json(terminal=None, error=error)

    def record_profile(
        self, profile: str, tables: dict[str, Any] | None = None
    ) -> None:
        """Record which config profile this run's models come from, and what it held."""
        self._profile = profile
        self._profile_config = dict(tables or {})
        self._write_run_json(terminal=None)

    def record_worktree(self, path: str, branch: str) -> None:
        """Record the worktree and branch this run was dispatched into."""
        self._worktree_path = path
        self._worktree_branch = branch
        self._write_run_json(terminal=None)

    def record_launch(self, argv: list[str], resume_argv: list[str], cwd: str) -> None:
        """Record how *this process* was launched, in ``launch.json`` beside ``run.json``."""
        record = LaunchRecord(
            argv=list(argv),
            resume_argv=list(resume_argv),
            cwd=cwd,
            program=resume_argv[0] if resume_argv else "",
            pid=os.getpid(),
            started_at=datetime.now(timezone.utc).isoformat(),
            resume_generation=turnkey.read_generation(self.run_dir),
            container=Path("/.dockerenv").exists(),
        )
        try:
            (self.run_dir / "launch.json").write_text(record.model_dump_json(indent=2))
        except OSError:
            pass

    def finish(self, terminal: str) -> None:
        (self.run_dir / "context.json").write_text("{}")
        self._previous_process_died_at = None
        self._previous_process_pid = None
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
            repo_end=_observe_repo() if terminal else None,
            profile=self._profile,
            profile_config=self._profile_config,
            worktree_path=self._worktree_path,
            worktree_branch=self._worktree_branch,
            previous_process_died_at=self._previous_process_died_at,
            previous_process_pid=self._previous_process_pid,
        )
        (self.run_dir / "run.json").write_text(record.model_dump_json(indent=2))
