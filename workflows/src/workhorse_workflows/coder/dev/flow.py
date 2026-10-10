"""One strong dev agent builds, reviews and fixes a story through its subagents, and the run checks it."""
from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar

from workhorse import worklist as wl
from workhorse.pyflow import Await, Continue, Done, Workflow

from workhorse_workflows.coder.dev.report import findings_text, plan_arg, rejected_text, report_text
from workhorse_workflows.coder.shared import paths, roles, work
from workhorse_workflows.coder.shared.backlog import file_follow_up_backlog
from workhorse_workflows.coder.shared.branches import branch_code_repos
from workhorse_workflows.coder.shared.conversation import story_chain
from workhorse_workflows.coder.shared.dev import check_story_status, read_operator_context
from workhorse_workflows.coder.shared.escalation import context_path, escalation
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
from workhorse_workflows.coder.shared.resolution import RESOLVER_POWER, answered, resolver_args
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
from workhorse_workflows.coder.shared.schemas.dev_story import DevOutcome, DevResult
from workhorse_workflows.coder.shared.schemas.story import StoryPaths
from workhorse_workflows.coder.shared.service_gates import GATE_ORDER, declared_markers, run_gate
from workhorse_workflows.coder.shared.story import (
    guard_story_file,
    prepare_story,
    resolve_workspace_dirs,
    stamp_specs,
    workspace_dirs,
)
from workhorse_workflows.coder.shared.story_commit import check_repos_clean, commit_plan_record
from workhorse_workflows.kit.telemetry import counter_labels

