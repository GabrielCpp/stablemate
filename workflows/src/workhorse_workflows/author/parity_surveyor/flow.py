"""The parity survey as a state machine — the port of `author/workflow.yaml`'s `flows.parity-surveyor` (13 nodes, lines 1389-1560)."""
from __future__ import annotations

from workhorse.pyflow import (
    Continue,
    Done,
    NodeNotRunError,
    Workflow,
    WorkflowFailed,
)
from workhorse_workflows.author.parity_surveyor.nodes import (
    emit_parity_backlog,
    expand_parity_inventory,
    load_parity_config,
)
from workhorse_workflows.author.shared.survey.records import validate_record, verify_records
from workhorse_workflows.author.shared.survey.units import mark_unit, select_next_unit
from workhorse_workflows.author.shared.schemas import ParityConfig, UnitAssessment


class ParitySurveyor(Workflow):
    """Legacy baseline vs the current OKF book, one surface at a time."""

    baseline_inventory: str = ""
    survey_dir: str = "docs/survey/legacy-vs-new"

    def setup(self) -> ParityConfig:
        """Resolve and validate both sides of the comparison."""
        return self.call(
            load_parity_config,
            self.baseline_inventory,
            self.survey_dir,
        )

    def labels(self) -> dict[str, str]:
        """Which unit the survey is on, and how far along — the YAML's `labels:` block."""
        try:
            pick = self.output(select_next_unit)
        except NodeNotRunError:
            return {}
        return {"work_id": pick.unit_id, "progress": pick.progress}


    def start(self) -> Continue:
        """Transcribe the baseline into a frozen unit list."""
        expansion = self.call(
            expand_parity_inventory, self.ctx.baseline_inventory, self.ctx.inventory
        )
        if not expansion.expand_ok:
            raise WorkflowFailed(
                f"could not freeze the parity inventory: {expansion.expand_errors}"
            )
        return Continue(expansion, self.pick)


    def pick(self) -> Continue:
        """Take the next pending unit, or fall through to the coverage gate."""
        pick = self.call(select_next_unit, self.ctx.inventory, self.ctx.findings_dir)
        if not pick.has_unit:
            return Continue(pick, self.verify)
        return Continue(
            pick,
            self.assess,
            unit_id=pick.unit_id,
            unit_path=pick.unit_path,
            unit_kind=pick.unit_kind,
            record_path=pick.record_path,
            progress=pick.progress,
        )

    def assess(
        self,
        unit_id: str,
        unit_path: str,
        unit_kind: str,
        record_path: str,
        progress: str = "",
    ) -> Continue:
        """Judge one legacy surface against the new app, and write its record."""
        where = f"assessing parity {unit_kind} {unit_id}"
        self.logger.info(
            "%s%s", where, f" · {progress}" if progress else "", extra={"activity": True}
        )
        result = self.agent(
            "parity_surveyor/prompts/assess-parity-unit.md",
            returns=UnitAssessment,
            power="medium",
            cwd=self.ctx.repo_root,
            args={
                "unit_id": unit_id,
                "unit_path": unit_path,
                "unit_kind": unit_kind,
                "record_path": record_path,
                "baseline_inventory": self.ctx.baseline_inventory,
                "target_features": self.ctx.target_features,
                "backlog": self.ctx.backlog,
                "epics_dir": self.ctx.epics_dir,
            },
        )
        return Continue(
            result, self.mark, unit_id=unit_id, record_path=record_path
        )

    def mark(self, unit_id: str, record_path: str) -> Continue:
        """Check the record the turn wrote, then take the unit off the pending list."""
        check = self.call(validate_record, record_path, unit_id)
        if not check.record_ok:
            raise WorkflowFailed(
                f"finding record for '{unit_id}' is invalid: {check.record_errors}"
            )
        marked = self.call(mark_unit, self.ctx.inventory, unit_id, record_path)
        return Continue(marked, self.pick)


    def verify(self) -> Continue:
        """The coverage gate: every frozen unit accounted for, and no silent shrinkage."""
        result = self.call(verify_records, self.ctx.inventory, self.ctx.findings_dir)
        if not result.holds or result.nothing_surveyed:
            raise WorkflowFailed(
                "parity coverage does not hold: "
                f"{result.verify_errors or result.verify_report}"
            )
        return Continue(result, self.emit)

    def emit(self) -> Done:
        """One backlog bullet per assessed surface no new-app feature already owns."""
        result = self.call(
            emit_parity_backlog,
            self.ctx.inventory,
            self.ctx.findings_dir,
            self.ctx.unit_manifest,
        )
        if not result.emit_ok:
            self.logger.warning("emission reported errors: %s", result.emit_errors)
        return Done(result)


__all__ = ["ParitySurveyor"]
