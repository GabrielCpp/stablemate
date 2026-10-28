"""One dev owner plans, builds and reviews a story in three phases on one conversation, and the run checks it."""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any, ClassVar, TypeVar

from pydantic import BaseModel
from workhorse import worklist as wl
from workhorse.pyflow import Await, Continue, Done, Workflow

from workhorse_workflows.coder.dev.report import (
    findings_text,
    plan_arg,
    rejected_text,
    report_text,
    self_check_text,
    unadvised_text,
    unconsulted_text,
    walk_text,
)
from workhorse_workflows.coder.shared import causes, paths, roles, work
from workhorse_workflows.coder.shared.backlog import file_follow_up_backlog
from workhorse_workflows.coder.shared.branches import branch_code_repos
from workhorse_workflows.coder.shared.conversation import (
    brief_dir,
    brief_ledger,
    needs_brief,
    opening_phase,
    record_brief,
    reset_briefs,
    story_chain,
)
from workhorse_workflows.coder.shared.clones import check_copies
from workhorse_workflows.coder.shared.counsel import consulted, record_consults
from workhorse_workflows.coder.shared.dev import check_story_status, read_operator_context
from workhorse_workflows.coder.shared.escalation import context_path, escalation
from workhorse_workflows.coder.shared.judge import Judge
from workhorse_workflows.coder.shared.failed import (
    failed_scenario_ids,
    failed_scenarios_arg,
    last_failed_scenarios,
)
from workhorse_workflows.coder.shared.failure import from_findings, from_gate
from workhorse_workflows.coder.shared.owner import (
    HUMAN_MODES,
    MAX_BLOCKS,
    MAX_LAPS,
    SILENCE_S,
    UNBOUNDED,
    owner_profile,
)
from workhorse_workflows.coder.shared.plan import record_plan, resolve_impl_context
from workhorse_workflows.coder.shared.resolution import (
    RESOLVER_POWER,
    answered,
    decisions_dir,
    resolver_args,
)
from workhorse_workflows.coder.shared.reach import resolve_check_set
from workhorse_workflows.coder.shared.review import (
    ANSWERS_FILE,
    resolve_review_context,
    settle_findings,
)
from workhorse_workflows.coder.shared.schemas._base import Finding
from workhorse_workflows.coder.shared.schemas.dev import (
    FailureReport,
    GateOutcome,
    OperatorResolution,
)
from workhorse_workflows.coder.shared.schemas.dev_story import (
    BuildResult,
    DevOutcome,
    DevResult,
    FollowUp,
    PlanResult,
)
from workhorse_workflows.coder.shared.schemas.story import StoryPaths
from workhorse_workflows.coder.shared.service_gates import GATE_ORDER, declared_services, run_gate
from workhorse_workflows.coder.shared.stack import (
    ensure_stack,
    release_copy,
    run_qa_plan,
    stack_target,
)
from workhorse_workflows.coder.shared.story import (
    guard_story_file,
    prepare_story,
    resolve_workspace_dirs,
    stamp_specs,
    workspace_dirs,
)
from workhorse_workflows.coder.shared.story_commit import (
    check_repos_clean,
    commit_plan_record,
    leftover_text,
)
from workhorse_workflows.coder.shared.walk import acceptance_walk
from workhorse_workflows.kit.qa.runner import copy_lease
from workhorse_workflows.kit.telemetry import counter_labels


T = TypeVar("T", bound=BaseModel)
REVIEW_REFERENCES = {
    "reviewer_brief": "dev/prompts/dev-reviewer.md",
    "answer_format": "dev/prompts/dev-answer-file.md",
}


def _reports(entries: list[FollowUp]) -> dict[str, str]:
    """Each follow-up entry by its index, as its title and the reason it gave."""
    return {
        str(i): f"{e.title}: {e.reason}" if e.reason else e.title
        for i, e in enumerate(entries)
    }