class Dev(Workflow):
    """Dev one work item through one session, then check its plan, gates and answers."""

    story: str = ""
    docs_path: str = ""
    workspace_file: str = ""
    epic: str = ""
    operator_mode: str = "auto"
    target_env: str = "local"
    branch: str = ""
    work_id: str = ""
    follow_up_title: str = ""
    follow_up_reason: str = ""
    note: str = ""
    preexisting: tuple[str, ...] = ()

    injects: ClassVar[tuple[str, ...]] = paths.AMBIENT

    BUDGET_LABELS: ClassVar[tuple[str, ...]] = ("laps", "blocks", "number")

    def setup(self) -> StoryPaths:
        """Resolve the slug to paths and the workspace to directories."""
        self.call(resolve_workspace_dirs, self.docs_path)
        story = self.call(prepare_story, self.docs_path, self.story, self.epic)
        guard_story_file(story)
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
    def _worklist(self) -> wl.WorkList:
        return work.worklist(self.run_dir)

    def _next_round(self) -> int:
        return work.next_round(self._worklist, self._work_id, "review")

    def _rebrief(self) -> str:
        return work.resume_note(
            self.run_dir, self._work_id, self.ctx.story_path, self.ctx.spec_dir
        )

    def _story_args(self) -> dict[str, Any]:
        return {
            "story_slug": self.ctx.story_slug,
            "story_id": self.ctx.story_id or self.ctx.story_slug,
            "epic": self.epic,
            "story_path": self.ctx.story_path,
            "spec_dir": self.ctx.spec_dir,
            "branch": self.branch or self.story,
        }

    def start(self) -> Continue:
        """Hand the work item to the dev owner, with any findings already filed against it."""
        return Continue(None, self.build, note=self.note, number=self._next_round())

    def build(
        self,
        note: str = "",
        operator_context: str = "",
        report: str = "",
        laps: int = 0,
        blocks: int = 0,
        number: int = 1,
    ) -> Continue | Await:
        """Run the dev turn: its subagents plan, build, review and fix the work item."""
        self.logger.info("developing %s", self._work_id, extra={"activity": True})
        w = self._worklist
        turn = roles.turn(self, "dev-story", returns=DevResult)
        result: DevResult = self.agent(
            turn.prompt,
            returns=turn.returns,
            power="high",
            timeout=UNBOUNDED,
            silence=SILENCE_S,
            profile=owner_profile("dev"),
            session=story_chain(self.ctx.story_slug),
            rebrief=self._rebrief,
            add_dirs=workspace_dirs(self),
            args=turn.args
            | self._story_args()
            | {
                "resume_note": self._rebrief(),
                "worklist_path": str(work.worklist_path(self.run_dir)),
                "answers_file": str(Path(self.ctx.spec_dir) / ANSWERS_FILE),
                "review_prefix": f"{self._work_id}/review-{number}.",
                "follow_up_title": self.follow_up_title,
                "follow_up_reason": self.follow_up_reason,
                "note": note,
                "report": report,
                "findings": findings_text(work.open_findings(w, self._work_id)),
                "operator_context": operator_context,
                "markers": self.call(declared_markers).text,
            },
        )
        self.call(stamp_specs, self.docs_path, self.ctx.story_slug)
        self._file_follow_ups(result)
        found = [f.model_dump() for f in result.findings]
        filed = work.file(w, work.finding_items(self._work_id, "review", number, found), by="review")
        if filed:
            self.logger.info("the review filed %d finding(s) against %s", len(filed), self._work_id)
        if result.status == "blocked":
            return self._block(result, result.notes, "the dev turn", blocks)
        return Continue(result, self.check, plan=plan_arg(result), laps=laps, blocks=blocks)

    def _file_follow_ups(self, result: DevResult) -> None:
        entries = [f.model_dump(include={"title", "reason"}) for f in result.follow_ups]
        if not entries:
            return
        w = self._worklist
        item = work.find(w, self._work_id)
        if item is None or item.kind == work.FOLLOW_UP:
            self.call(
                file_follow_up_backlog, self.docs_path, parent=self._work_id, follow_ups=entries
            )
            return
        filed = work.file(w, work.follow_up_items(w, item, entries), by="dev")
        self.logger.info("filed %d follow-up(s) after %s", len(filed), item.id)

    def check(
        self, plan: dict[str, Any] | None = None, laps: int = 0, blocks: int = 0
    ) -> Continue | Await:
        """Check the plan, the gates and every answer, and send what failed back to the dev owner."""
        recorded = self.call(record_plan, plan, self.ctx.spec_dir)
        if recorded.status == "invalid":
            failures = [f"The plan's service paths did not validate: {recorded.errors}"]
        else:
            self.call(
                commit_plan_record, self.epic, self.ctx.story_slug, self.ctx.spec_dir
            )
            failures = self._gate_failures(laps) + self._settle() + self._leftovers()
        if not failures:
            return Continue(recorded, self.finish)
        text = "\n\n".join(failures)
        if laps >= MAX_LAPS:
            notes = f"{text}\n\nThe checks still fail after {laps} repair turn(s)."
            return self._block(recorded, notes, "the checks", blocks)
        return Continue(
            recorded,
            self.build,
            report=text,
            laps=laps + 1,
            blocks=blocks,
            number=self._next_round(),
        )

    def _gate_failures(self, lap: int) -> list[str]:
        document = self.output(record_plan).document
        self.call(
            resolve_impl_context, self.ctx.spec_dir, self.target_env, self.docs_path, plan=document
        )
        self.call(
            branch_code_repos,
            self.ctx.spec_dir,
            self.branch or self.story,
            self.docs_path,
            plan=document,
        )
        report = self._first_failure(lap)
        return [] if report is None else [report_text(report)]

    def _first_failure(self, lap: int) -> FailureReport | None:
        stamped = self.call(
            check_story_status,
            self.docs_path,
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
        for entry in impl.dispatch_list:
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
        ids = [it.id for it in work.open_findings(w, self._work_id)]
        if not ids:
            return []
        context = self.call(
            resolve_review_context,
            self.ctx.spec_dir,
            docs_path=self.docs_path,
            workspace_file=self.workspace_file,
        )
        verdict = self.call(
            settle_findings,
            self.docs_path,
            self.ctx.story_slug,
            self.ctx.story_id or self.ctx.story_slug,
            filed=ids,
            repos=context.affected_repo_paths,
        )
        work.move(w, verdict.settled, work.SETTLED, kind=work.FINDING, by="settlement")
        work.move(w, verdict.declined, work.DECLINED, kind=work.FINDING, by="settlement")
        work.move(w, verdict.open, work.OPEN, kind=work.FINDING, by="settlement")
        if not verdict.open and not verdict.errors:
            return []
        reasons = rejected_text(verdict.rejected, verdict.errors)
        unanswered = [fid for fid in verdict.open if fid not in verdict.rejected]
        lines = [f"Answers: {len(verdict.open)} finding(s) are still open."]
        if unanswered:
            lines.append("No answer settles " + ", ".join(f"`{fid}`" for fid in unanswered) + ".")
        if reasons:
            lines.append(reasons)
        return ["\n".join(lines)]

    def _leftovers(self) -> list[str]:
        state = self.call(
            check_repos_clean, self.ctx.story_slug, self.ctx.spec_dir, list(self.preexisting)
        )
        if state.clean:
            return []
        listing = "\n".join(f"- `{path}`" for path in state.dirty[:40])
        elided = f"\n- … and {len(state.dirty) - 40} more" if len(state.dirty) > 40 else ""
        return [
            "Uncommitted work: these paths changed since the story began and are not "
            f"committed.\n\n{listing}{elided}\n\n"
            "Commit what this story wrote. Leave alone what it did not write, and report "
            "`blocked` naming those paths, so the operator decides what happens to them."
        ]

    def finish(self) -> Done:
        """Report which findings settled and which the dev owner declined."""
        mine = work.findings_of(self._worklist, self._work_id)
        return Done(
            DevOutcome(
                settled=[it.id for it in mine if it.status == work.SETTLED],
                declined=[it.id for it in mine if it.status == work.DECLINED],
            )
        )

    def _block(self, result: object, notes: str, where: str, blocks: int) -> Continue | Await:
        if self.operator_mode in HUMAN_MODES or blocks >= MAX_BLOCKS:
            return self._ask(notes, where, blocks)
        return Continue(result, self.resolve, notes=notes, where=where, blocks=blocks)

    def _ask(
        self, notes: str, where: str, blocks: int, result: OperatorResolution | None = None
    ) -> Await:
        gate = escalation(
            self,
            block_kind="dev",
            where=where,
            notes=notes,
            number=blocks + 1,
            result=result,
        )
        return Await(context_path(self), gate.body, self.read_operator, blocks=blocks + 1)

    def resolve(self, notes: str, where: str, blocks: int = 0) -> Continue | Await:
        """Answer a block from what is already written down, or ask the operator."""
        self.logger.info("resolving a block at %s", where, extra={"activity": True})
        result = self.agent(
            "shared/prompts/resolve-operator.md",
            returns=OperatorResolution,
            power=RESOLVER_POWER,
            timeout=UNBOUNDED,
            add_dirs=workspace_dirs(self),
            args=resolver_args(self, block_kind="dev", notes=notes, docs_path=self.docs_path),
        )
        if answered(self, result, "dev"):
            return Continue(result, self.read_operator, blocks=blocks + 1)
        return self._ask(notes, where, blocks, result)

    def read_operator(self, blocks: int = 0) -> Continue | Done:
        """Log the answer, then resume the dev owner's session with it in hand."""
        answer = self.call(read_operator_context, self.ctx.story_path)
        work.log_answer(self.run_dir, f"{self._work_id}: {answer.scope}", answer.content)
        if answer.scope == "epic":
            self.logger.info("the operator scoped the answer to the epic, so the run replans")
            return Done(DevOutcome(status="replan", operator_notes=answer.content))
        return Continue(
            answer,
            self.build,
            operator_context=answer.content,
            blocks=blocks,
            number=self._next_round(),
        )


__all__ = ["Dev"]
