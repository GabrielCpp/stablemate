"""One seat brings a story's service books up to its claims, and the run plays them against the story's code."""
from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar

from workhorse.pyflow import Await, Continue, Done

from workhorse_workflows.coder.book_qa.nodes import (
    BOOK_OUT,
    book_check,
    book_plan,
    book_run,
    book_scope,
    commit_service_book,
    covered_services,
    read_book_record,
    stamp_books_verified,
    story_base_of,
    write_book_record,
    write_qa_plan,
)
from workhorse_workflows.coder.shared import roles
from workhorse_workflows.coder.shared.plan import resolve_impl_context
from workhorse_workflows.coder.shared.qa_owner import QaOwner
from workhorse_workflows.coder.shared.schemas.book_qa import (
    BookPlan,
    BookQaOwnerResult,
    ServiceCalls,
)
from workhorse_workflows.coder.shared.schemas.qa import (
    QaFinding,
    QaFlowResult,
    QaFlowStatus,
    QaResult,
)
from workhorse_workflows.coder.shared.stack import ensure_stack, hold_copy, stack_target
from workhorse_workflows.kit import find_book_root, find_docs_root
from workhorse_workflows.kit.leased_env import scoped_envs
from workhorse_workflows.kit.qa.runner import copy_lease

ENVIRONMENT_EXIT = 3
AFFECTED_USAGE_EXIT = 2


def _gate(gate: str, notes: str) -> str:
    """One failed check, as the seat's next turn reads it."""
    return f"Check: {gate}\n\n{notes.strip() or 'the check reported no detail.'}"