class Dev(Workflow):
    """Dev one work item through its plan, build and review phases on one conversation, then check its plan, gates and answers."""

    story: str = ""
    epic: str = ""
    operator_mode: str = "auto"
    target_env: str = "local"
    branch: str = ""
    work_id: str = ""
    follow_up_title: str = ""
    follow_up_reason: str = ""
    note: str = ""
    preexisting: tuple[str, ...] = ()
    worklist_dir: str = ""

    injects: ClassVar[tuple[str, ...]] = paths.AMBIENT

    INFRA_NODES: ClassVar[frozenset[Any]] = frozenset({ensure_stack, release_copy})

    BUDGET_LABELS: ClassVar[tuple[str, ...]] = ("laps", "blocks", "number")

    def setup(self) -> StoryPaths:
        """Resolve the slug to paths and the workspace to directories."""
        self.call(resolve_workspace_dirs)
        story = self.call(prepare_story, self.story, self.epic)
        self.call(guard_story_file, story)
        return story

    def labels(self) -> dict[str, str]:
        """Which work item this run is on: what the run's activity line shows."""
        current = self._work_id
        return {"work_id": current} if current else {}

    def state_labels(self, params: dict[str, Any]) -> dict[str, str]:
        """The same, plus which attempt of which budget the next state is on."""
        return self.labels() | counter_labels(params, "dev", self.BUDGET_LABELS)

    @property
    def _work_id(self) -> str:
        return self.work_id or self.ctx.story_slug

    @property
    def _state_dir(self) -> Path:
        return Path(self.worklist_dir) if self.worklist_dir else self.run_dir

    @property
    def _worklist(self) -> wl.WorkList:
        return work.worklist(self._state_dir)

    def _next_round(self) -> int:
        return work.next_round(self._worklist, self._work_id, "review")

    def _rebrief(self) -> str:
        return work.resume_note(
            self._state_dir, self._work_id, self.ctx.story_path, self.ctx.spec_dir
        )

    def _story_args(self) -> dict[str, Any]:
        return {
            "story_slug": self.ctx.story_slug,
            "story_id": self.ctx.story_id,
            "epic": self.epic,
            "story_path": self.ctx.story_path,
            "story_services": self.ctx.story_services,
            "spec_dir": self.ctx.spec_dir,
            "branch": self.branch,
            "decisions_dir": str(decisions_dir(self.repo_dir)),
        }

    def start(self) -> Continue:
        """Open the plan phase, or the review phase when QA has already filed findings against the work item."""
        reset_briefs(self._state_dir, self._work_id)
        if self._sent_back(self._worklist):
            return Continue(None, self.review, note=self.note, number=self._next_round())
        return Continue(None, self.plan, note=self.note)

    def _power(self, phase: str) -> str:
        """The plan runs on the strongest tier; build and review run cheaper only when an advisor can answer their design calls."""
        if phase == "plan" or not self.has_delegate("advisor"):
            return "max"
        return "high"

    def _turn(
        self,
        phase: str,
        returns: type[T],
        said: dict[str, Any],
        references: dict[str, str] | None = None,
    ) -> T:
        turn = (
            roles.turn(self, "dev-plan", returns=PlanResult)
            if phase == "plan"
            else roles.turn(self, "dev-build", returns=BuildResult)
            if phase == "build"
            else roles.turn(self, "dev-review", returns=DevResult)
        )
        chain = story_chain(self.ctx.story_slug)
        session = self.chain_session(chain)
        ledger = brief_ledger(self._state_dir, self._work_id)
        folder = brief_dir(self._state_dir, self._work_id)
        brief = folder / f"{phase}.md"
        opener = opening_phase(ledger, session)
        refs = {name: folder / Path(template).name for name, template in (references or {}).items()}
        args = (
            turn.args
            | self._story_args()
            | {
                "brief_path": str(brief),
                "resume_note": self._rebrief(),
                "worklist_path": str(work.worklist_path(self._state_dir)),
                "follow_up_title": self.follow_up_title,
                "follow_up_reason": self.follow_up_reason,
                "advisor": self.has_delegate("advisor"),
                "services": self.call(declared_services).text,
                "opening_brief": str(folder / f"{opener}.md") if opener else "",
            }
            | {name: str(path) for name, path in refs.items()}
            | said
        )

        def rebrief() -> str:
            text = self.render_prompt(
                turn.prompt, args | {"resume_note": self._rebrief(), "opening_brief": ""}
            )
            brief.write_text(text, encoding="utf-8")
            return text

        if needs_brief(ledger, phase, session):
            folder.mkdir(parents=True, exist_ok=True)
            for name, template in (references or {}).items():
                refs[name].write_text(self.render_prompt(template, args), encoding="utf-8")
            brief.write_text(self.render_prompt(turn.prompt, args), encoding="utf-8")
            result = self.agent(
                turn.prompt,
                returns=returns,
                power=self._power(phase),
                timeout=UNBOUNDED,
                silence=SILENCE_S,
                profile=owner_profile("dev"),
                session=chain,
                rebrief=rebrief,
                add_dirs=workspace_dirs(self),
                args=args,
            )
        else:
            result = self.agent(
                "dev/prompts/dev-follow-up.md",
                returns=returns,
                power=self._power(phase),
                timeout=UNBOUNDED,
                silence=SILENCE_S,
                profile=owner_profile("dev"),
                session=chain,
                rebrief=rebrief,
                add_dirs=workspace_dirs(self),
                args={
                    **self._story_args(),
                    "phase": phase,
                    "brief_path": str(brief),
                    "report": said.get("report", ""),
                    "findings": said.get("findings", ""),
                    "qa_findings": said.get("qa_findings", ""),
                    "operator_context": said.get("operator_context", ""),
                    "note": said.get("note", ""),
                    "review_prefix": said.get("review_prefix", ""),
                },
            )
        record_brief(self._state_dir, self._work_id, phase, self.chain_session(chain))
        return result

    def plan(
        self, note: str = "", operator_context: str = "", blocks: int = 0
    ) -> Continue | Await:
        """Run the plan turn on the strongest tier: the plan files, before any product code."""
        self.logger.info("planning %s", self._work_id, extra={"activity": True})
        said = {"note": note, "operator_context": operator_context}
        result = self._turn("plan", PlanResult, said)
        if result.status == "blocked":
            return self._block(result, result.notes, "the plan turn", blocks, phase="plan")
        return Continue(result, self.build, blocks=blocks)

    def build(
        self,
        note: str = "",
        operator_context: str = "",
        report: str = "",
        laps: int = 0,
        blocks: int = 0,
    ) -> Continue | Await:
        """Run the build turn on the plan's conversation, and hold every departure to the advisor's word."""
        self.logger.info("building %s", self._work_id, extra={"activity": True})
        said = {"note": note, "operator_context": operator_context, "report": report}
        result = self._turn("build", BuildResult, said)
        self._file_follow_ups(result.follow_ups)
        if result.status == "blocked":
            return self._block(result, result.notes, "the build turn", blocks, phase="build")
        if self.has_delegate("advisor"):
            unadvised = [d for d in result.departures if not d.advice.strip()]
            if unadvised:
                text = unadvised_text(unadvised)
                if laps >= MAX_LAPS:
                    return self._block(result, text, "the build turn", blocks, phase="build")
                return Continue(
                    result, self.build, report=text, laps=laps + 1, blocks=blocks
                )
        return Continue(result, self.review, blocks=blocks, number=self._next_round())

    def review(
        self,
        note: str = "",
        operator_context: str = "",
        report: str = "",
        laps: int = 0,
        blocks: int = 0,
        number: int = 1,
        rechecked: bool = False,
    ) -> Continue | Await:
        """Run the review turn: review, triage, fix and answer, and every repair lap the checks send back."""
        self.logger.info("reviewing %s", self._work_id, extra={"activity": True})
        w = self._worklist
        open_items = work.open_findings(w, self._work_id)
        qa = [it for it in open_items if it.payload.get("source") == "qa"]
        rest = [it for it in open_items if it.payload.get("source") != "qa"]
        said = {
            "note": note,
            "operator_context": operator_context,
            "report": report,
            "answers_file": str(Path(self.ctx.spec_dir) / ANSWERS_FILE),
            "review_prefix": f"{self._work_id}/review-{number}.",
            "findings": findings_text(rest),
            "qa_findings": findings_text(qa),
        }
        result = self._turn("review", DevResult, said, REVIEW_REFERENCES)
        self.call(stamp_specs, self.ctx.story_id)
        self._file_follow_ups(result.follow_ups)
        found = [f.model_dump() for f in result.findings]
        filed = causes.file_findings(
            self._judge(), w, self._work_id, "review", number, found, by="review"
        )
        if filed:
            self.logger.info("the review filed %d finding(s) against %s", len(filed), self._work_id)
        record_consults(self._state_dir, self._work_id, result.consults)
        if result.status == "blocked":
            return self._block(result, result.notes, "the review turn", blocks, phase="review")
        return Continue(
            result,
            self.check,
            plan=plan_arg(result),
            laps=laps,
            blocks=blocks,
            rechecked=rechecked,
        )

    def _sent_back(self, w: wl.WorkList) -> bool:
        """Whether QA has filed a finding against this work item, so the turn is a rework."""
        return any(it.payload.get("source") == "qa" for it in work.findings_of(w, self._work_id))

    def _file_follow_ups(self, follow_ups: list[FollowUp]) -> None:
        entries = self._product_work(list(follow_ups))
        if not entries:
            return
        self.call(file_follow_up_backlog, parent=self._work_id, follow_ups=entries)

    def _product_work(self, entries: list[FollowUp]) -> list[FollowUp]:
        """The entries the judge reads as product work; each other one is logged for the operator with what it is instead."""
        reports = _reports(entries)
        outside = causes.not_product(self._judge("low"), reports)
        for rid, kind in outside.items():
            self.logger.info("[%s] %r is no product work, so it is not filed", kind, reports[rid])
        return [entry for i, entry in enumerate(entries) if str(i) not in outside]

    def _judge(self, power: str = "medium") -> Judge:
        """The one judge this flow asks: the word rule first, then one reading of what it left."""
        return causes.cause_judge(self, power)

    def check(
        self,
        plan: dict[str, Any] | None = None,
        laps: int = 0,
        blocks: int = 0,
        rechecked: bool = False,
    ) -> Continue | Await:
        """Check the plan, the gates and every answer, and send what failed back to the dev owner."""
        recorded = self.call(record_plan, plan, self.ctx.spec_dir)
        if recorded.status == "invalid":
            failures = [f"The plan's service paths did not validate: {recorded.errors}"]
        else:
            self.call(
                commit_plan_record,
                self.epic,
                self.ctx.story_slug,
                self.ctx.spec_dir,
                story_id=self.ctx.story_id,
            )
            failures = self._gate_failures(laps) + self._settle() + self._leftovers()
            failures += self._walk_failures()
            if not failures:
                failures = self._self_check(rechecked)
                rechecked = rechecked or bool(failures)
        if not failures:
            return Continue(recorded, self.finish)
        text = "\n\n".join(failures)
        if laps >= MAX_LAPS:
            notes = f"{text}\n\nThe checks still fail after {laps} repair turn(s)."
            return self._block(recorded, notes, "the checks", blocks, phase="review")
        return Continue(
            recorded,
            self.review,
            report=text,
            laps=laps + 1,
            blocks=blocks,
            number=self._next_round(),
            rechecked=rechecked,
        )

    def _gate_failures(self, lap: int) -> list[str]:
        document = self.output(record_plan).document
        self.call(resolve_impl_context, self.ctx.spec_dir, plan=document)
        if self.branch:
            self.call(
                branch_code_repos, self.ctx.spec_dir, self.branch, plan=document
            )
        report = self._first_failure(lap)
        return [] if report is None else [report_text(report)]

    def _first_failure(self, lap: int) -> FailureReport | None:
        stamped = self.call(
            check_story_status,
            self.ctx.story_slug,
            epic=self.ctx.story_epic,
            story_path=self.ctx.story_path,
        )
        impl = self.output(resolve_impl_context)
        if stamped.status == "dirty":
            return from_findings(
                "story status",
                [
                    Finding(
                        target=self.ctx.story_path,
                        issue=(
                            f"the story's Status reads '{stamped.written}', which marks it "
                            "finished. The run reads that line to pick work, so the story "
                            "drops out of every later pass and out of QA."
                        ),
                        repair=(
                            "put the Status line back to the value it held before this "
                            "story's work. `git diff` on the story file shows it. Record "
                            "what you ran as prose under `## Implementation Status` instead. "
                            "The run stamps the outcome itself, from a QA run it performed."
                        ),
                    )
                ],
                self.ctx.story_path,
                lap,
            )
        copies = self.call(
            check_copies,
            [entry.cwd for entry in impl.dispatch_list if entry.type != "docs"],
            story_slug=self.ctx.story_slug,
            story_id=self.ctx.story_id,
        )
        if copies.findings:
            return from_findings("copies", copies.findings, copies.cwd, lap)
        checks = self.call(
            resolve_check_set,
            tuple(impl.dispatch_list),
            self.ctx.story_slug,
            self.ctx.story_id,
        )
        for entry in checks.checks:
            outcome = GateOutcome()
            for gate in GATE_ORDER:
                outcome = self.call(
                    run_gate, entry.cwd, entry.service, gate, service_type=entry.type
                )
                if outcome.status == "dirty":
                    return from_gate(outcome, entry.cwd, lap)
        return None

    def _settle(self) -> list[str]:
        w = self._worklist
        items = work.open_findings(w, self._work_id)
        ids = [it.id for it in items]
        if not ids:
            return []
        context = self.call(
            resolve_review_context,
            self.ctx.spec_dir,
            workspace=self.workspace,
        )
        verdict = self.call(
            settle_findings,
            self.ctx.story_slug,
            self.ctx.story_id,
            filed=ids,
            repos=context.affected_repo_paths,
            reuse=[it.id for it in items if it.payload.get("category") == "Reuse"],
        )
        work.move(w, verdict.settled, work.SETTLED, kind=work.FINDING, by="settlement")
        work.move(w, verdict.declined, work.DECLINED, kind=work.FINDING, by="settlement")
        work.move(w, verdict.open, work.OPEN, kind=work.FINDING, by="settlement")
        failures: list[str] = []
        if verdict.open or verdict.errors:
            reasons = rejected_text(verdict.rejected, verdict.errors)
            unanswered = [fid for fid in verdict.open if fid not in verdict.rejected]
            lines = [f"Answers: {len(verdict.open)} finding(s) are still open."]
            if unanswered:
                lines.append("No answer settles " + ", ".join(f"`{fid}`" for fid in unanswered) + ".")
            if reasons:
                lines.append(reasons)
            failures.append("\n".join(lines))
        if self.has_delegate("advisor"):
            heard = consulted(self._state_dir, self._work_id)
            unconsulted = [fid for fid in verdict.declined if fid not in heard]
            if unconsulted:
                work.move(w, unconsulted, work.OPEN, kind=work.FINDING, by="settlement")
                failures.append(unconsulted_text(unconsulted))
        return failures

    def _leftovers(self) -> list[str]:
        state = self.call(
            check_repos_clean, self.ctx.story_slug, self.ctx.spec_dir, list(self.preexisting)
        )
        return [] if state.clean else [leftover_text(state.dirty)]

    def _walk_failures(self) -> list[str]:
        if self.follow_up_title:
            return []
        walk = self.call(
            acceptance_walk, self.ctx.story_path, self.ctx.spec_dir
        )
        return [walk_text(walk.missing, walk.criteria)] if walk.missing else []

    def _self_check(self, rechecked: bool) -> list[str]:
        ids = self.call(last_failed_scenarios, self.ctx.spec_dir).ids
        if not ids:
            return []
        lease = copy_lease(self.ctx.story_id or self.ctx.story_slug, self.run_id, "dev")
        target = self.call(stack_target, self.ctx.story_slug, lease)
        started = time.monotonic()
        try:
            return self._rerun(ids, target.near, target.lease, rechecked)
        finally:
            self.call(release_copy, near=target.near, lease=target.lease)
            self.logger.info("self-check took %.0fs", time.monotonic() - started)

    def _rerun(self, ids: list[str], near: str, lease: str, rechecked: bool) -> list[str]:
        stack = self.call(ensure_stack, near=near, lease=lease)
        if stack.ready not in ("yes", "unneeded"):
            self.logger.info("self-check skipped: the QA stack is not up (%s)", stack.ready)
            return []
        run = self.call(
            run_qa_plan, self.ctx.spec_dir, near=near, lease=lease, only=ids
        )
        if run.status == "passed":
            self.logger.info("self-check: %d scenario(s) QA failed now pass", len(ids))
            return []
        if run.status != "failed":
            self.logger.info("self-check skipped: the scoped run ended %s", run.status)
            return []
        still = list(failed_scenario_ids(run)) or ids
        if rechecked:
            self.logger.info(
                "self-check: %d scenario(s) still fail after one bounce, QA owns them now: %s",
                len(still),
                ", ".join(still),
            )
            return []
        return [self_check_text(failed_scenarios_arg(self.ctx.spec_dir, still))]

    def finish(self) -> Done:
        """Report which findings settled and which the dev owner declined."""
        mine = work.findings_of(self._worklist, self._work_id)
        return Done(
            DevOutcome(
                settled=[it.id for it in mine if it.status == work.SETTLED],
                declined=[it.id for it in mine if it.status == work.DECLINED],
            )
        )

    def _block(
        self, result: object, notes: str, where: str, blocks: int, phase: str
    ) -> Continue | Await:
        if self.operator_mode in HUMAN_MODES or blocks >= MAX_BLOCKS:
            return self._ask(notes, where, blocks, phase)
        return Continue(
            result, self.resolve, notes=notes, where=where, blocks=blocks, phase=phase
        )

    def _ask(
        self,
        notes: str,
        where: str,
        blocks: int,
        phase: str,
        result: OperatorResolution | None = None,
    ) -> Await:
        gate = escalation(
            self,
            block_kind="dev",
            where=where,
            notes=notes,
            number=blocks + 1,
            result=result,
        )
        return Await(
            context_path(self), gate.body, self.read_operator, blocks=blocks + 1, phase=phase
        )

    def resolve(
        self, notes: str, where: str, blocks: int = 0, phase: str = "review"
    ) -> Continue | Await:
        """Answer a block from what is already written down, or ask the operator."""
        self.logger.info("resolving a block at %s", where, extra={"activity": True})
        result = self.agent(
            "shared/prompts/resolve-operator.md",
            returns=OperatorResolution,
            power=RESOLVER_POWER,
            timeout=UNBOUNDED,
            add_dirs=workspace_dirs(self),
            args=resolver_args(self, block_kind="dev", notes=notes),
        )
        if answered(self, result, "dev"):
            return Continue(result, self.read_operator, blocks=blocks + 1, phase=phase)
        return self._ask(notes, where, blocks, phase, result)

    def read_operator(self, blocks: int = 0, phase: str = "review") -> Continue | Done:
        """Log the answer, then resume the phase that blocked, on its conversation, with the answer in hand."""
        answer = self.call(read_operator_context, self.ctx.story_path)
        work.log_answer(self.run_dir, f"{self._work_id}: {answer.scope}", answer.content)
        if answer.scope == "epic":
            self.logger.info("the operator scoped the answer to the epic, so the run replans")
            return Done(DevOutcome(status="replan", operator_notes=answer.content))
        if phase == "plan":
            return Continue(answer, self.plan, operator_context=answer.content, blocks=blocks)
        if phase == "build":
            return Continue(answer, self.build, operator_context=answer.content, blocks=blocks)
        return Continue(
            answer,
            self.review,
            operator_context=answer.content,
            blocks=blocks,
            number=self._next_round(),
        )


__all__ = ["Dev"]
