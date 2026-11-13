"""One seat brings a story's service books up to its claims, and the run plays them against the story's code."""
from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar

from workhorse.pyflow import Await, Continue, Done

from workhorse_workflows.coder.book_qa.nodes import (
    BOOK_OUT,
    book_check,
    book_run,
    book_scope,
    commit_service_book,
    covered_services,
    read_book_record,
    write_book_record,
)
from workhorse_workflows.coder.shared import roles
from workhorse_workflows.coder.shared.plan import resolve_impl_context
from workhorse_workflows.coder.shared.qa_owner import QaOwner
from workhorse_workflows.coder.shared.schemas.book_qa import (
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
from workhorse_workflows.kit.credentials import scoped_envs
from workhorse_workflows.kit.qa.runner import copy_lease

ENVIRONMENT_EXIT = 3


def _gate(gate: str, notes: str) -> str:
    """One failed check, as the seat's next turn reads it."""
    return f"Check: {gate}\n\n{notes.strip() or 'the check reported no detail.'}"


class BookQa(QaOwner):
    """Judge one story by a run of the executable book of each service it touches."""

    LABEL_PREFIX: ClassVar[str] = "book-qa"

    def start(self) -> Continue | Await | Done:
        """Find the story's covered services, bring a stack copy up for them, and replay the recorded calls or call the seat."""
        covered = self.call(covered_services, self.ctx.story_services)
        if not covered.services:
            self.logger.info("no service of %s has an executable book", self.ctx.story_slug)
            return Done(QaFlowResult(status="passed"))
        self.call(resolve_impl_context, self.ctx.spec_dir)
        lease = copy_lease(self.ctx.story_id or self.ctx.story_slug, self.run_id)
        target = self.call(stack_target, self.ctx.story_slug, lease, services=list(self.ctx.story_services))
        stack = self.call(ensure_stack, near=target.near, lease=target.lease)
        if stack.ready == "no":
            notes = _gate("the QA stack", f"The stack did not come up at step `{stack.failed_step}`.\n\n{stack.notes}")
            return self._ask(notes, "the QA environment", 0)
        record = self.call(read_book_record, self.ctx.spec_dir)
        if record.services:
            return Continue(
                record,
                self.check,
                calls=[s.model_dump() for s in record.services],
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
        }

    def work(
        self,
        report: str = "",
        operator_context: str = "",
        laps: int = 0,
        blocks: int = 0,
    ) -> Continue | Await:
        """Run the seat turn: it names the touched calls and brings the books up to the story."""
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
            calls=[c.model_dump() for c in result.calls],
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
        """Check and play each covered service's calls, and send what failed to the seat, the operator or the developer."""
        services = self.output(covered_services).services
        named = {c.service: c for c in (ServiceCalls.model_validate(c) for c in calls or [])}
        silent = [name for name in services if not (named.get(name) and named[name].calls)]
        if silent:
            text = _gate(
                "the touched calls",
                "Name the calls the story touches, for every covered service. None named for: "
                + ", ".join(silent),
            )
            return self._lap(None, [text], laps, blocks)
        target = self.output(stack_target)
        self.call(hold_copy, lease=target.lease)
        out_dir = str(Path(self.ctx.spec_dir) / BOOK_OUT)
        for name in services:
            checked = self.call(book_check, name)
            if checked.exit_code:
                return self._lap(checked, [_gate(f"ostler book check services.{name}", checked.output)], laps, blocks)
            self.logger.info("playing the book of %s", name, extra={"activity": True})
            scope = self.call(book_scope, name, list(self.preexisting))
            if scope.whole:
                self.logger.info(
                    "playing the whole book of %s: the pass changed a shared part (%s)", name, ", ".join(scope.shared)
                )
            else:
                self.logger.info(
                    "playing the named calls of %s: %d changed path(s), none shared", name, scope.changed
                )
            play = self.call(
                book_run,
                name,
                [] if scope.whole else named[name].calls,
                target.lease,
                out_dir,
                named[name].calls if scope.whole else [],
            )
            if play.exit_code == ENVIRONMENT_EXIT:
                return self._ask(_gate(f"ostler book run services.{name}", play.output), "the QA environment", blocks)
            if play.exit_code:
                return self._lap(play, [_gate(f"ostler book run services.{name}", play.output)], laps, blocks)
        landed = self.call(
            commit_service_book,
            services,
            self.ctx.story_slug,
            self.ctx.story_id,
            self.epic,
            list(self.preexisting),
        )
        if landed.refused:
            return self._lap(landed, [_gate("the book commit", landed.refused)], laps, blocks)
        found = [QaFinding.model_validate(f) for f in findings or []]
        self.call(write_book_record, self.ctx.spec_dir, list(named.values()), found, list(unreached or []))
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
