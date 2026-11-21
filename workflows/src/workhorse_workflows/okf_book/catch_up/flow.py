"""Every book the app has left behind. One book after another, an owner turn updates the book from what its stale report names and the diff of those files, the run judges it with the book's own check and a targeted run, and a green book is stamped verified at the app's HEAD and committed."""
from __future__ import annotations

import textwrap
from collections.abc import Callable
from typing import NamedTuple

from workhorse.pyflow import Await, Continue, Done, Transition
from workhorse.worklist import WorkItem
from workhorse_workflows.kit.schema import schema_block
from workhorse_workflows.okf_book.catch_up.models import ELEMENTS_LISTED, STALE, BookOutcome, BookReport, CatchUpOutcome, CatchUpReply, FormatMove, ModuleCheck, Roots
from workhorse_workflows.okf_book.catch_up.nodes import BOOK, catch_up_declined, catch_up_diff, catch_up_fill, catch_up_format_notes, catch_up_move, catch_up_outcomes, catch_up_record
from workhorse_workflows.okf_book.catch_up.report import kind_moves, note_kinds, note_listing, owed_notes, read_check, undeclined
from workhorse_workflows.okf_book.shared.book_commits import caught_up_book_commit_subject, format_book_commit_subject
from workhorse_workflows.okf_book.shared.book_flow import BLOCKED_GATE, COULD_NOT_JUDGE, ENVIRONMENT_GATE, MAX_LAPS, RED_GATE, BookFlow, blocked_question, environment_question, owed_question, red_question
from workhorse_workflows.okf_book.shared.book_format import mark_book_format
from workhorse_workflows.okf_book.shared.book_gates import AFFECTED_PLANNED, BookGate, CheckSaid, python_book_affected, python_book_calls, python_book_check, python_book_run, python_book_verified, run_flags

UPDATE_PROMPT = "catch_up/prompts/update-book.md"
STALE_GATE = "catch-up-stale.md"
BODY_WIDTH = 72


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
        """Send the owner the first lap of the book taken, after the check's findings and notes of the book as filed are recorded as the before of its move."""
        report = self._report(items[0].id)
        if report.for_format:
            _ = self.call(catch_up_move, self.run_dir, items[0].id, FormatMove(findings_before=report.check_findings, notes_before=report.check_notes))
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
    def _notes(report: BookReport, declined: list[str]) -> list[dict[str, object]] | None:
        if not report.for_format:
            return None
        return [{"kind": group.kind, "count": group.count, "elements": group.elements[:ELEMENTS_LISTED], "more": group.more} for group in note_kinds(undeclined(report.noted, declined))]

    @staticmethod
    def _findings(report: BookReport) -> list[dict[str, object]] | None:
        if not report.for_format:
            return None
        return [{"module": check.module, "count": check.findings, "lines": check.lines, "unlisted": check.unlisted} for check in report.checks if check.red]

    def write(self, service: str, gate: str, lap: int, added: list[str], ignored: list[str]) -> Continue[...] | Await[...]:
        """One owner turn updates the book from its stale report and the diff, opening on what the last gate printed. A turn that ends without a reply starts the next one fresh, and the gates judge what it left."""
        report = self._report(service)
        declined = self.call(catch_up_declined, self.run_dir, service, ())
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
            "notes": self._notes(report, declined),
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
        _ = self.call(catch_up_declined, self.run_dir, service, tuple(reply.declined))
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
        waiting = self._checks_or_fix(self._message(service), self._paths(service), seen or [], self.check, self.checks, service=service, lap=lap, added=added, ignored=ignored)
        return waiting or Continue(None, self.play, service=service, lap=lap, added=added, ignored=ignored).because("the commit checks pass")

    def play(self, service: str, lap: int, added: list[str], ignored: list[str]) -> Continue[...] | Await[...]:
        """Play, in each module, the journeys that call the endpoints and interactions the report named or the owner added, or for a book filed for the format the calls and journeys the owner's edits select. A whole module is never played here. A pass stamps the book, and the first fail sends the owner another lap."""
        gate, red = self._played(service, lap, added, ignored)
        return red or Continue(gate, self.stamp, service=service, lap=lap, added=added, ignored=ignored).because("the run is green")

    def _checked(self, service: str, lap: int, added: list[str], ignored: list[str]) -> tuple[CheckSaid, Continue[...] | Await[...] | None]:
        gate = CheckSaid(exit_code=0)
        after: list[ModuleCheck] = []
        for module in self._modules(service):
            gate = self.call(python_book_check, self.root, module, self.code_root)
            if gate.exit_code != 0:
                return gate, self._judged("check", module, gate, Lap(service, lap, added, ignored), self.check)
            after.append(read_check(module, gate.exit_code, gate.output, gate.noted))
        report = self._report(service)
        if not report.for_format:
            return gate, None
        declined = self.call(catch_up_declined, self.run_dir, service, ())
        left = [note for check in after for note in check.noted]
        kinds = kind_moves(report.noted, left, declined)
        _ = self.call(catch_up_move, self.run_dir, service, FormatMove(findings_after=sum(c.findings for c in after), notes_after=sum(c.notes for c in after), kinds=kinds))
        owed = owed_notes(report.noted, left, declined)
        return gate, self._owed(Lap(service, lap, added, ignored), owed) if owed else None

    def _played(self, service: str, lap: int, added: list[str], ignored: list[str]) -> tuple[BookGate, Continue[...] | Await[...] | None]:
        report = self._report(service)
        if report.verdict != STALE:
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

    def _owed(self, lap: Lap, owed: list[str]) -> Continue[...] | Await[...]:
        listing = note_listing(owed)
        said = f"The check passes, and these notes are neither stated nor declined:\n\n{listing}\n\nState each one from what the app's code shows, or decline it with one line, `<Element>: <reason>`, or `<kind>: <reason>` for a whole kind that is not about the format the book is moving onto."
        if lap.number >= MAX_LAPS:
            question = owed_question(lap.service, lap.number, listing)
            return Await(self.run_dir / RED_GATE, question, self.heard, question=question, gate_name=RED_GATE, service=lap.service, lap=lap.number, kept={"added": lap.added, "ignored": lap.ignored}).because(
                "notes are still owed after the last lap"
            )
        return Continue(said, self.write, service=lap.service, gate=said, lap=lap.number + 1, added=lap.added, ignored=lap.ignored).because("notes are still owed")

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
        waiting = self._commit_or_await(self._message(service), self._paths(service), lambda: self._replayed(service, lap, added, ignored), self.commit, service=service, lap=lap, added=added, ignored=ignored)
        if waiting:
            return waiting
        notes = self.call(catch_up_format_notes, self.run_dir, service, ())
        move = self._move(service) if report.for_format else None
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
            declined=self.call(catch_up_declined, self.run_dir, service, ()) if report.for_format else [],
        )
        _ = self.call(catch_up_record, self.run_dir, outcome)
        return Continue(outcome, self.books).because("the book is committed")

    def _move(self, service: str) -> FormatMove:
        return self.call(catch_up_move, self.run_dir, service, FormatMove())

    def _subject(self, service: str) -> str:
        return caught_up_book_commit_subject(service) if self._report(service).verdict == STALE else format_book_commit_subject(service)

    def _message(self, service: str) -> str:
        """The commit message of a book: its subject, and for a book moved onto the format a body with how far each kind of note went."""
        subject = self._subject(service)
        if not self._report(service).for_format:
            return subject
        lines = [kind.said for kind in self._move(service).kinds]
        body = "\n".join(textwrap.fill(line, BODY_WIDTH, subsequent_indent="  ") for line in lines)
        return f"{subject}\n\n{body}" if body else subject

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
        """End on the book's lines, which are logged one record each as the last thing the run says: one line per book, and for a book moved onto the format one line per kind of note."""
        outcomes = self.call(catch_up_outcomes, self.run_dir)
        lines = [line for outcome in outcomes for line in _lines(outcome)]
        for line in lines:
            self.logger.info("%s", line)
        return Done(CatchUpOutcome(books=outcomes, summary="\n".join(lines))).because("every book is judged")


