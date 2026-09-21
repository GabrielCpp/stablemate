"""Genesis as a state machine."""
from __future__ import annotations

from workhorse.pyflow import (
    Continue,
    Done,
    Workflow,
    WorkflowFailed,
)
from workhorse_workflows.coder.genesis.nodes import (
    genesis_git_init,
    init_skeleton,
    install_farrier,
    resolve_genesis_target,
    validate_genesis,
    write_agents_yml,
)
from workhorse_workflows.coder.shared.schemas.genesis import TargetClassification


class Genesis(Workflow):
    """A directory in, a repo the main loop will accept out."""

    target: str = ""
    service: str = ""
    service_root: str = ""
    packs: str = ""
    scaffolds: str = ""
    init_cmd: str = ""
    marker: str = ""
    markers: str = ""
    workflows: str = "coder"
    assistants: str = "claude"
    gates: str = ""


    def start(self) -> Continue:
        """Classify the target before anything mutates it."""
        found = self.call(
            resolve_genesis_target,
            self.target,
            self.service,
            self.service_root,
            self.marker,
            self._split(self.markers),
        )
        if not found.ok:
            raise WorkflowFailed(found.note or "no usable genesis target")
        if found.target_state == "existing":
            return Continue(found, self.config)
        return Continue(found, self.git_init)


    def git_init(self) -> Continue:
        """`git init` and one initial commit — the first mutating step, and it must be."""
        result = self.call(genesis_git_init, self._target().target_dir)
        return Continue(result, self.config)

    def config(self) -> Continue:
        """Merge the service into `agents.yml`, then decide whether it needs building."""
        found = self._target()
        result = self.call(
            write_agents_yml,
            found.target_dir,
            found.service,
            self._split(self.packs),
            self.service_root,
            found.markers,
            self._split(self.workflows),
            self._split(self.scaffolds),
            self._split(self.assistants),
            self._split(self.gates),
        )
        if found.service_state == "existing":
            return Continue(result, self.farrier)
        return Continue(result, self.skeleton)

    def skeleton(self) -> Continue:
        """Run the stack's native init tooling, and assert it left its marker behind."""
        result = self.call(
            init_skeleton, self._target().target_dir, self.service_root, self.init_cmd, self.marker
        )
        return Continue(result, self.farrier)

    def farrier(self) -> Continue:
        """Install the packs and render the scaffolds, then move on to validation."""
        result = self.call(
            install_farrier,
            self._target().target_dir,
            self._split(self.scaffolds),
            not self._split(self.packs),
        )
        return Continue(result, self.verify)

    def verify(self) -> Done:
        """Assert every precondition the main loop assumes, and fail if it does not hold."""
        found = self._target()
        report = self.call(
            validate_genesis, found.target_dir, self.service_root, found.markers
        )
        for warning in report.warnings.splitlines():
            self.logger.warning("%s", warning)
        if not report.valid:
            raise WorkflowFailed(f"genesis target is invalid: {report.errors}")
        return Done(report)


    def _target(self) -> TargetClassification:
        """The classification every state below reads."""
        return self.output(resolve_genesis_target)

    @staticmethod
    def _split(value: str) -> tuple[str, ...]:
        """A comma-separated operator input as the sequence the nodes take."""
        return tuple(part.strip() for part in value.split(",") if part.strip())


__all__ = ["Genesis"]
