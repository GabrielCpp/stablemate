from __future__ import annotations
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class ArtifactWriter:
    CHECKPOINT_FILE = "checkpoint.json"

    def __init__(self, workflow_name: str, runs_dir: Path, run_id: str | None = None) -> None:
        # A fixed run_id (e.g. the program name, used by --auto) gives a single
        # stable run dir that is resumed in place across restarts; otherwise a
        # timestamped+random id makes a fresh, unique dir per invocation.
        if run_id is None:
            run_id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:4]
        self.run_dir = runs_dir / f"{workflow_name}-{run_id}"
        self.run_dir.mkdir(parents=True, exist_ok=True)
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

    def _write_done(self, node_id: str, next_node: str | None) -> None:
        """Mark ``node_id`` complete under the current checkpoint seq, recording the
        node to advance to. Resume matches this seq against the checkpoint's to know
        the node truly finished under that checkpoint (vs. a stale prior-visit run)."""
        (self.run_dir / node_id).mkdir(exist_ok=True)
        (self.run_dir / node_id / "done.json").write_text(
            json.dumps({"seq": self._seq, "next": next_node}, indent=2)
        )

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
