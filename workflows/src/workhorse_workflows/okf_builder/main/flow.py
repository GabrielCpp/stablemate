"""The okf-builder workflow: a service's code becomes an exhaustive OKF book."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, ClassVar

from workhorse.pyflow import (
    AgentTimeout, AgentTurnFailed, Await, Continue, Done, NodeNotRunError, Workflow,
    WorkflowFailed,
)
from workhorse_workflows.kit import build_worklist, head_sha
from workhorse_workflows.okf_builder.live_audit.flow import LiveAudit, LiveAuditReport
from workhorse_workflows.okf_builder.main.nodes import (
    apply_verdict,
    blocked_rows,
    commit_book,
    commit_turn,
    compute_coverage,
    gather_evidence,
    inventory_source,
    prepare,
    snapshot_book,
    stamp_turn,
)
from workhorse_workflows.okf_builder.shared import paths
from workhorse_workflows.okf_builder.shared.checkpoint import checkpoint_book, settle_stale
from workhorse_workflows.okf_builder.shared.schemas import (
    Adjudication,
    Evidence,
    Investigation,
    Prepared,
    Recheck,
    Recorded,
    SourceRequest,
)
from workhorse_workflows.okf_builder.shared.vocabulary import (
    act_vocabulary, bullet_grammar, check_vocabulary)
from workhorse_workflows.okf_builder.shared.worklist import (
    MAX_TARGET_ATTEMPTS,
    record,
    select_item,
)

MAX_RESCAN_ROUNDS = 6

MAX_STALL_ROUNDS = 3

def _attempts(current_item: dict[str, Any]) -> int:
    try:
        return int(current_item.get("attempts", 0) or 0)
    except (TypeError, ValueError):
        return 0


def investigation_power(current_item: dict[str, Any]) -> str:
    """Escalate an investigation only after its first model attempt failed."""
    return "medium" if _attempts(current_item) > 0 else "low"


def _live_audit_gate_message(reports: list[LiveAuditReport]) -> str:
    """The live-audit gate body: every blocked obligation and failing scenario, by name."""
    lines = ["okf-builder's live audit found work the operator must clear before this book can commit."]
    for report in reports:
        if report.gaps:
            blocked_ids = sorted({str(gap.get("obligation_id", "")) for gap in report.gaps})
            lines.append(
                f"- {report.spec_dir}: {len(blocked_ids)} obligation(s) blocked "
                "(book not yet executable) — no compiled call exists yet for:"
            )
            for gap in report.gaps:
                lines.append(
                    f"  - {gap.get('obligation_id')} {gap.get('kind')}: {gap.get('detail')}"
                )
        if report.status == "blocked" and not report.gaps:
            lines.append(f"- {report.spec_dir}: blocked — {report.notes}")
            continue
        failing = [scenario for scenario in report.scenarios if scenario.status != "passed"]
        if failing:
            lines.append(f"- {report.spec_dir}: {len(failing)} scenario(s) failed")
            for scenario in failing:
                lines.append(
                    f"  - {scenario.id} {scenario.status} "
                    f"({scenario.failures}/{scenario.assertions} failed): {scenario.message}"
                )
    lines.append(
        "\nFix the book, the fixture, or the code under test, then answer to re-run the "
        "live audit — only claims whose fingerprint changed are re-executed."
    )
    return "\n".join(lines)


def repair_power(
    current_item: dict[str, Any], item_context: str, batch: list[dict[str, Any]] | None = None
) -> str:
    """Choose the repair turn's model tier from deterministic worklist context."""
    attempts = max(_attempts(row) for row in [current_item, *(batch or [])])
    if attempts >= 2:
        return "high"
    if attempts == 1:
        return "medium"
    try:
        context = json.loads(item_context or "{}")
    except ValueError:
        return "medium"
    if not isinstance(context, dict):
        return "medium"
    findings = context.get("findings")
    related = context.get("related")
    paths_in_scope = context.get("paths")
    if (
        context.get("grounded") is True
        or bool(batch)
        or (isinstance(related, list) and bool(related))
        or (isinstance(paths_in_scope, list) and len(paths_in_scope) > 1)
        or (isinstance(findings, list) and len(findings) >= 3)
    ):
        return "medium"
    return "low"


