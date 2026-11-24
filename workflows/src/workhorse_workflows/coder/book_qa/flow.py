"""One seat brings a story's service books up to its claims, and the run plays them against the story's code."""
from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar

from pydantic import PositiveInt
from workhorse._vendor.stablemate_core import books
from workhorse.pyflow import AgentTimeout, Await, Continue, Done

from workhorse_workflows.coder.book_qa.apps import service_app
from workhorse_workflows.coder.book_qa.nodes import (
    BOOK_OUT,
    OUTSIDE_SYSTEM,
    PLAN_FILE,
    book_check,
    book_plan,
    book_run,
    book_scope,
    commit_service_book,
    covered_services,
    owed_summary,
    read_book_record,
    stamp_books_verified,
    story_base_of,
    write_book_record,
    write_qa_plan,
    write_qa_review,
)
from workhorse_workflows.coder.book_qa.review import (
    REVIEW_LAPS,
    missing_criteria,
    missing_text,
    unmet_findings,
    unobserved,
)
from workhorse_workflows.coder.shared import roles
from workhorse_workflows.coder.shared.plan import resolve_impl_context
from workhorse_workflows.coder.shared.owner import REVIEW_MINUTES, cut_notes, turn_seconds
from workhorse_workflows.coder.shared.qa_owner import QaOwner
from workhorse_workflows.coder.shared.schemas.book_qa import (
    BookPlan,
    BookQaOwnerResult,
    QaReviewResult,
    ReviewVerdict,
    ServiceCalls,
)
from workhorse_workflows.coder.shared.schemas.qa import (
    QaFinding,
    QaFlowResult,
    QaFlowStatus,
    QaResult,
)
from workhorse_workflows.coder.shared.stack import ensure_stack, hold_copy, stack_target
from workhorse_workflows.coder.shared.walk import story_criteria
from workhorse_workflows.kit import find_book_package, find_book_root, find_docs_root
from workhorse_workflows.kit.leased_env import scoped_envs
from workhorse_workflows.kit.qa.runner import copy_lease

ENVIRONMENT_EXIT = 3
AFFECTED_USAGE_EXIT = 2


def _gate(gate: str, notes: str) -> str:
    """One failed check, as the seat's next turn reads it."""
    return f"Check: {gate}\n\n{notes.strip() or 'the check reported no detail.'}"


def _earlier_findings(findings: list[QaFinding]) -> str:
    """The findings an earlier pass recorded, as the seat's next turn reads them."""
    rows = "\n".join(f"- `{f.id}`, target `{f.target}`: {f.issue}" for f in findings)
    return _gate(
        "the findings of the earlier pass",
        "An earlier pass of this story reported the findings below, and the developer has worked on the story since. "
        "Judge each again against the running app. Report a finding again only when the app still fails it. "
        "For each finding the app now meets, state the claim in the book as current behaviour and remove any "
        "known-defect entry the earlier pass wrote for it.\n\n" + rows,
    )


