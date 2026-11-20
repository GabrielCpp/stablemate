"""Every book the app has left behind. One book after another, an owner turn updates the book from what its stale report names and the diff of those files, the run judges it with the book's own check and a targeted run, and a green book is stamped verified at the app's HEAD and committed."""
from __future__ import annotations

from collections.abc import Callable
from typing import NamedTuple

from workhorse.pyflow import Await, Continue, Done, Transition
from workhorse.worklist import WorkItem
from workhorse_workflows.kit.schema import schema_block
from workhorse_workflows.okf_book.catch_up.models import STALE, BookOutcome, BookReport, CatchUpOutcome, CatchUpReply, FormatMove, ModuleCheck, Roots
from workhorse_workflows.okf_book.catch_up.nodes import BOOK, catch_up_diff, catch_up_fill, catch_up_format_notes, catch_up_move, catch_up_outcomes, catch_up_record
from workhorse_workflows.okf_book.catch_up.report import read_check
from workhorse_workflows.okf_book.shared.book_commits import caught_up_book_commit_subject, format_book_commit_subject
from workhorse_workflows.okf_book.shared.book_flow import BLOCKED_GATE, COULD_NOT_JUDGE, ENVIRONMENT_GATE, MAX_LAPS, RED_GATE, BookFlow, blocked_question, environment_question, red_question
from workhorse_workflows.okf_book.shared.book_format import mark_book_format
from workhorse_workflows.okf_book.shared.book_gates import AFFECTED_PLANNED, BookGate, python_book_affected, python_book_calls, python_book_check, python_book_run, python_book_verified, run_flags

UPDATE_PROMPT = "catch_up/prompts/update-book.md"
STALE_GATE = "catch-up-stale.md"


class Lap(NamedTuple):
    """The book a gate judged, the lap it was judged on, and what the owner added and ignored so far."""

    service: str
    number: int
    added: list[str]
    ignored: list[str]


def owner_chain(service: str) -> str:
    return f"catchup:{service}"