class OkfBuilder(Workflow):
    """Build (or repair) one service's OKF book from its source, exhaustively."""

    REFUEL_ON: ClassVar[frozenset[str]] = frozenset({"progress"})

    PROTECT_WORKTREE: ClassVar[bool] = True

    service: str = ""
    source_path: str = ""
    source_excludes: str = ""
    docs_path: str = ""
    max_items: int = 0

    since: str = ""
    recheck_only: bool = False
    diff_base: str = ""
    story: str = ""
    workspace_file: str = ""
    sources: tuple[SourceRequest, ...] = ()

    def setup(self) -> Prepared:
        """Resolve every path and adopt (or reset) the worklist."""
        return self.call(
            prepare,
            self.docs_path,
            self.service,
            self.source_path,
            self.source_excludes,
            recheck_only=self.recheck_only,
            diff_base=self.diff_base,
            story=self.story,
            workspace_file=self.workspace_file,
            sources=self.sources,
            worklist_dir=str(self.run_dir / "drain"),
        )

    def labels(self) -> dict[str, str]:
        """The dashboard's dimensions: which item, and how far through the drain."""
        labels = {"service": self.service}
        try:
            pick = self.output(select_item)
        except NodeNotRunError:
            return labels
        return {**labels, "work_id": pick.item_target, "progress": pick.progress}

    def state_labels(self, params: dict[str, Any]) -> dict[str, str]:
        """Per-state dimensions on top of `labels()`: the coverage re-scan counter."""
        labels = self.labels()
        if "rescan" in params:
            labels["rescan_round"] = str(params.get("rescan", 0))
        return labels


    def start(self) -> Continue:
        """`check_ostler` + `decide_start`: can this run measure anything, and from where."""
        if not self.ctx.ostler_ok:
            raise WorkflowFailed(
                self.ctx.prepare_error
                or "ostler could not load a graph at the docs root, so nothing this run "
                "claimed about coverage could be checked",
                failure_class="okf-builder-ostler-not-ok",
                artifacts={"features_root": str(self.ctx.features_root)},
            )
        if self.ctx.book_exists:
            self.logger.info("the book exists: reconciling it to HEAD from the checkpoint")
            return Continue(None, self.checkpoint).because("the book exists: reconcile it to HEAD")
        self.logger.info("no book yet: the join reports every unit as missing; recheck classifies")
        return Continue(None, self.checkpoint).because(
            "empty book: same join seeds the worklist"
        )


    def select(
        self,
        rnd: int = 0,
        rescan: int = 0,
        stall: int = 0,
        signature: str = "",
        refuels: int = 0,
    ) -> Continue | Await:
        """`select_item` + `guard_budget` + `decide_item`: take one item, or converge."""
        self.call(settle_stale, self.ctx.worklist_path, self.ctx.repo_root, self.ctx.features_root)
        pick = self.call(
            select_item,
            self.ctx.worklist_path,
            self.max_items * (refuels + 1) if self.max_items else 0,
            self.ctx.done_baseline,
        )
        if pick.over_budget:
            self.call(checkpoint_book, self.ctx.repo_root, self.ctx.features_root, rnd)
            return Await(
                paths.operator_context_path(
                    Path(self.ctx.repo_root), self.service, self.ctx.scope_id
                ),
                f"okf-builder stopped at its {self.max_items * (refuels + 1)}-item "
                f"ceiling with {pick.pending_count} item(s) still pending — the book "
                f"is partial, not converged. It was canonicalized (`ostler fmt`) so "
                f"what exists is well-formed. Flip this file's `STATUS:` line to "
                f"`ANSWERED` to resume the drain with a fresh allowance of "
                f"{self.max_items} item(s).",
                self.refuel,
                rnd=rnd,
                rescan=rescan,
                stall=stall,
                signature=signature,
                refuels=refuels,
            ).because("item ceiling hit with work pending: ask for more")
        if not pick.has_item:
            return Continue(
                pick,
                self.checkpoint,
                rnd=rnd,
                rescan=rescan,
                stall=stall,
                signature=signature,
                refuels=refuels,
            ).because("the drain is dry: run doctor")
        return Continue(
            pick,
            self.investigate,
            current_item=pick.current_item,
            batch=pick.batch,
            item_kind=pick.item_kind,
            item_code=pick.item_code,
            item_codes=pick.item_codes,
            item_target=pick.item_target,
            item_context=pick.item_context,
            progress=pick.progress,
            rnd=rnd,
            rescan=rescan,
            stall=stall,
            signature=signature,
            refuels=refuels,
        ).because("next item picked")

    def refuel(
        self,
        rnd: int = 0,
        rescan: int = 0,
        stall: int = 0,
        signature: str = "",
        refuels: int = 0,
    ) -> Continue:
        """Consume the operator's answer to an item-ceiling stop: one more allowance."""
        self.logger.info(
            "operator refuel #%d: granting %d more item(s)", refuels + 1, self.max_items
        )
        return Continue(
            None,
            self.select,
            rnd=rnd,
            rescan=rescan,
            stall=stall,
            signature=signature,
            refuels=refuels + 1,
        ).because("operator granted another allowance")

    def investigate(
        self,
        current_item: dict,
        item_kind: str,
        item_target: str,
        item_context: str,
        item_code: str = "",
        progress: str = "",
        rnd: int = 0,
        rescan: int = 0,
        stall: int = 0,
        signature: str = "",
        refuels: int = 0,
        batch: list[dict] | None = None,
        item_codes: list[str] | None = None,
    ) -> Continue:
        """The heart: document ONE item to the spec-complete bar, or repair one file's findings."""
        repair = item_kind.startswith("fix:")
        behavior_repair = item_kind == "behavior-repair"
        batch = batch or []
        item_codes = item_codes or ([item_code] if item_code else [])
        where = f"{'repairing' if repair else 'documenting'} {item_kind} {item_target}"
        if batch:
            where += f" (+{len(batch)} row(s) on its file and siblings)"
        self.logger.info(
            "%s%s", where, f" · {progress}" if progress else "", extra={"activity": True}
        )
        self.call(
            commit_turn, self.ctx.repo_root, self.ctx.features_root,
            f"docs({self.service}): record book edits before the next turn", self.story,
        )
        pre_turn_sha = head_sha(self.ctx.repo_root)
        baseline = (
            self.call(snapshot_book, self.ctx.features_root, str(self.run_dir / "turn-baseline")).path
            if repair or behavior_repair
            else ""
        )
        result = self.agent(
            "main/prompts/repair-behavior.md" if behavior_repair else
            "main/prompts/repair.md" if repair else "main/prompts/investigate.md",
            returns=Investigation,
            power=(
                "medium" if behavior_repair else repair_power(current_item, item_context, batch)
                if repair
                else investigation_power(current_item)
            ),
            cwd=self.ctx.repo_root,
            add_dirs=[self.ctx.repo_root],
            args={
                "item_kind": item_kind,
                "item_code": item_code,
                "item_codes": item_codes,
                "item_target": item_target,
                "item_context": item_context,
                "result_schema": json.dumps(Investigation.model_json_schema(), indent=2),
                "check_vocabulary": check_vocabulary(),
                "act_vocabulary": act_vocabulary(),
                "bullet_grammar": bullet_grammar(),
                "source_inventory_path": str(
                    paths.source_inventory_path(self.ctx.worklist_path)
                ),
                "service": self.service,
                "features_root": self.ctx.features_root,
                "baseline": baseline,
                "repo_root": self.ctx.repo_root,
                "source_root": self.ctx.source_root,
                "source_excludes": self.ctx.source_excludes,
            },
        )
        self.call(
            stamp_turn, self.ctx.repo_root, self.ctx.features_root, pre_turn_sha,
            item_kind, item_context, result.doc_status,
        )
        self.call(
            commit_turn, self.ctx.repo_root, self.ctx.features_root,
            result.commit_message or f"docs({self.service}): {where}", self.story,
        )
        return Continue(
            result,
            self.record_item,
            current_item=current_item,
            batch=batch,
            discovered=result.discovered,
            item_kind=item_kind,
            item_context=item_context,
            doc_status=result.doc_status,
            note=result.note,
            rnd=rnd,
            rescan=rescan,
            stall=stall,
            signature=signature,
            refuels=refuels,
        ).because("turn finished: record what it wrote")

    def record_item(
        self,
        current_item: dict,
        discovered: list[dict],
        item_kind: str = "",
        item_context: str = "",
        doc_status: str = "",
        note: str = "",
        rnd: int = 0,
        rescan: int = 0,
        stall: int = 0,
        signature: str = "",
        refuels: int = 0,
        batch: list[dict] | None = None,
    ) -> Continue:
        """`record`: close the item the turn documented, open what it revealed."""
        return Continue(
            self.call(
                record,
                self.ctx.worklist_path,
                current_item,
                discovered,
                doc_status=doc_status,
                note=note,
                repo_root=str(self.ctx.repo_root),
                features_root=str(self.ctx.features_root),
                batch=batch or [],
            ),
            self.select,
            rnd=rnd,
            rescan=rescan,
            stall=stall,
            signature=signature,
            refuels=refuels,
        ).because("item closed, discoveries opened")


    def checkpoint(
        self,
        rnd: int = 0,
        rescan: int = 0,
        stall: int = 0,
        signature: str = "",
        refuels: int = 0,
    ) -> Continue | Await:
        """`checkpoint` + `decide_checkpoint` + `guard_fixup_progress` + `seed_fixup` + `guard_rounds`: canonicalize, read doctor, and decide what the dirt means."""
        result = self.call(
            checkpoint_book,
            self.ctx.repo_root,
            self.ctx.features_root,
            rnd,
            signature,
            stall,
        )
        if not result.checkpoint_clean:
            recorded = self.call(
                record, self.ctx.worklist_path, None, result.fixup_items, settle_fix_items=True,
                repo_root=str(self.ctx.repo_root),
            )
            if recorded.blocked_count and not recorded.pending_count:
                return Continue(
                    recorded,
                    self.adjudicate,
                    rnd=result.round,
                    rescan=rescan,
                    signature=result.fixup_signature,
                    refuels=refuels,
                ).because("blocked rows and nothing pending: read the other side")
            if result.stall_rounds >= MAX_STALL_ROUNDS:
                return Await(
                    paths.operator_context_path(Path(self.ctx.repo_root), self.service),
                    self._stalled_gate_question(result.stall_rounds, recorded),
                    self.retry_blocked,
                    rnd=result.round,
                    rescan=rescan,
                    signature=result.fixup_signature,
                    refuels=refuels,
                ).because("findings unchanged for the stall cap: operator gate")
            return Continue(
                recorded,
                self.select,
                rnd=result.round,
                rescan=rescan,
                stall=result.stall_rounds,
                signature=result.fixup_signature,
                refuels=refuels,
            ).because("doctor dirty: repairs queued")
        if rescan >= MAX_RESCAN_ROUNDS:
            return Await(
                paths.operator_context_path(Path(self.ctx.repo_root), self.service),
                f"okf-builder's coverage re-scan did not converge in "
                f"{MAX_RESCAN_ROUNDS} rounds — doctor is clean, but the coverage state "
                f"kept coming back incomplete. Which half is incomplete is not something "
                f"this gate can see, and the two want opposite work, so read it before "
                f"answering: `covered`/`total` in the book's `coverage.json` says whether "
                f"units are genuinely uncited (a book gap — author them, or waive them in "
                f"`coverage-waivers.json` with a reason), while `missing_count` and "
                f"`regrounding` on the run's latest `compute_coverage/output.json` "
                f"separate that from cited symbols that were rewritten underneath their "
                f"nodes (a re-grounding gap — re-read those bullets against the source). "
                f"100% coverage with the scan still refusing to complete is the second "
                f"one. Then flip this file's `STATUS:` line to `ANSWERED` to resume the "
                f"re-scan with a fresh {MAX_RESCAN_ROUNDS}-round allowance.",
                self.retry_blocked,
                rnd=result.round,
                rescan=0,
                refuels=refuels,
            ).because("re-scan cap hit, coverage still incomplete: operator gate")
        return Continue(
            result, self.rescan_coverage, rnd=result.round, rescan=rescan, refuels=refuels
        ).because("doctor clean: check the inventory")

    def adjudicate(
        self,
        rnd: int = 0,
        rescan: int = 0,
        signature: str = "",
        refuels: int = 0,
    ) -> Continue | Await:
        """Give each blocked finding a side, one agent turn per row, then route."""
        pending = self.call(blocked_rows, self.ctx.worklist_path)
        if pending.rows:
            row = pending.rows[0]
            evidence = self.call(
                gather_evidence, self.ctx.repo_root, self.ctx.source_root, json.dumps(row)
            )
            story = evidence.story or {}
            try:
                result = self._adjudication(evidence, story)
                self.call(
                    apply_verdict,
                    self.ctx.repo_root,
                    self.ctx.worklist_path,
                    json.dumps(row),
                    result.verdict,
                    result.chain,
                    result.seed_summary,
                    str(story.get("slug") or ""),
                    str(story.get("epic") or ""),
                )
            except (
                ValueError, RuntimeError, WorkflowFailed, AgentTimeout, AgentTurnFailed,
            ) as exc:
                return Await(
                    paths.operator_context_path(Path(self.ctx.repo_root), self.service),
                    f"okf-builder could not adjudicate {row.get('target', '?')!r}: {exc}\n\n"
                    f"The row is still blocked and keeps its attempts. Answering re-reads "
                    f"this same row, so fix what made the turn unusable before answering — "
                    f"an answer alone re-asks the turn that already failed.",
                    self.adjudicate,
                    rnd=rnd,
                    rescan=rescan,
                    signature=signature,
                    refuels=refuels,
                ).because("adjudication turn unusable: operator gate")
            return Continue(
                result,
                self.adjudicate,
                rnd=rnd,
                rescan=rescan,
                signature=signature,
                refuels=refuels,
            ).because("verdict applied: next blocked row")
        self.call(
            settle_stale, self.ctx.worklist_path, self.ctx.repo_root, self.ctx.features_root, 0
        )
        recorded = self.call(record, self.ctx.worklist_path)
        if recorded.pending_count:
            return Continue(
                recorded,
                self.select,
                rnd=rnd,
                rescan=rescan,
                stall=0,
                signature=signature,
                refuels=refuels,
            ).because("a book verdict re-queued rows")
        if recorded.blocked_count:
            return Await(
                paths.operator_context_path(Path(self.ctx.repo_root), self.service),
                self._blocked_gate_question(recorded),
                self.retry_blocked,
                rnd=rnd,
                rescan=rescan,
                signature=signature,
                refuels=refuels,
            ).because("rows still blocked after verdicts: operator gate")
        return Continue(
            recorded, self.checkpoint, rnd=rnd, rescan=rescan, signature=signature,
            refuels=refuels,
        ).because("every row closed: re-read doctor")

    def _adjudication(self, evidence: Evidence, story: dict[str, Any]) -> Adjudication:
        """The adjudication turn itself, lifted out so its state reads as one branch."""
        return self.agent(
            "main/prompts/adjudicate.md",
            returns=Adjudication,
            power="medium",
            cwd=self.ctx.repo_root,
            add_dirs=[self.ctx.repo_root, self.ctx.source_root],
            args={
                "item_target": evidence.target,
                "item_kind": evidence.kind,
                "item_code": evidence.code,
                "item_findings": json.dumps(evidence.findings, indent=2),
                "nodes": json.dumps(evidence.nodes),
                "code_refs": json.dumps(evidence.code_refs),
                "story": json.dumps(story) if story else "",
                "story_text": evidence.story_text,
                "story_resolved": "true" if evidence.story_resolved else "false",
                "warnings": json.dumps(evidence.warnings),
                "blocked_reason": evidence.blocked_reason,
                "result_schema": json.dumps(
                    Adjudication.model_json_schema(), indent=2, ensure_ascii=False
                ),
                "service": self.service,
                "features_root": self.ctx.features_root,
                "repo_root": self.ctx.repo_root,
                "source_root": self.ctx.source_root,
            },
        )

    @staticmethod
    def _blocked_gate_question(recorded: Recorded) -> str:
        """Name every target that spent its attempts, so the gate is actionable."""
        lines = "\n".join(
            f"  - {b.get('target', '?')} ({b.get('kind', '?')}) — "
            f"{b.get('attempts', 0)} attempt(s); last turn said: "
            f"{b.get('reason') or 'nothing'}"
            + (
                f"\n    adjudicated `{b['verdict']}`"
                + (f", seed {b['seed']}" if b.get("seed") else "")
                + f" — {' '.join(str(b.get('chain') or '').split()) or 'no chain given'}"
                if b.get("verdict")
                else ""
            )
            for b in recorded.blocked
        )
        return (
            f"okf-builder cannot clear {recorded.blocked_count} doctor finding(s) from the "
            f"book. Each was handed to a repair turn {MAX_TARGET_ATTEMPTS} times and came "
            f"back standing, an adjudication turn read the story and the source to name "
            f"the side at fault, and there is no other work left on the worklist:\n\n"
            f"{lines}\n\n"
            f"These are not excused — doctor still reports them. A `story` verdict means "
            f"the intent itself is in conflict, which is yours to rewrite: edit the story "
            f"(or the book, or the detector, when the adjudication is wrong). A `code` "
            f"verdict on a node that carries no `known-defect:` bullet stands until its "
            f"seed lands. Then set this file's `STATUS:` line to `ANSWERED` to return "
            f"those targets to the drain with a fresh {MAX_TARGET_ATTEMPTS}-attempt "
            f"allowance and a fresh adjudication."
        )

    @staticmethod
    def _regrounding_gate_question(recorded: Recorded) -> str:
        """Every changed file whose citing nodes spent their re-grounding attempts."""
        lines = "\n".join(
            f"  - {b.get('target', '?')} — {b.get('attempts', 0)} attempt(s); last turn said: "
            f"{b.get('reason') or 'nothing'}"
            for b in recorded.blocked
        )
        return (
            f"okf-builder cannot re-ground {recorded.blocked_count} file(s) whose cited "
            f"source changed under the nodes citing them. Each was handed to a repair turn "
            f"{MAX_TARGET_ATTEMPTS} times and the coverage join still reports the drift, "
            f"and there is no other work left on the worklist:\n\n{lines}\n\n"
            f"Re-read each bullet against the symbol it cites (or fix what makes the turn "
            f"report it undone), then set this file's `STATUS:` line to `ANSWERED` to "
            f"return those nodes to the drain with a fresh {MAX_TARGET_ATTEMPTS}-attempt "
            f"allowance."
        )

    @staticmethod
    def _stalled_gate_question(stall_rounds: int, recorded: Recorded) -> str:
        """The whole-book backstop: the finding set stopped moving while rows are pending."""
        return (
            f"okf-builder's doctor finding set has not changed in {stall_rounds} rounds — "
            f"the repair turns are running and nothing they write moves doctor, with "
            f"{recorded.pending_count} row(s) still pending on the worklist. This is not "
            f"convergence. Read the worklist beside this file under .agents/okf-build/ to "
            f"see what keeps coming back, then either repair it by hand, decide the "
            f"finding is wrong and fix the detector, or, when the code is the side at "
            f"fault, file a seed and a `known-defect:` bullet naming it on the node. Then "
            f"set this file's `STATUS:` line to `ANSWERED` to resume the drain with the "
            f"stall count reset."
        )

    def retry_blocked(
        self,
        rnd: int = 0,
        rescan: int = 0,
        signature: str = "",
        refuels: int = 0,
    ) -> Continue:
        """The operator answered: return the blocked targets to the drain."""
        self.call(
            settle_stale, self.ctx.worklist_path, self.ctx.repo_root, self.ctx.features_root, 0
        )
        return Continue(
            self.call(record, self.ctx.worklist_path, unblock=True),
            self.select,
            rnd=rnd,
            rescan=rescan,
            stall=0,
            signature=signature,
            refuels=refuels,
        ).because("operator answered: blocked targets unblocked")


    def rescan_coverage(
        self, rnd: int = 0, rescan: int = 0, refuels: int = 0
    ) -> Continue | Await:
        """`inventory_source` + `compute_coverage` + `decide_coverage`, with the worklist builder seeding deterministic rows alongside."""
        inventory = self.call(
            inventory_source,
            self.ctx.source_root,
            str(paths.source_inventory_path(self.ctx.worklist_path)),
            self.ctx.source_excludes,
            self.ctx.repo_root,
        )
        coverage = self.call(
            compute_coverage,
            self.ctx.repo_root,
            self.ctx.features_root,
            self.service,
            inventory.source_inventory_path,
            str(paths.waivers_path(self.ctx.features_root)),
            rescan,
        )
        builder_rows: tuple = ()
        if rescan == 0 and not coverage.coverage_complete:
            try:
                builder_rows = build_worklist(
                    Path(self.ctx.repo_root),
                    Path(self.ctx.features_root),
                    self.service,
                ).rows
            except (OSError, ValueError, RuntimeError) as exc:
                self.logger.warning("worklist builder failed: %s", exc)
                builder_rows = ()
            if builder_rows:
                self.logger.info(
                    "%d deterministic row(s) from the builder", len(builder_rows),
                    extra={"activity": True},
                )
            self.call(record, self.ctx.worklist_path, None, list(builder_rows))
        if coverage.coverage_complete:
            return Continue(coverage, self.semantic_audit).because("inventory cited: audit behavior in both directions")
        if coverage.regrounding:
            self.logger.info(
                "%d node(s) cite source that moved or changed under them; requeueing",
                len(coverage.regrounding),
                extra={"activity": True},
            )
            recorded = self.call(record, self.ctx.worklist_path, None, coverage.regrounding)
            if recorded.pending_count:
                return Continue(
                    recorded,
                    self.select,
                    rnd=rnd,
                    rescan=coverage.rescan_round,
                    refuels=refuels,
                ).because("cited source moved: re-ground those nodes")
            if coverage.missing_count:
                return Continue(
                    coverage, self.recheck, rnd=rnd, rescan=coverage.rescan_round, refuels=refuels
                ).because("re-grounding rows all blocked: adjudicate the uncovered units")
            return Await(
                paths.operator_context_path(Path(self.ctx.repo_root), self.service),
                self._regrounding_gate_question(recorded),
                self.retry_blocked,
                rnd=rnd,
                rescan=coverage.rescan_round,
                refuels=refuels,
            ).because("re-grounding rows all blocked and nothing uncovered: operator gate")
        return Continue(
            coverage, self.recheck, rnd=rnd, rescan=coverage.rescan_round, refuels=refuels
        ).because("uncovered units: ask whether they are units")

    def recheck(self, rnd: int = 0, rescan: int = 0, refuels: int = 0) -> Continue:
        """Adjudicate the computed missing list — the only coverage judgement left to an agent."""
        inventory = self.output(inventory_source)
        coverage = self.output(compute_coverage)
        self.logger.info(
            "adjudicating %d uncovered unit(s), re-scan %d",
            coverage.missing_count,
            rescan,
            extra={"activity": True},
        )
        result = self.agent(
            "main/prompts/recheck-coverage.md",
            returns=Recheck,
            power="medium",
            cwd=self.ctx.repo_root,
            add_dirs=[self.ctx.repo_root],
            args={
                "service": self.service,
                "features_root": self.ctx.features_root,
                "repo_root": self.ctx.repo_root,
                "source_root": self.ctx.source_root,
                "source_excludes": self.ctx.source_excludes,
                "source_inventory_path": inventory.source_inventory_path,
                "inventory_errors": inventory.inventory_errors,
                "missing_path": coverage.missing_path,
                "missing_count": coverage.missing_count,
                "coverage_summary": coverage.coverage_summary,
                "coverage_error": coverage.coverage_error,
                "waivers_path": str(paths.waivers_path(self.ctx.features_root)),
            },
        )
        return Continue(
            result,
            self.seed_recheck,
            discovered=result.discovered,
            rnd=rnd,
            rescan=rescan,
            refuels=refuels,
        ).because("recheck verdicts in")

    def seed_recheck(
        self, discovered: list[dict], rnd: int = 0, rescan: int = 0, refuels: int = 0
    ) -> Continue:
        """`seed_recheck`: queue what the adjudication ruled to be real work."""
        return Continue(
            self.call(record, self.ctx.worklist_path, None, discovered),
            self.select,
            rnd=rnd,
            rescan=rescan,
            refuels=refuels,
        ).because("real gaps queued")

    def semantic_audit(self) -> Continue | Await:
        """Run the book's QA plans for real against a live stack, then gate on the result."""
        result = self.handoff(LiveAudit, docs_path=self.ctx.repo_root, repo_dir=self.ctx.repo_root)
        reports = [LiveAuditReport.model_validate(r) for r in result["reports"]]
        blocked_or_failing = any(
            report.status == "blocked"
            or bool(report.gaps)
            or any(s.status != "passed" for s in report.scenarios)
            for report in reports
        )
        if blocked_or_failing:
            return Await(
                paths.operator_context_path(Path(self.ctx.repo_root), self.service, self.ctx.scope_id),
                _live_audit_gate_message(reports),
                self.semantic_audit,
            ).because("live audit blocked or failing: operator gate")
        return Continue(reports, self.commit, reports).because("live audit clear: commit the book")

    def commit(self, reports: list[LiveAuditReport]) -> Done:
        """Record the completed book without touching work outside its directory."""
        self.call(commit_book, self.ctx.repo_root, self.ctx.features_root, self.story)
        return Done({"reports": [r.model_dump() for r in reports]}).because("completed book committed")


__all__ = ["MAX_RESCAN_ROUNDS", "MAX_STALL_ROUNDS", "OkfBuilder"]