class BookQa(QaOwner):
    """Judge one story by a run of the executable book of each service it touches."""

    LABEL_PREFIX: ClassVar[str] = "book-qa"

    book_play_minutes: int = 15
    review_minutes: PositiveInt = REVIEW_MINUTES

    def start(self) -> Continue | Await | Done:
        """Find the story's covered services, bring a stack copy up for them, and replay the recorded calls or call the seat."""
        covered = self.call(
            covered_services, self.ctx.story_services, story_slug=self.ctx.story_slug, story_id=self.ctx.story_id
        )
        if not covered.services:
            self.logger.info("no service of %s has an executable book", self.ctx.story_slug)
            return Done(QaFlowResult(status="passed"))
        self.call(resolve_impl_context, self.ctx.spec_dir)
        self.call(
            story_base_of,
            story_slug=self.ctx.story_slug,
            story_id=self.ctx.story_id,
            services=covered.services,
        )
        lease = copy_lease(self.ctx.story_id or self.ctx.story_slug, self.run_id)
        target = self.call(stack_target, self.ctx.story_slug, lease, services=list(covered.services))
        stack = self.call(ensure_stack, near=target.near, lease=target.lease)
        if stack.ready == "no":
            notes = _gate("the QA stack", f"The stack did not come up at step `{stack.failed_step}`.\n\n{stack.notes}")
            return self._ask(notes, "the QA environment", 0)
        record = self.call(read_book_record, self.ctx.spec_dir)
        if record.services and record.findings:
            return Continue(stack, self.work, report=_earlier_findings(record.findings))
        if record.services:
            return Continue(record, self.check, unreached=list(record.unreached))
        return Continue(stack, self.work)

    @property
    def _review_session(self) -> str:
        return f"{self.LABEL_PREFIX}-review:{self.ctx.story_slug}"

    def _retire(self, status: QaFlowStatus) -> None:
        """Release the stack copy, and end both sessions unless the developer takes the findings."""
        super()._retire(status)
        self.reset_session(self._review_session)

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
            "service_package": find_book_package(self.repo_dir),
            "service_books": str(find_book_root(self.repo_dir) / books.package_folder(find_book_package(self.repo_dir))),
            "target_env": self.target_env,
            "services": self.output(covered_services).services,
            "story_base": self.output(story_base_of).base,
            "service_apps": self._service_apps(),
        }

    def _service_apps(self) -> list[dict[str, str]]:
        """The module, code checkout and story base of each covered service."""
        bases = self.output(story_base_of).bases
        found: list[dict[str, str]] = []
        for name in self.output(covered_services).services:
            sa = service_app(self.repo_dir, self.workspace, name)
            if sa is not None:
                found.append({"name": name, "module": f"{sa.package}.{name}", "app": str(sa.app), "base": bases.get(name, "")})
        return found

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
        try:
            with scoped_envs(self.output(stack_target).env):
                result: BookQaOwnerResult = self.agent(
                    turn.prompt,
                    returns=turn.returns,
                    **self._owner_options(),
                    args=turn.args
                    | self._owner_args()
                    | {"report": report, "operator_context": operator_context},
                )
        except AgentTimeout as exc:
            return self._ask(cut_notes("The book turn", exc), "the book turn", blocks)
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
        """Check each covered service's book, let `ostler book affected` select what to play from the story's diff, play it, and send what failed to the seat, the operator or the developer, then hand a green pass to the end review. `calls` is read by no check: an old checkpoint may still carry it."""
        services = self.output(covered_services).services
        target = self.output(stack_target)
        self.call(hold_copy, lease=target.lease)
        out_dir = str(Path(self.ctx.spec_dir) / BOOK_OUT)
        plans: list[BookPlan] = []
        exits: dict[str, int] = {}
        played = False
        for name in services:
            sa = service_app(self.repo_dir, self.workspace, name)
            package = sa.package if sa is not None else find_book_package(self.repo_dir)
            checked = self.call(book_check, name)
            if checked.exit_code:
                return self._lap(checked, [_gate(f"ostler book check {package}.{name}", checked.output)], laps, blocks)
            plan = self.call(book_plan, name, self.ctx.spec_dir, story_slug=self.ctx.story_slug, story_id=self.ctx.story_id)
            plans.append(plan)
            if plan.exit_code == AFFECTED_USAGE_EXIT:
                self.call(write_qa_plan, self.ctx.spec_dir, plans, exits)
                return self._lap(plan, [_gate(f"ostler book affected {package}.{name}", plan.output)], laps, blocks)
            if plan.uncovered:
                self.call(write_qa_plan, self.ctx.spec_dir, plans, exits)
                listing = "\n".join(f"- `{entry}`" for entry in plan.uncovered)
                text = (
                    f"These changed files or functions of the story are named by no element of the book of `{name}`:\n\n{listing}\n\n"
                    "Each changed file or function the story touched must be named by an element's `source=` or by an "
                    "ignore pattern of the book. The plays cannot be selected until it is."
                )
                return self._lap(plan, [_gate(f"ostler book affected {package}.{name}", text)], laps, blocks)
            scope = self.call(book_scope, name, list(self.preexisting))
            owed = [*(plan.owed_reasons if plan.plan == "whole" else []), *([", ".join(scope.shared)] if scope.shared else [])]
            if plan.plan == "whole" and not owed:
                owed = ["the selection could not narrow the story's change"]
            if owed:
                plans[-1] = plan = plan.model_copy(update={"owed": owed_summary(owed), "owed_reasons": owed})
                self.logger.info("owed to the scheduled whole play for %s: %s", name, plan.owed)
            direct_titles, direct_calls = (plan.direct_journeys, plan.direct_only) if plan.direct else (plan.by_journey, plan.only)
            if not direct_calls and not direct_titles:
                self.logger.info("no play for %s: %s", name, plan.reason or f"the plan is {plan.plan}")
                continue
            self.logger.info(
                "playing %d call(s) and %d journey(s) of %s, limit %d min",
                len(direct_calls),
                len(direct_titles),
                name,
                self.book_play_minutes,
                extra={"activity": True},
            )
            play = self.call(
                book_run, name, direct_calls, target.lease, out_dir, self.book_play_minutes, direct_titles, True, direct=plan.direct
            )
            played = True
            exits[name] = play.exit_code
            if play.owed:
                plans[-1] = plan = plan.model_copy(update={"cut": play.owed})
                self.logger.warning("the play of %s was cut: %s", name, play.owed)
            self.call(write_qa_plan, self.ctx.spec_dir, plans, exits)
            if play.exit_code == ENVIRONMENT_EXIT:
                return self._ask(_gate(f"ostler book run {package}.{name}", play.output), "the QA environment", blocks)
            if play.exit_code:
                return self._lap(play, [_gate(f"ostler book run {package}.{name}", play.output)], laps, blocks)
        self.call(write_qa_plan, self.ctx.spec_dir, plans, exits)
        total = sum(plan.changed for plan in plans if OUTSIDE_SYSTEM not in plan.reason)
        owed_reasons = [f"- `{plan.service}`: {plan.owed}" for plan in plans if plan.owed and OUTSIDE_SYSTEM not in plan.reason]
        if not played and owed_reasons:
            text = (
                "The story's change could not be narrowed to any play, so nothing was played and these are owed "
                "to the scheduled whole play:\n\n" + "\n".join(owed_reasons) + "\n\n"
                "State the change in an element a play reaches, so the selection can narrow to it."
            )
            return self._lap(None, [_gate("the story's plays", text)], laps, blocks)
        if not played and total:
            text = (
                f"The story changed {total} files and the books select no play for them, so the book does not "
                "state what the story changed. State it in the book, or name the files in an ignore pattern."
            )
            reaches = [plan for plan in plans if plan.direct and (plan.reached_calls or plan.reached_journeys)]
            if reaches:
                text += (
                    f"\n\nThe change reaches {sum(p.reached_calls for p in reaches)} call(s) and "
                    f"{sum(p.reached_journeys for p in reaches)} journey(s) only through shared code or shared book "
                    "definitions, and the scheduled whole play owes them. Add or edit the journey that states the "
                    "story's claims, so the story plays it."
                )
            return self._lap(None, [_gate("the story's plays", text)], laps, blocks)
        recorded = [
            ServiceCalls(service=plan.service, calls=plan.direct_only if plan.direct else plan.only).model_dump()
            for plan in plans
        ]
        change_read = list(dict.fromkeys(plan.read for plan in plans if plan.read))
        if findings:
            return Continue(
                None, self.land, recorded=recorded, findings=findings, unreached=list(unreached or []), laps=laps, blocks=blocks
            )
        return Continue(
            None, self.review, recorded=recorded, unreached=list(unreached or []), change_read=change_read, laps=laps, blocks=blocks
        )

    def review(
        self,
        recorded: list[dict[str, Any]] | None = None,
        unreached: list[str] | None = None,
        change_read: list[str] | None = None,
        report: str = "",
        operator_context: str = "",
        review_laps: int = 0,
        laps: int = 0,
        blocks: int = 0,
    ) -> Continue | Await:
        """Run the end review: one capped turn judges each acceptance criterion of the story by the plays, the tests and the recorded evidence."""
        criteria = self.call(story_criteria, self.ctx.story_path).criteria
        if not criteria:
            self.logger.info("%s lists no acceptance criterion, so the end review has nothing to judge", self.ctx.story_slug)
            return Continue(None, self.land, recorded=recorded, unreached=unreached, laps=laps, blocks=blocks)
        target = self.output(stack_target)
        self.call(hold_copy, lease=target.lease)
        self.logger.info(
            "reviewing %d criteria of %s, limit %d min",
            len(criteria),
            self.ctx.story_slug,
            self.review_minutes,
            extra={"activity": True},
        )
        turn = roles.turn(self, "qa-review", returns=QaReviewResult)
        spec = Path(self.ctx.spec_dir)
        try:
            with scoped_envs(target.env):
                result: QaReviewResult = self.agent(
                    turn.prompt,
                    returns=turn.returns,
                    **self._owner_options(turn_seconds(self.review_minutes), self._review_session),
                    args=turn.args
                    | self._owner_args()
                    | {
                        "criteria": criteria,
                        "unreached": unreached or [],
                        "change_read": change_read or [],
                        "qa_plan": str(spec / PLAN_FILE),
                        "play_reports": str(spec / BOOK_OUT),
                        "lease": target.lease,
                        "report": report,
                        "operator_context": operator_context,
                    },
                )
        except AgentTimeout as exc:
            return self._ask_review(
                cut_notes("The end review", exc, "review_minutes"),
                blocks,
                recorded=recorded,
                unreached=unreached,
                change_read=change_read,
                laps=laps,
            )
        missing = missing_criteria(result.verdicts, len(criteria))
        if missing and review_laps < REVIEW_LAPS:
            return Continue(
                result,
                self.review,
                report=_gate("the end review", missing_text(missing)),
                review_laps=review_laps + 1,
                recorded=recorded,
                unreached=unreached,
                change_read=change_read,
                laps=laps,
                blocks=blocks,
            )
        if missing:
            notes = _gate("the end review", missing_text(missing)) + "\n\nThe review still left them out after one more turn."
            return self._ask_review(
                notes, blocks, recorded=recorded, unreached=unreached, change_read=change_read, laps=laps
            )
        return Continue(
            result,
            self.land,
            recorded=recorded,
            unreached=unreached,
            criteria=criteria,
            verdicts=[v.model_dump() for v in result.verdicts],
            laps=laps,
            blocks=blocks,
        )

    def _ask_review(self, notes: str, blocks: int, **lane: Any) -> Await:
        path, body = self._escalate(notes, "the end review", blocks)
        return Await(path, body, self.read_review_operator, blocks=blocks + 1, **lane)

    def read_review_operator(
        self,
        blocks: int = 0,
        recorded: list[dict[str, Any]] | None = None,
        unreached: list[str] | None = None,
        change_read: list[str] | None = None,
        laps: int = 0,
    ) -> Continue | Done:
        """Log the operator's answer to a stopped end review, then run the review again with it in hand."""
        answer = self._take_answer()
        if answer.scope == "epic":
            self.reset_session(self._review_session)
            return self._replan(answer)
        return Continue(
            answer,
            self.review,
            operator_context=answer.content,
            recorded=recorded,
            unreached=unreached,
            change_read=change_read,
            laps=laps,
            blocks=blocks,
        )

    def land(
        self,
        recorded: list[dict[str, Any]] | None = None,
        findings: list[dict[str, Any]] | None = None,
        unreached: list[str] | None = None,
        criteria: list[str] | None = None,
        verdicts: list[dict[str, Any]] | None = None,
        laps: int = 0,
        blocks: int = 0,
    ) -> Continue | Await | Done:
        """Write the review, stamp the books when nothing failed, land the book commit and the record, and finish."""
        services = self.output(covered_services).services
        judged = [ReviewVerdict.model_validate(v) for v in verdicts or []]
        count = len(criteria or [])
        unmet = unmet_findings(judged, criteria or [], self.ctx.story_path)
        unseen = unobserved(judged, count)
        if judged:
            self.call(write_qa_review, self.ctx.spec_dir, criteria or [], judged)
        if unseen:
            self.logger.warning(
                "the end review of %s observed %d of %d criteria nowhere: %s",
                self.ctx.story_slug,
                len(unseen),
                count,
                ", ".join(str(v.criterion) for v in unseen),
            )
        seat = [QaFinding.model_validate(f) for f in findings or []]
        if not seat and not unmet:
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
        self.call(
            write_book_record,
            self.ctx.spec_dir,
            [ServiceCalls.model_validate(r) for r in recorded or []],
            seat,
            list(unreached or []),
            unseen,
        )
        found = [*seat, *unmet]
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
