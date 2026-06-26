from __future__ import annotations
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class ArtifactWriter:
    CHECKPOINT_FILE = "checkpoint.json"
    # Append-only, per-node event log (enter/done/terminal) with timestamps.
    # Unlike checkpoint.json (overwritten every step), this preserves the full
    # node-visit history so spend/output can be attributed to individual nodes.
    EVENTS_FILE = "events.jsonl"

    def __init__(self, workflow_name: str, runs_dir: Path, run_id: str | None = None) -> None:
        # A fixed run_id (e.g. the program name, used by --auto) gives a single
        # stable run dir that is resumed in place across restarts; otherwise a
        # timestamped+random id makes a fresh, unique dir per invocation.
        if run_id is None:
            run_id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:4]
        self.run_dir = runs_dir / f"{workflow_name}-{run_id}"
        self.run_dir.mkdir(parents=True, exist_ok=True)
        # A fresh start may reuse a stable dir whose previous run already finished
        # (e.g. --auto restarting after a terminal run). Drop any stale checkpoint so
        # an interruption before this run's first checkpoint can't resurrect the old
        # one on the next auto-resume; this run starts from the graph's start node.
        (self.run_dir / self.CHECKPOINT_FILE).unlink(missing_ok=True)
        # A fresh start re-runs from the graph's start node with seq reset to 0, so
        # any prior event log in a reused (stable-id) dir belongs to a different run
        # and would interleave confusingly — drop it, mirroring the checkpoint above.
        (self.run_dir / self.EVENTS_FILE).unlink(missing_ok=True)
        self._started_at = datetime.now(timezone.utc).isoformat()
        self._workflow_name = workflow_name
        self._run_id = run_id
        # Monotonic checkpoint sequence. Each write_checkpoint bumps it; a node's
        # completion marker records the seq it ran under, so resume can tell "this
        # node finished under the current checkpoint" (fast-forward) from "stale
        # artifact from an earlier loop visit" (must re-run).
        self._seq = 0
        self._write_run_json(terminal=None)

    @classmethod
    def resume(cls, run_dir: Path) -> "ArtifactWriter":
        """Re-bind to an existing run directory (for checkpoint resume) without
        creating a new run or clobbering its step artifacts."""
        self = cls.__new__(cls)
        self.run_dir = run_dir
        try:
            meta = json.loads((run_dir / "run.json").read_text())
        except (FileNotFoundError, json.JSONDecodeError):
            meta = {}
        self._workflow_name = meta.get("workflow", run_dir.name)
        self._run_id = meta.get("run_id", run_dir.name)
        self._started_at = meta.get("started_at", datetime.now(timezone.utc).isoformat())
        # Continue the checkpoint sequence from where it left off so new checkpoints
        # don't collide with the completion markers already on disk.
        self._seq = 0
        try:
            self._seq = json.loads((run_dir / cls.CHECKPOINT_FILE).read_text()).get("seq", 0)
        except (FileNotFoundError, json.JSONDecodeError):
            pass
        # Re-mark the run as in-progress (terminal=None) until it finishes.
        self._write_run_json(terminal=None)
        return self

    @classmethod
    def at(cls, run_dir: Path, workflow_name: str, run_id: str) -> "ArtifactWriter":
        """Create a FRESH writer rooted directly at ``run_dir`` (no
        ``runs_dir/<name>-<id>`` derivation). Used for a flow's nested scope, which
        lives under the parent run's node dir. Mirrors ``__init__``'s fresh-start
        hygiene (drop any stale checkpoint/event log from a prior visit)."""
        self = cls.__new__(cls)
        self.run_dir = run_dir
        self.run_dir.mkdir(parents=True, exist_ok=True)
        (self.run_dir / cls.CHECKPOINT_FILE).unlink(missing_ok=True)
        (self.run_dir / cls.EVENTS_FILE).unlink(missing_ok=True)
        self._started_at = datetime.now(timezone.utc).isoformat()
        self._workflow_name = workflow_name
        self._run_id = run_id
        self._seq = 0
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
            return ArtifactWriter.resume(sub_dir)
        return ArtifactWriter.at(sub_dir, flow_name, node_id)

    def write_checkpoint(self, current_id: str, context: dict[str, Any]) -> None:
        """Atomically record the node about to run and the context going into it,
        so a crashed run can resume from exactly this point. Bumps the checkpoint
        sequence; the node that runs next records this seq when it completes."""
        self._seq += 1
        data = {
            "workflow": self._workflow_name,
            "run_id": self._run_id,
            "current_id": current_id,
            "seq": self._seq,
            "context": context,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        path = self.run_dir / self.CHECKPOINT_FILE
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps(data, indent=2))
        tmp.replace(path)  # atomic rename on the same filesystem
        # Mirror the node-entry to the append-only event log (history-preserving).
        self._append_event(node_id=current_id, phase="enter")

    def _append_event(self, node_id: str, phase: str, **fields: Any) -> None:
        """Append one timestamped line to the per-node event log. Best-effort:
        instrumentation must never crash a run, so I/O errors are swallowed.
        ``phase`` is one of "enter" | "done" | "terminal"; extra ``fields`` (e.g.
        a resolved model name, passed by the runner) are merged into the record."""
        record = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "seq": self._seq,
            "node": node_id,
            "phase": phase,
            **fields,
        }
        try:
            with (self.run_dir / self.EVENTS_FILE).open("a") as f:
                f.write(json.dumps(record) + "\n")
        except OSError:
            pass

    def read_events(self) -> list[dict[str, Any]]:
        """Read the append-only event log in order (empty if absent/unwritten).
        Consumers (e.g. a cost-per-node scorecard) join these node windows against
        timestamped provider spend and git commits."""
        path = self.run_dir / self.EVENTS_FILE
        if not path.exists():
            return []
        events: list[dict[str, Any]] = []
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
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

    def read_checkpoint(self) -> dict[str, Any] | None:
        path = self.run_dir / self.CHECKPOINT_FILE
        if not path.exists():
            return None
        return json.loads(path.read_text())

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
        (step_dir / "prompt.md").write_text(prompt)
        (step_dir / "output.json").write_text(json.dumps(output, indent=2))
        (step_dir / "context_after.json").write_text(json.dumps(context_after, indent=2))
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
        (step_dir / "branch.json").write_text(
            json.dumps({"path": path, "value": value, "next": next_node}, indent=2)
        )
        self._write_done(node_id, next_node)

    def finish(self, terminal: str) -> None:
        (self.run_dir / "context.json").write_text("{}")  # overwritten by controller
        self._write_run_json(terminal=terminal)
        self._append_event(node_id="<run>", phase="terminal", terminal=terminal)

    def write_final_context(self, context: dict[str, Any]) -> None:
        (self.run_dir / "context.json").write_text(json.dumps(context, indent=2))

    def _write_run_json(self, terminal: str | None) -> None:
        data: dict[str, Any] = {
            "workflow": self._workflow_name,
            "run_id": self._run_id,
            "started_at": self._started_at,
            "ended_at": datetime.now(timezone.utc).isoformat() if terminal else None,
            "terminal": terminal,
        }
        (self.run_dir / "run.json").write_text(json.dumps(data, indent=2))