class CatchUpBooks(BookFlow):
    """Files each book the app has changed since the commit it was verified at, and works them one at a time, with an owner turn per lap on a book and the book's own gates and the stamp between laps. A book still red after three laps, an owner that replies blocked, and a stale report or check that cannot be read each wait on an operator gate, and the answer goes to the owner's next turn on the same book or reads the report again. The run ends on a line per book."""

    stack_copy: str = ""
    services: list[str] = []
    format_history: str = ""

    def start(self) -> Continue[...]:
        """File the books that are behind."""
        return Continue(None, self.fill).because("find the books that are behind")

    def fill(self) -> Continue[...] | Await[...]:
        """Read the stale report of each book not yet judged and the check of each book with nothing stale, file the books behind on the work list and record the rest. A report or a check that cannot be read waits for the operator, whose answer reads it again."""
        filed = self.call(catch_up_fill, Roots(book=self.root, app=self.code_root, history=self.format_history), tuple(self.services), self.run_dir)
        if filed.unread:
            books = "\n\n".join(f"{service}:\n{said}" for service, said in sorted(filed.unread.items()))
            question = f"The stale report or the check of these books could not be read:\n\n{books}\n\nFix what it names, then answer here to read them again."
            return Await(self.run_dir / STALE_GATE, question, self.fill).because("a stale report or a check could not be read")
        return Continue(filed, self.books).because("the books are filed")

    def books(self) -> Transition:
        """Take the next stale book, a resumed run taking first the one it stopped on, and end on the summary when none is left."""
        return self.pipeline("book", to=self.take, n=1) or Continue(None, self.summarize).because("every book is judged")

    def take(self, items: list[WorkItem]) -> Continue[...]:
        """Send the owner the first lap of the book taken."""
        return Continue(None, self.write, service=items[0].id, gate="", lap=1, added=[], ignored=[]).because("update the book")

    def _report(self, service: str) -> BookReport:
        item = next(item for item in self.work_list.items(BOOK) if item.id == service)
        return BookReport.model_validate(item.payload)

    def _sections(self, report: BookReport) -> list[dict[str, object]]:
        return [
            {
                "module": module.module,
                "verified": module.verified,
                "elements": [{"name": name, "files": pointers} for name, pointers in sorted(module.elements.items())],
                "new_files": module.new_files,
                "gone": module.gone,
                "diff": self.call(catch_up_diff, self.code_root, module.verified, tuple(module.files)),
            }
            for module in report.modules
        ]

    @staticmethod
    def _format(report: BookReport) -> dict[str, object] | None:
        if report.format is None or not report.format.behind:
            return None
        return {"commits": [{"sha": commit.sha, "short": commit.sha[:7], "subject": commit.subject} for commit in report.format.commits], "diff": report.format.diff}

    @staticmethod
    def _findings(report: BookReport) -> list[dict[str, object]] | None:
        if not report.for_format:
            return None
        return [{"module": check.module, "count": check.findings, "lines": check.lines, "unlisted": check.unlisted} for check in report.checks if check.red]

    def write(self, service: str, gate: str, lap: int, added: list[str], ignored: list[str]) -> Continue[...] | Await[...]:
        """One owner turn updates the book from its stale report and the diff, opening on what the last gate printed. A turn that ends without a reply starts the next one fresh, and the gates judge what it left."""
        report = self._report(service)
        args = {
            "service": service,
            "package": f"services/{service}",
            "modules": [module.module for module in report.modules],
            "book_root": self.root.as_posix(),
            "app_root": self.code_root.as_posix(),
            "stack_copy": self.stack_copy,
            "app_changed": report.verdict == STALE,
            "sections": self._sections(report),
            "format": self._format(report),
            "findings": self._findings(report),
            "gate": gate,
            "result_schema": schema_block(CatchUpReply),
        }
        reply = self._timed_turn(
            service,
            UPDATE_PROMPT,
            CatchUpReply(),
            lambda: self.agent(UPDATE_PROMPT, returns=CatchUpReply, power="high", timeout=float("inf"), args=args, cwd=self.root, add_dirs=self._add_dirs(), session=owner_chain(service)),
            session=owner_chain(service),
        )
        _ = self.call(catch_up_format_notes, self.run_dir, service, tuple(reply.format))
        if reply.blocked:
            question = blocked_question(service, reply.blocked)
            return Await(self.run_dir / BLOCKED_GATE, question, self.heard, question=question, gate_name=BLOCKED_GATE, service=service, lap=lap, kept={"added": sorted({*added, *reply.added}), "ignored": sorted({*ignored, *reply.ignored})}).because(
                "the owner is blocked"
            )
        return Continue(reply, self.check, service=service, lap=lap, added=sorted({*added, *reply.added}), ignored=sorted({*ignored, *reply.ignored})).because("check the book")

    def heard(self, question: str, gate_name: str, service: str, lap: int, kept: dict[str, list[str]]) -> Continue[...]:
        """Hand the operator's answer to the owner's next turn on the same book."""
        gate = self._owner_gate(question, gate_name)
        return Continue(gate, self.write, service=service, gate=gate, lap=lap, added=kept["added"], ignored=kept["ignored"]).because("the operator answered")

    def check(self, service: str, lap: int, added: list[str], ignored: list[str], seen: list[str] | None = None) -> Continue[...] | Await[...]:
        """Run the check of each of the book's modules. A pass sends the book through the repo's commit checks, and the first fail sends the owner another lap."""
        gate, red = self._checked(service, lap, added, ignored)
        return red or Continue(gate, self.checks, service=service, lap=lap, added=added, ignored=ignored, seen=seen or []).because("the check passes")

    def checks(self, service: str, lap: int, added: list[str], ignored: list[str], seen: list[str] | None = None) -> Continue[...] | Await[...]:
        """Meet the repo's commit checks over the book's package before the targeted run, so a refusal costs no replay. Each refusal goes to a fix turn and back to the check, and a pass plays the targeted run."""
        waiting = self._checks_or_fix(self._subject(service), self._paths(service), seen or [], self.check, self.checks, service=service, lap=lap, added=added, ignored=ignored)
        return waiting or Continue(None, self.play, service=service, lap=lap, added=added, ignored=ignored).because("the commit checks pass")

    def play(self, service: str, lap: int, added: list[str], ignored: list[str]) -> Continue[...] | Await[...]:
        """Play, in each module, the journeys that call the endpoints and interactions the report named or the owner added, or for a book filed for the format the calls and journeys the owner's edits select. A whole module is never played here. A pass stamps the book, and the first fail sends the owner another lap."""
        gate, red = self._played(service, lap, added, ignored)
        return red or Continue(gate, self.stamp, service=service, lap=lap, added=added, ignored=ignored).because("the run is green")

    def _checked(self, service: str, lap: int, added: list[str], ignored: list[str]) -> tuple[BookGate, Continue[...] | Await[...] | None]:
        gate = BookGate(exit_code=0)
        after: list[ModuleCheck] = []
        for module in self._modules(service):
            gate = self.call(python_book_check, self.root, module, self.code_root)
            if gate.exit_code != 0:
                return gate, self._judged("check", module, gate, Lap(service, lap, added, ignored), self.check)
            after.append(read_check(module, gate.exit_code, gate.output))
        if self._report(service).for_format:
            _ = self.call(catch_up_move, self.run_dir, service, FormatMove(findings_after=sum(c.findings for c in after), notes_after=sum(c.notes for c in after)))
        return gate, None

    def _played(self, service: str, lap: int, added: list[str], ignored: list[str]) -> tuple[BookGate, Continue[...] | Await[...] | None]:
        report = self._report(service)
        if report.for_format:
            return self._played_selected(service, lap, added, ignored)
        gate = BookGate(exit_code=0)
        for module in report.modules:
            known = self.call(python_book_calls, self.root, module.module)
            names = tuple(sorted(set(known) & {*module.elements, *added}))
            if not names:
                continue
            gate = self.call(python_book_run, self.root, module.module, self.run_dir / "book-run" / module.module, run_flags(self.stack_copy, names))
            if gate.exit_code != 0:
                return gate, self._judged("run", module.module, gate, Lap(service, lap, added, ignored), self.play)
        return gate, None

    def _played_selected(self, service: str, lap: int, added: list[str], ignored: list[str]) -> tuple[BookGate, Continue[...] | Await[...] | None]:
        gate = BookGate(exit_code=0)
        calls = journeys = 0
        owed: list[str] = []
        modules = self._modules(service)
        for module in modules:
            selected = self.call(python_book_affected, self.root, module, self.code_root, self.run_dir / "book-plan" / module)
            if selected.exit_code not in AFFECTED_PLANNED:
                said = self._said("affected", module, selected)
                return selected, Await(self.run_dir / ENVIRONMENT_GATE, environment_question(service, "affected", said), self.play, service=service, lap=lap, added=added, ignored=ignored).because("the plays could not be selected")
            if selected.whole:
                why = selected.reason or "the plan is whole"
                owed.append(why if len(modules) == 1 else f"{module}: {why}")
            plays = ([run_flags(self.stack_copy, selected.only, fresh=True)] if selected.only else []) + ([run_flags(self.stack_copy, journeys=selected.journeys, fresh=not selected.only)] if selected.journeys else [])
            for number, flags in enumerate(plays):
                folder = module if number == 0 else f"{module}.journeys"
                gate = self.call(python_book_run, self.root, module, self.run_dir / "book-run" / folder, flags)
                if gate.exit_code != 0:
                    return gate, self._judged("run", module, gate, Lap(service, lap, added, ignored), self.play)
            calls += len(selected.only)
            journeys += len(selected.journeys)
        _ = self.call(catch_up_move, self.run_dir, service, FormatMove(calls=calls, journeys=journeys, exit_code=gate.exit_code if calls or journeys else None, owed="; ".join(owed)))
        return gate, None

    def _replayed(self, service: str, lap: int, added: list[str], ignored: list[str]) -> Continue[...] | Await[...] | None:
        return self._checked(service, lap, added, ignored)[1] or self._played(service, lap, added, ignored)[1]

    def stamp(self, service: str, lap: int, added: list[str], ignored: list[str]) -> Continue[...] | Await[...]:
        """Record the app's HEAD as the commit each of the book's modules is verified at, when the app changed. A module that refuses, because a file or function changed since the verified commit is named by no element or a pointer names a file that is gone, sends the owner another lap with what it printed. A book that moved onto the format then records the commit of the instructions it was judged against."""
        report = self._report(service)
        gate = BookGate(exit_code=0)
        for module in self._modules(service) if report.verdict == STALE else []:
            gate = self.call(python_book_verified, self.root, module, self.code_root)
            if gate.exit_code != 0:
                return self._judged("verified", module, gate, Lap(service, lap, added, ignored), self.stamp)
        if report.format is not None and report.format_behind:
            _ = self.call(mark_book_format, self.root, service, report.format.head)
        return Continue(gate, self.render, service=service, lap=lap, added=added, ignored=ignored).because("the book is stamped")

    def render(self, service: str, lap: int, added: list[str], ignored: list[str]) -> Continue[...] | Await[...]:
        """Render the repo's agent files before the book is committed. A failed render waits for the operator."""
        waiting = self._render_agent_files_or_await(self.render, service=service, lap=lap, added=added, ignored=ignored)
        if waiting:
            return waiting
        return Continue(lap, self.commit, service=service, lap=lap, added=added, ignored=ignored).because("commit the book")

    def commit(self, service: str, lap: int, added: list[str], ignored: list[str]) -> Continue[...] | Await[...]:
        """Commit the book's package and its stamp, and record the book as caught up. A retry after the commit landed finds nothing to commit."""
        report = self._report(service)
        waiting = self._commit_or_await(self._subject(service), self._paths(service), lambda: self._replayed(service, lap, added, ignored), self.commit, service=service, lap=lap, added=added, ignored=ignored)
        if waiting:
            return waiting
        notes = self.call(catch_up_format_notes, self.run_dir, service, ())
        move = self._move(service, report) if report.for_format else None
        outcome = BookOutcome(
            service=service,
            verdict="caught-up",
            laps=lap,
            elements=report.elements,
            added=added,
            ignored=ignored,
            app=report.verdict == STALE,
            moved=report.for_format or report.format_behind,
            format=notes if report.format_behind else [],
            move=move,
        )
        _ = self.call(catch_up_record, self.run_dir, outcome)
        return Continue(outcome, self.books).because("the book is committed")

    def _move(self, service: str, report: BookReport) -> FormatMove:
        recorded = self.call(catch_up_move, self.run_dir, service, FormatMove())
        return recorded.model_copy(update={"findings_before": report.check_findings, "notes_before": report.check_notes})

    def _subject(self, service: str) -> str:
        return caught_up_book_commit_subject(service) if self._report(service).verdict == STALE else format_book_commit_subject(service)

    def _modules(self, service: str) -> list[str]:
        return [module.module for module in self._report(service).modules]

    @staticmethod
    def _said(verb: str, module: str, gate: BookGate) -> str:
        return f"`python -m ostler.book {verb} {module}` exited {gate.exit_code}:\n\n{gate.output}"

    def _judged(self, verb: str, module: str, gate: BookGate, lap: Lap, retry: Callable[..., Transition]) -> Continue[...] | Await[...]:
        said = self._said(verb, module, gate)
        if gate.exit_code == COULD_NOT_JUDGE:
            return Await(self.run_dir / ENVIRONMENT_GATE, environment_question(lap.service, verb, said), retry, service=lap.service, lap=lap.number, added=lap.added, ignored=lap.ignored).because("the book could not be judged")
        if lap.number >= MAX_LAPS:
            question = red_question(lap.service, lap.number, said)
            return Await(self.run_dir / RED_GATE, question, self.heard, question=question, gate_name=RED_GATE, service=lap.service, lap=lap.number, kept={"added": lap.added, "ignored": lap.ignored}).because(
                "the book is still red after the last lap"
            )
        return Continue(said, self.write, service=lap.service, gate=said, lap=lap.number + 1, added=lap.added, ignored=lap.ignored).because("the book is red")

    def summarize(self) -> Done:
        """End on one line per book: current, caught up, or a first book."""
        outcomes = self.call(catch_up_outcomes, self.run_dir)
        lines = [_line(outcome) for outcome in outcomes]
        return Done(CatchUpOutcome(books=outcomes, summary="\n".join(lines))).because("every book is judged")