class BookQa(QaOwner):
    """Judge one story by a run of the executable book of each service it touches."""

    LABEL_PREFIX: ClassVar[str] = "book-qa"

    def start(self) -> Continue | Await | Done:
        """Find the story's covered services, bring a stack copy up for them, and replay the recorded calls or call the seat."""
        covered = self.call(
            covered_services, self.ctx.story_services, story_slug=self.ctx.story_slug, story_id=self.ctx.story_id
        )
        if not covered.services:
            self.logger.info("no service of %s has an executable book", self.ctx.story_slug)
            return Done(QaFlowResult(status="passed"))
        self.call(resolve_impl_context, self.ctx.spec_dir)
        self.call(story_base_of, story_slug=self.ctx.story_slug, story_id=self.ctx.story_id)
        lease = copy_lease(self.ctx.story_id or self.ctx.story_slug, self.run_id)
        target = self.call(stack_target, self.ctx.story_slug, lease, services=list(covered.services))
        stack = self.call(ensure_stack, near=target.near, lease=target.lease)
        if stack.ready == "no":
            notes = _gate("the QA stack", f"The stack did not come up at step `{stack.failed_step}`.\n\n{stack.notes}")
            return self._ask(notes, "the QA environment", 0)
        record = self.call(read_book_record, self.ctx.spec_dir)
        if record.services:
            return Continue(
                record,
                self.check,
                findings=[f.model_dump() for f in record.findings],
                unreached=list(record.unreached),
            )
        return Continue(stack, self.work)

    def _owner_args(self) -> dict[str, Any]:
        """What the seat reads about its story and the services it brings up."""
        return {
            "story_path": self.ctx.story_path,
            "spec_dir": self.ctx.spec_dir,
            "story_slug": self.ctx.story_slug,
            "story_id": self.ctx.story_id,
            "epic": self.epic,
            "docs_root": str(find_docs_root(self.repo_dir)),
            "book_root": str(find_book_root(self.repo_dir)),
            "target_env": self.target_env,
            "services": self.output(covered_services).services,
            "story_base": self.output(story_base_of).base,
        }

    def work(
        self,
        report: str = "",
        operator_context: str = "",
        laps: int = 0,
        blocks: int = 0,
    ) -> Continue | Await:
        """Run the seat turn: it brings the books up to the story."""
        self.logger.info("bringing the book up to %s", self.ctx.story_slug, extra={"activity": True})
        turn = roles.turn(self, "qa-book", returns=BookQaOwnerResult)
        with scoped_envs(self.output(stack_target).env):
            result: BookQaOwnerResult = self.agent(
                turn.prompt,
                returns=turn.returns,
                **self._owner_options(),
                args=turn.args
                | self._owner_args()
                | {"report": report, "operator_context": operator_context},
            )
        if result.status == "blocked":
            return self._block(result, result.notes, "the book turn", blocks)
        if result.status == "findings" and not result.findings:
            return self._lap(
                result,
                [_gate("the seat's findings", "The turn reported `findings` and listed none. List each claim the app does not meet.")],
                laps,
                blocks,
            )
        return Continue(
            result,
            self.check,
            findings=[f.model_dump() for f in result.findings],
            unreached=list(result.unreached),
            laps=laps,
            blocks=blocks,
        )

    def check(
        self,
        calls: list[dict[str, Any]] | None = None,
        findings: list[dict[str, Any]] | None = None,
        unreached: list[str] | None = None,
        laps: int = 0,
        blocks: int = 0,
    ) -> Continue | Await | Done:
        """Check each covered service's book, let `ostler book affected` select what to play from the story's diff, play it, and send what failed to the seat, the operator or the developer. `calls` is read by no check: an old checkpoint may still carry it."""
        services = self.output(covered_services).services
        target = self.output(stack_target)
        self.call(hold_copy, lease=target.lease)
        out_dir = str(Path(self.ctx.spec_dir) / BOOK_OUT)
        plans: list[BookPlan] = []
        exits: dict[str, int] = {}
        played = False
        for name in services:
            checked = self.call(book_check, name)
            if checked.exit_code:
                return self._lap(checked, [_gate(f"ostler book check services.{name}", checked.output)], laps, blocks)
            plan = self.call(book_plan, name, self.ctx.spec_dir, story_slug=self.ctx.story_slug, story_id=self.ctx.story_id)
            plans.append(plan)
            if plan.exit_code == AFFECTED_USAGE_EXIT:
                self.call(write_qa_plan, self.ctx.spec_dir, plans, exits)
                return self._lap(plan, [_gate(f"ostler book affected services.{name}", plan.output)], laps, blocks)
            if plan.uncovered:
                self.call(write_qa_plan, self.ctx.spec_dir, plans, exits)
                listing = "\n".join(f"- `{entry}`" for entry in plan.uncovered)
                text = (
                    f"These changed files or functions of the story are named by no element of the book of `{name}`:\n\n{listing}\n\n"
                    "Each changed file or function the story touched must be named by an element's `source=` or by an "
                    "ignore pattern of the book. The plays cannot be selected until it is."
                )
                return self._lap(plan, [_gate(f"ostler book affected services.{name}", text)], laps, blocks)
            scope = self.call(book_scope, name, list(self.preexisting))
            if plan.plan in ("none", "empty") and not scope.whole:
                self.logger.info("no play for %s: %s", name, plan.reason or f"the plan is {plan.plan}")
                continue
            if plan.plan == "whole" or scope.whole:
                reason = plan.reason or ", ".join(scope.shared)
                self.logger.info("playing the whole book of %s: %s", name, reason)
                plans[-1] = plan.model_copy(update={"plan": "whole", "whole": True, "reason": reason})
                only, journeys, outside = [], [], plan.only
            else:
                self.logger.info("playing the plan of %s: %d call(s), %d journey(s)", name, len(plan.only), len(plan.by_journey))
                only, journeys, outside = plan.only, plan.by_journey, []
            self.logger.info("playing the book of %s", name, extra={"activity": True})
            play = self.call(book_run, name, only, target.lease, out_dir, outside, journeys, True)
            played = True
            exits[name] = play.exit_code
            self.call(write_qa_plan, self.ctx.spec_dir, plans, exits)
            if play.exit_code == ENVIRONMENT_EXIT:
                return self._ask(_gate(f"ostler book run services.{name}", play.output), "the QA environment", blocks)
            if play.exit_code:
                return self._lap(play, [_gate(f"ostler book run services.{name}", play.output)], laps, blocks)
        self.call(write_qa_plan, self.ctx.spec_dir, plans, exits)
        total = sum(plan.changed for plan in plans)
        if not played and total:
            text = (
                f"The story changed {total} files and the books select no play for them, so the book does not "
                "state what the story changed. State it in the book, or name the files in an ignore pattern."
            )
            return self._lap(None, [_gate("the story's plays", text)], laps, blocks)
        if not findings:
            stamped = self.call(
                stamp_books_verified, services, story_slug=self.ctx.story_slug, story_id=self.ctx.story_id
            )
            if stamped.exit_code:
                return self._lap(stamped, [_gate("ostler book verified", stamped.output)], laps, blocks)
        landed = self.call(
            commit_service_book,
            services,
            self.ctx.story_slug,
            self.ctx.story_id,
            self.epic,
            list(self.preexisting),
        )
        if landed.refused:
            self.logger.warning("the book commit was refused: %s", landed.refused)
            return self._lap(landed, [_gate("the book commit", landed.refused)], laps, blocks)
        found = [QaFinding.model_validate(f) for f in findings or []]
        recorded = [ServiceCalls(service=plan.service, calls=plan.only) for plan in plans]
        self.call(write_book_record, self.ctx.spec_dir, recorded, found, list(unreached or []))
        return self._finish("refix" if found else "passed", found)

    def _finish(self, status: QaFlowStatus, findings: list[QaFinding]) -> Done:
        self._retire(status)
        notes = "; ".join(f.issue for f in findings)
        return Done(
            QaFlowResult(
                status=status,
                qa=QaResult(status="failed" if findings else "passed", notes=notes),
                findings=findings,
            )
        )


__all__ = ["BookQa"]
