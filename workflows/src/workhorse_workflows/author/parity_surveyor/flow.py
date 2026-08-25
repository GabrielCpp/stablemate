"""The parity survey as a state machine — the port of `author/workflow.yaml`'s
`flows.parity-surveyor` (13 nodes, lines 1389-1560).

It asks one question of a rewrite — which legacy surfaces have no home in the new app —
and it is a *survey*, so it carries the exhaustiveness guarantee: one frozen unit per
baseline surface, one finding record each, and the empty pending set as the proof. The
shape is a per-unit loop between two ends:

    freeze the unit list → (pick → assess → mark)* → verify coverage → emit bullets

Thirteen nodes become six states, and every node that disappeared was a branch. All four
`type: branch` nodes — `parity_decide_expand`, `parity_decide_unit`,
`parity_decide_record`, `parity_decide_verify` — were reading a value the node *directly
above them* had just produced, which is `if` written across two nodes because a script
cannot route. `parity_validate_record` folds in with `parity_mark_unit` for the same
reason: validate-then-gate-then-mark is one step an operator resumes as a unit, and the
expensive thing that must not be re-run on resume is the agent turn, which is its own
state ahead of it.

`parity_failed`, a `type: fail` node reached from three branches, becomes three
`raise WorkflowFailed(...)` at the sites that decided to fail. That is the one place this
port says *more* than the YAML did: a shared fail terminal cannot name which gate tripped
it, so the YAML's run ends with "reached parity_failed" and the reason only in a log
line. Each raise here carries the errors the node reported.

Divergences from the YAML, all deliberate:

* the `*_ok` / `has_*` outputs were `"yes"`/`"no"` **strings**, because a YAML branch
  compares text. They are `bool` on the models; nothing on disk carried the strings.
* `parity_decide_verify` routes anything but `"yes"` to `parity_failed`, and
  `verify-records.py` emits `verify_ok: "skip"` when there is no inventory at all — so
  a nothing-surveyed run failed. `VerifyResult` splits that tri-state into `holds` and
  `nothing_surveyed`, and the gate is `holds and not nothing_surveyed` to keep it.
* `refuel: unit_id` on `parity_select_unit` has no counterpart: pyflow has no gas tank,
  and the transition budget is what bounds the machine. The loop costs three transitions
  per unit, so the 1,000 default covers ~330 units; a larger baseline raises
  `WORKHORSE_MAX_TRANSITIONS`. Left as the operator's knob rather than pinned as a
  `max_transitions` class value, because pinning it would take the env var away.
* `parity_emit_artifacts` routes to `parity_done` unconditionally — an emission that
  reports `emit_ok: "no"` still ends the flow clean. Kept, with a warning line so the
  failure is at least visible in the log.
* the agent node's `default: {status: "assessed"}` is dropped. Nothing routes on the
  assessment (the record on disk is what `validate_record` reads), and the model's `""`
  default says "the turn produced nothing" where `"assessed"` claimed the opposite.
* `verify-records.py` was passed `""` for `ref` and `mark-unit.py` `""` for its
  fallback; both nodes normalize an empty string to their default, so both are omitted.
* the pre-rendered reference (the internal author-workflow-python plan) deliberately leaves
  this flow out: *"The two sub-graphs under the YAML's `flows:` … are not gathered in.
  They are their own state machines; under this design each is its own `Workflow`
  subclass, reached with `self.handoff(...)`, and each would get this same treatment in
  its own module."* This module is that treatment. (Its node count for this flow, 8, is
  an undercount — the YAML has 13.)
"""
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
    """Legacy baseline vs the current OKF book, one surface at a time.

    Reuses the surveyor's frozen-inventory and one-unit-at-a-time mechanics over a
    different list, and emits one backlog bullet per uncovered baseline surface instead
    of clustering several into one synthetic finding — each missing surface is its own
    gap, so clustering would merge exactly what a parity backlog needs kept apart.
    """

    #: Repo-relative path to the baseline inventory being compared against. Required in
    #: practice: `load_parity_config` fails the flow when it names no readable file.
    #: `null` in the YAML's `vars`, `""` here, because an input is typed.
    baseline_inventory: str = ""
    #: The new app's feature book — the "does anything own this?" side of the compare.
    #: Blank means the book ostler configures for this repo.
    target_features: str = ""
    #: Where this survey's own artifacts live. The inventory, the findings dir and the
    #: unit manifest are all derived from it by `load_parity_config`.
    survey_dir: str = "docs/survey/legacy-vs-new"
    #: What emission appends to, inside its generated fence. Blank means ostler's backlog.
    backlog: str = ""
    #: Read by the assessor to recognize a surface an epic already covers. Blank means the
    #: epics root ostler configures.
    epics_dir: str = ""

    def setup(self) -> ParityConfig:
        """Resolve and validate both sides of the comparison.

        `parity_load_config`. It is `setup` rather than a state because every state
        below reads these paths and none of them decides one: a parity survey with no
        baseline has nothing to be exhaustive *about*, and one with no target feature
        book would report every legacy surface as missing.
        """
        return self.call(
            load_parity_config,
            self.baseline_inventory,
            self.target_features,
            self.survey_dir,
            self.backlog,
            self.epics_dir,
        )

    def labels(self) -> dict[str, str]:
        """Which unit the survey is on, and how far along — the YAML's `labels:` block.

        Both dimensions come off `select_next_unit`, exactly as the YAML read them with
        `get_node_output('parity_select_unit', …)`. Before the first pick there is no
        output to read, and that is the normal state of the run's first transition, not
        an error.
        """
        try:
            pick = self.output(select_next_unit)
        except NodeNotRunError:
            return {}
        return {"work_id": pick.unit_id, "progress": pick.progress}

    # --- the freeze ---------------------------------------------------------

    def start(self) -> Continue:
        """Transcribe the baseline into a frozen unit list.

        `parity_expand_inventory` + `parity_decide_expand`. Same freeze semantics as the
        surveyor's: an inventory already on disk is the coverage baseline and is consumed
        verbatim rather than re-derived, which is what makes a resumed survey mean the
        same thing as an uninterrupted one.
        """
        expansion = self.call(
            expand_parity_inventory, self.ctx.baseline_inventory, self.ctx.inventory
        )
        if not expansion.expand_ok:
            raise WorkflowFailed(
                f"could not freeze the parity inventory: {expansion.expand_errors}"
            )
        return Continue(expansion, self.pick)

    # --- the per-unit loop --------------------------------------------------

    def pick(self) -> Continue:
        """Take the next pending unit, or fall through to the coverage gate.

        `parity_select_unit` + `parity_decide_unit`. The empty select *is* the
        exhaustiveness proof, so "no unit" is the loop's success exit, not a problem —
        `has_unit` false and the YAML's `"no"` case both land on the same verify.
        """
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
        """Judge one legacy surface against the new app, and write its record.

        A state of its own, holding nothing but the turn: it is the expensive thing in
        the loop, and the checkpoint is written *before* a state runs, so validation and
        marking living downstream is what makes a resume cheap.

        `cwd` is the surveyed repo — it decides whose `CLAUDE.md`, skills and git context
        the turn sees, and it is the field the YAML node carried.
        """
        where = f"assessing parity {unit_kind} {unit_id}"
        # The YAML hung this on the node's `activity:` string, reaching back into
        # `parity_select_unit`'s output for the progress suffix. Here the pick already
        # handed it over, and the flagged record is what publishes it.
        self.logger.info(
            "%s%s", where, f" · {progress}" if progress else "", extra={"activity": True}
        )
        result = self.agent(
            "parity_surveyor/prompts/assess-parity-unit.md",
            returns=UnitAssessment,
            # medium: reads one surface, the target feature book and the epics, and
            # decides whether anything owns it — judgment over documents, not design.
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
        """Check the record the turn wrote, then take the unit off the pending list.

        `parity_validate_record` + `parity_decide_record` + `parity_mark_unit`. Unlike
        the surveyor flow there is no bounded fix loop here: an invalid record fails the
        survey outright, because the parity record *is* the finding and a malformed one
        would emit a bullet nobody can act on.
        """
        check = self.call(validate_record, record_path, unit_id)
        if not check.record_ok:
            raise WorkflowFailed(
                f"finding record for '{unit_id}' is invalid: {check.record_errors}"
            )
        marked = self.call(mark_unit, self.ctx.inventory, unit_id, record_path)
        return Continue(marked, self.pick)

    # --- the ends -----------------------------------------------------------

    def verify(self) -> Continue:
        """The coverage gate: every frozen unit accounted for, and no silent shrinkage.

        `parity_verify_records` + `parity_decide_verify`. `nothing_surveyed` fails here
        rather than passing, which is the YAML's behavior read literally: its branch
        routes everything but `"yes"` to `parity_failed`, and the script answers
        `"skip"` when there is no inventory to check. A survey that surveyed nothing has
        not proved anything.
        """
        result = self.call(verify_records, self.ctx.inventory, self.ctx.findings_dir)
        if not result.holds or result.nothing_surveyed:
            raise WorkflowFailed(
                "parity coverage does not hold: "
                f"{result.verify_errors or result.verify_report}"
            )
        return Continue(result, self.emit)

    def emit(self) -> Done:
        """One backlog bullet per assessed surface no new-app feature already owns.

        `parity_emit_artifacts` + `parity_done`. The manifest carries *every* unit,
        including the suppressed ones and the owner that suppressed them, so "we decided
        this one is already covered" stays an auditable claim rather than an absence.

        The result is what `handoff` hands back to `author`, which reads `bullet_count`
        off it.
        """
        result = self.call(
            emit_parity_backlog,
            self.ctx.inventory,
            self.ctx.findings_dir,
            self.ctx.backlog,
            self.ctx.unit_manifest,
        )
        if not result.emit_ok:
            # The YAML ends clean here too — `parity_emit_artifacts` has no branch after
            # it. Kept as-is; the warning is so a run that emitted nothing says so.
            self.logger.warning("emission reported errors: %s", result.emit_errors)
        return Done(result)


__all__ = ["ParitySurveyor"]