def _line(outcome: BookOutcome) -> str:
    if outcome.verdict == "current":
        return f"{outcome.service}: current"
    if outcome.verdict == "first-book":
        return f"{outcome.service}: first book, write it with python_book"
    if outcome.move is not None:
        return _moved_line(outcome, outcome.move)
    moved = f"moved onto the format, {_count(outcome, 'applied')} changes applied, {_count(outcome, 'not applicable')} not applicable"
    if not outcome.app:
        return f"{outcome.service}: {moved}"
    line = f"{outcome.service}: caught up in {outcome.laps} laps, {len(outcome.elements)} elements changed, {len(outcome.added)} endpoints added"
    if outcome.ignored:
        line += f", {len(outcome.ignored)} files ignored: {', '.join(outcome.ignored)}"
    return f"{line}, {moved}" if outcome.moved else line


def _moved_line(outcome: BookOutcome, move: FormatMove) -> str:
    line = f"{outcome.service}: moved onto the format in {outcome.laps} laps, check {move.findings_before} findings to {move.findings_after}, notes {move.notes_before} to {move.notes_after}, "
    if move.exit_code is None:
        line += "played nothing"
    else:
        line += f"played {move.calls} calls and {move.journeys} journeys {'green' if move.exit_code == 0 else f'exit {move.exit_code}'}"
    if outcome.format:
        line += f", {_count(outcome, 'applied')} changes applied, {_count(outcome, 'not applicable')} not applicable"
    return f"{line}, owed to a whole play: {move.owed}" if move.owed else line


def _count(outcome: BookOutcome, kind: str) -> int:
    return sum(1 for line in outcome.format if line.partition(" ")[2].startswith(kind))