def _lines(outcome: BookOutcome) -> list[str]:
    if outcome.move is None:
        return [_line(outcome)]
    owed = [f"{outcome.service}: owed to a scheduled whole play: {outcome.move.owed}"] if outcome.move.owed else []
    return [_moved_line(outcome, outcome.move), *(f"{outcome.service}: {kind.said}" for kind in outcome.move.kinds), *owed]


def _line(outcome: BookOutcome) -> str:
    if outcome.verdict == "current":
        return f"{outcome.service}: current"
    if outcome.verdict == "first-book":
        return f"{outcome.service}: first book, write it with python_book"
    moved = f"moved onto the format, {_count(outcome, 'applied')} changes applied, {_count(outcome, 'not applicable')} not applicable"
    if not outcome.app:
        return f"{outcome.service}: {moved}"
    line = _caught_up(outcome)
    return f"{line}, {moved}" if outcome.moved else line


def _caught_up(outcome: BookOutcome) -> str:
    line = f"{outcome.service}: caught up in {outcome.laps} laps, {len(outcome.elements)} elements changed, {len(outcome.added)} endpoints added"
    if outcome.ignored:
        line += f", {len(outcome.ignored)} files ignored: {', '.join(outcome.ignored)}"
    return line


def _moved_line(outcome: BookOutcome, move: FormatMove) -> str:
    checked = f"check {move.findings_before} findings to {move.findings_after}"
    if outcome.app:
        line = f"{_caught_up(outcome)}, {checked}"
    else:
        line = f"{outcome.service}: moved onto the format in {outcome.laps} laps, {checked}, "
        if move.exit_code is None:
            line += "played nothing"
        else:
            line += f"played {move.calls} calls and {move.journeys} journeys {'green' if move.exit_code == 0 else f'exit {move.exit_code}'}"
    if outcome.format:
        line += f", {_count(outcome, 'applied')} changes applied, {_count(outcome, 'not applicable')} not applicable"
    return line


def _count(outcome: BookOutcome, kind: str) -> int:
    return sum(1 for line in outcome.format if line.partition(" ")[2].startswith(kind))
