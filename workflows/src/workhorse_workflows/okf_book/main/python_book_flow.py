"""One service's Python book. A book reached by a screen surface whose package exists first gets a breadth pass, one skeleton screen per entry file the book names nowhere, and a reasons pass, the decisions for the screens no decision names. A screen-reached book with no package starts with the owner, whose first lap writes the package. A pass never drops work silently: a turn without a reply or a failed listing waits for the operator. Then one owner turn per lap writes the service's book folder, the run judges it with the book's own check and run, and a green book is committed."""
from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

from pydantic import BaseModel
from workhorse._vendor.stablemate_core import books
from workhorse.pyflow import Await, Continue, Done, Transition, dry_run
from workhorse_workflows.kit.schema import schema_block
from workhorse_workflows.kit.tools import run_tool
from workhorse_workflows.kit.book_files import BOOK_ENV
from workhorse_workflows.okf_book.shared.blueprint import blueprint
from workhorse_workflows.okf_book.shared.book_format import book_format_delta, mark_book_format
from workhorse_workflows.okf_book.shared.book_gates import BookGate, book_command, tail, python_book_check, python_book_missing, python_book_run, python_book_verified, run_flags
from workhorse_workflows.okf_book.shared.book_commits import book_commit_subject
from workhorse_workflows.okf_book.shared.book_flow import (
    BLOCKED_GATE,
    COULD_NOT_JUDGE,
    DECISIONS_GATE,
    ENVIRONMENT_GATE,
    FORMAT_GATE,
    MAX_LAPS,
    REASONS_GATE,
    RED_GATE,
    SKELETON_GATE,
    BookFlow,
    blocked_question,
    decisions_question,
    environment_question,
    format_question,
    no_reply_question,
    red_question,
)
from workhorse_workflows.okf_book.main.book_names import book_module, finished_books, owner_chain
from workhorse_workflows.okf_book.main.models import BookEntries, PythonBookOutcome, PythonBookReply
from workhorse_workflows.okf_book.main.nodes.passes import BREADTH_DIR, REASONS_DIR, Reasons, Skeletons, pass_handed, record_pass

WRITE_PROMPT = "main/prompts/write-python-book.md"
INVENTORY_PROMPT = "main/prompts/list-book-entries.md"
SKELETON_PROMPT = "main/prompts/write-screen-skeletons.md"
REASONS_PROMPT = "main/prompts/write-screen-reasons.md"
SCREEN_KINDS = frozenset({"web", "mobile"})
BATCH_SIZE = 8
REASONS_BATCH = 5
FIRST_BOOK_MARK = "first-book"
FORMAT_UNMARKED = "format-unmarked.txt"


class Unexplained(BookGate):
    """What the book's decisions listing said of one module: its exit code, the tail of its output and the screens no decision names."""

    module: str = ""
    screens: tuple[str, ...] = ()


def _none_unexplained(_logger: logging.Logger, *_args: object) -> Unexplained:
    return Unexplained(exit_code=0)


@blueprint.node(stub=_none_unexplained)
def python_book_unexplained(logger: logging.Logger, root: Path, module: str) -> Unexplained:
    """List the screens of one of the book's modules that no decision names, from the book root, with the exit code and output of the listing."""
    done = run_tool(book_command("decisions", module, "--unexplained", "--kind", "screen"), cwd=root, logger=logger, env=BOOK_ENV)
    screens = tuple(line.strip() for line in done.stdout.splitlines() if line.strip())
    return Unexplained(exit_code=done.returncode, output=tail(f"{done.stdout}\n{done.stderr}".strip()), module=module, screens=screens)


@dry_run(service="dry-run")
class WritePythonBook(BookFlow):
    """Surveys the entry files a screen-reached book names nowhere and has a skeleton screen written for each, eight to a turn. Then has the reasons written for each screen no decision names, five to a turn. A turn of either pass that ends without a reply, and a decisions listing that fails, each wait on an operator gate, and the answer sends the same batch again or lists again. Then sends the book's owner until the book's check and run both pass and no source file is left unnamed, stamps the book verified at the app's HEAD, and commits the book's package. A screen-reached book whose package exists first gets the breadth and reasons passes. One with no package starts with the owner, whose first lap writes the package. A missing list still red after a lap sends it through the survey."""

    service: str = ""
    kind: str = "cli"
    source_folder: str = ""
    stack_copy: str = ""
    format_history: str = ""

    @property
    def source_root(self) -> Path:
        return self.code_root / self.source_folder

    @property
    def package(self) -> str:
        return books.service_folder(self.code_root, self.service)

    @property
    def written(self) -> bool:
        """Whether the book's package holds a service, so its modules load. A package holding only the stack it is played on is not written yet."""
        return (self.root / self.package / "service.py").is_file()

    @property
    def kinds(self) -> tuple[str, ...]:
        return tuple(kind.strip() for kind in self.kind.split(",") if kind.strip())

    @property
    def modules(self) -> tuple[str, ...]:
        """One module per surface the service is reached by. A book with one surface is its package's module."""
        base = book_module(books.service_package(self.code_root), self.service)
        return (base,) if len(self.kinds) <= 1 else tuple(f"{base}.{kind}" for kind in self.kinds)

    @property
    def screen_modules(self) -> tuple[str, ...]:
        """The modules whose surface is a screen."""
        if len(self.kinds) <= 1:
            return self.modules if SCREEN_KINDS & set(self.kinds) else ()
        base = book_module(books.service_package(self.code_root), self.service)
        return tuple(f"{base}.{kind}" for kind in self.kinds if kind in SCREEN_KINDS)

    def start(self) -> Continue[...] | Await[...]:
        """Read what the book format changed for a book whose package exists, and wait for the operator where that cannot be read. Survey a book reached by a screen surface that already has a package, and send the owner its first lap otherwise."""
        if not self.written:
            self.run_dir.mkdir(parents=True, exist_ok=True)
            (self.run_dir / FIRST_BOOK_MARK).write_text("", encoding="utf-8")
        if self.written:
            delta = self.call(book_format_delta, self.root, self.package, self.format_history)
            if delta.unreadable:
                return Await(self.run_dir / FORMAT_GATE, format_question(self.service, delta.unreadable), self.start).because("the format history could not be read")
        if self.screen_modules and self.written:
            return Continue(None, self.survey, gate="", lap=0).because("survey the screens")
        return Continue(None, self.write, gate="", lap=1).because("send the owner")

    def survey(self, gate: str, lap: int) -> Continue[...] | Await[...]:
        """List the entry files each screen module names nowhere. The first module with entries not yet handed to a skeleton turn gets them, and none left goes to the reasons for any screen no decision names, or else sends the owner. A decisions listing that fails waits for the operator."""
        for module in self.screen_modules:
            missing = self.call(python_book_missing, self.root, module, self.code_root, self.source_folder)
            if missing.exit_code != 1:
                continue
            entries = self._entries(module, missing.unnamed)
            if entries:
                return Continue(None, self.skeleton, module=module, entries=entries, gate=gate, lap=lap).because("write the skeletons")
        found = self._to_explain()
        if isinstance(found, Unexplained):
            return Await(self.run_dir / DECISIONS_GATE, self._unlisted(found), self.survey, gate=gate, lap=lap).because("the decisions could not be listed")
        if found:
            return Continue(None, self.reasons, module=found[0], screens=found[1], lap=lap).because("write the reasons")
        return Continue(None, self.write, gate=self._noted(gate), lap=lap + 1).because("send the owner")

    def _entries(self, module: str, unnamed: tuple[str, ...]) -> list[str]:
        if not unnamed:
            return []
        args = {**self._turn_args(module), "unnamed": list(unnamed), "result_schema": schema_block(BookEntries)}
        reply = self._timed(
            INVENTORY_PROMPT,
            BookEntries(),
            lambda: self.agent(INVENTORY_PROMPT, returns=BookEntries, power="medium", timeout=float("inf"), args=args, cwd=self.root, add_dirs=self._add_dirs()),
        )
        found = reply.entries
        handed = set(self.call(pass_handed, self.run_dir, BREADTH_DIR))
        return [entry for entry in found if entry in unnamed and entry not in handed]

    def _noted(self, gate: str) -> str:
        if not (self.run_dir / BREADTH_DIR).is_dir():
            return gate
        note = f"The breadth pass left its notes on the entry files it tried under {self.run_dir / BREADTH_DIR}/."
        return f"{gate}\n\n{note}" if gate else note

    def skeleton(self, module: str, entries: list[str], gate: str, lap: int, answer: str = "") -> Continue[...] | Await[...]:
        """One turn writes a skeleton screen for each of the next eight entry files, opening on the operator's answer when there is one. A batch whose turn replied is recorded as handed, and the files left go to another turn. A turn that ends without a reply waits for the operator, whose answer sends the same batch again."""
        batch, rest = entries[:BATCH_SIZE], entries[BATCH_SIZE:]
        args = {**self._turn_args(module), "files": batch, "gate": answer, "result_schema": schema_block(Skeletons)}
        empty = Skeletons()
        reply = self._timed(
            SKELETON_PROMPT,
            empty,
            lambda: self.agent(SKELETON_PROMPT, returns=Skeletons, power="medium", timeout=float("inf"), args=args, cwd=self.root, add_dirs=self._add_dirs()),
        )
        if reply is empty:
            question = no_reply_question(self.service, "skeleton screens", batch)
            return Await(self.run_dir / SKELETON_GATE, question, self.skeleton_heard, question=question, module=module, entries=entries, gate=gate, lap=lap).because(
                "a skeleton turn ended without a reply"
            )
        sections = {"Written": reply.written, "Left": reply.left, "Odd for a user": reply.odd}
        self.call(record_pass, self.run_dir, BREADTH_DIR, batch, sections)
        if rest:
            return Continue(reply, self.skeleton, module=module, entries=rest, gate=gate, lap=lap).because("write the next batch")
        return self._reasons_or_check(reply, lap)

    def skeleton_heard(self, question: str, module: str, entries: list[str], gate: str, lap: int) -> Continue[...]:
        """Send the same skeleton batch to a new turn, with the operator's answer."""
        answer = self._owner_gate(question, SKELETON_GATE)
        return Continue(answer, self.skeleton, module=module, entries=entries, gate=gate, lap=lap, answer=answer).because("the operator answered")

    def _to_explain(self) -> tuple[str, list[str]] | Unexplained | None:
        handed = set(self.call(pass_handed, self.run_dir, REASONS_DIR))
        for module in self.screen_modules:
            listed = self.call(python_book_unexplained, self.root, module)
            if listed.exit_code != 0:
                return listed
            todo = [screen for screen in listed.screens if screen not in handed]
            if todo:
                return module, todo
        return None

    def _unlisted(self, listed: Unexplained) -> str:
        said = f"`python -m ostler.book decisions {listed.module} --unexplained --kind screen` exited {listed.exit_code}:\n\n{listed.output}"
        return decisions_question(self.service, said)

    def _reasons_or_check(self, result: object, lap: int) -> Continue[...] | Await[...]:
        found = self._to_explain()
        if isinstance(found, Unexplained):
            return Await(self.run_dir / DECISIONS_GATE, self._unlisted(found), self.explain, lap=lap).because("the decisions could not be listed")
        if found:
            return Continue(result, self.reasons, module=found[0], screens=found[1], lap=lap).because("write the reasons")
        return Continue(result, self.check, lap=lap).because("check the book")

    def explain(self, lap: int) -> Continue[...] | Await[...]:
        """List the screens no decision names again, after the operator fixed the listing. Some go to the reasons, and none left goes to the check."""
        return self._reasons_or_check(None, lap)

    def reasons(self, module: str, screens: list[str], lap: int, answer: str = "") -> Continue[...] | Await[...]:
        """One turn writes why each of the next five screens behaves as it does, opening on the operator's answer when there is one. A batch whose turn replied is recorded as handed, and the screens left go to another turn. A turn that ends without a reply waits for the operator, whose answer sends the same batch again."""
        batch, rest = screens[:REASONS_BATCH], screens[REASONS_BATCH:]
        args = {**self._turn_args(module), "module_dir": module.replace(".", "/"), "screens": batch, "gate": answer, "result_schema": schema_block(Reasons)}
        empty = Reasons()
        reply = self._timed(
            REASONS_PROMPT,
            empty,
            lambda: self.agent(REASONS_PROMPT, returns=Reasons, power="medium", timeout=float("inf"), args=args, cwd=self.root, add_dirs=self._add_dirs()),
        )
        if reply is empty:
            question = no_reply_question(self.service, "reasons", batch)
            return Await(self.run_dir / REASONS_GATE, question, self.reasons_heard, question=question, module=module, screens=screens, lap=lap).because(
                "a reasons turn ended without a reply"
            )
        self.call(record_pass, self.run_dir, REASONS_DIR, batch, {"Written": reply.written, "Open questions": reply.open})
        if rest:
            return Continue(reply, self.reasons, module=module, screens=rest, lap=lap).because("write the next batch")
        return self._reasons_or_check(reply, lap)

    def reasons_heard(self, question: str, module: str, screens: list[str], lap: int) -> Continue[...]:
        """Send the same reasons batch to a new turn, with the operator's answer."""
        answer = self._owner_gate(question, REASONS_GATE)
        return Continue(answer, self.reasons, module=module, screens=screens, lap=lap, answer=answer).because("the operator answered")

    def _turn_args(self, module: str) -> dict[str, object]:
        return {
            "service": self.service,
            "package": self.package,
            "module": module,
            "book_root": self.root.as_posix(),
            "source_root": self.source_root.as_posix(),
            "app_root": self.code_root.as_posix(),
        }

    def _timed[M: BaseModel](self, prompt: str, empty: M, ask: Callable[[], M], session: str | None = None) -> M:
        return self._timed_turn(self.service, prompt, empty, ask, session)

    def write(self, gate: str, lap: int) -> Continue[...] | Await[...]:
        """One owner turn writes the book's package until its check and a run of what it touched pass, opening on what the last gate printed. A turn that ends without a reply starts the next one fresh, and the gates judge what it left."""
        reply = self._timed(
            WRITE_PROMPT,
            PythonBookReply(),
            lambda: self.agent(
                WRITE_PROMPT,
                returns=PythonBookReply,
                power="high",
                timeout=float("inf"),
                args=self._prompt_args(gate),
                cwd=self.root,
                add_dirs=self._add_dirs(),
                session=owner_chain(self.service),
            ),
            session=owner_chain(self.service),
        )
        if reply.blocked:
            question = blocked_question(self.service, reply.blocked)
            return Await(self.run_dir / BLOCKED_GATE, question, self.heard, question=question, gate_name=BLOCKED_GATE, lap=lap).because(
                "the owner is blocked"
            )
        return Continue(reply, self.check, lap=lap).because("check the book")

    def _format(self) -> dict[str, object] | None:
        if not self.written:
            return None
        delta = self.call(book_format_delta, self.root, self.package, self.format_history)
        if not delta.behind:
            return None
        return {"commits": [{"short": commit.sha[:7], "subject": commit.subject} for commit in delta.commits], "diff": delta.diff}

    def _prompt_args(self, gate: str) -> dict[str, object]:
        return {
            "service": self.service,
            "kind": ", ".join(self.kinds),
            "kinds": list(self.kinds),
            "package": self.package,
            "modules": list(self.modules),
            "source_folder": self.source_folder,
            "book_root": self.root.as_posix(),
            "source_root": self.source_root.as_posix(),
            "app_root": self.code_root.as_posix(),
            "references": finished_books(self.root, books.service_package(self.code_root), self.service),
            "stack_copy": self.stack_copy,
            "format": self._format(),
            "gate": gate,
        }

    def heard(self, question: str, gate_name: str, lap: int) -> Continue[...]:
        """Hand the operator's answer to the owner's next turn."""
        gate = self._owner_gate(question, gate_name)
        return Continue(gate, self.write, gate=gate, lap=lap).because("the operator answered")

    def check(self, lap: int, seen: list[str] | None = None) -> Continue[...] | Await[...]:
        """Run the check of each of the book's modules. A pass sends the book through the repo's commit checks, and the first fail sends the owner another lap."""
        gate, red = self._checked(lap)
        return red or Continue(gate, self.checks, lap=lap, seen=seen or []).because("the check passes")

    def checks(self, lap: int, seen: list[str] | None = None) -> Continue[...] | Await[...]:
        """Meet the repo's commit checks over the book's package before it is played, so a refusal costs no replay. Each refusal goes to a fix turn and back to the check, and a pass plays the book."""
        waiting = self._checks_or_fix(book_commit_subject(self.service), self._paths(self.service), seen or [], self.check, self.checks, lap=lap)
        return waiting or Continue(None, self.play, lap=lap).because("the commit checks pass")

    def play(self, lap: int) -> Continue[...] | Await[...]:
        """Play each of the book's modules against the live app. A pass commits the book, and the first fail sends the owner another lap."""
        gate, red = self._played(lap)
        return red or Continue(gate, self.account, lap=lap).because("the book plays green")

    def account(self, lap: int) -> Continue[...] | Await[...]:
        """List the app's source files each of the book's modules names nowhere. An empty list stamps the book, and the first module with a file left sends a screen-reached book through the survey again, or any other book the owner, for another lap."""
        gate, red = self._accounted(lap)
        return red or Continue(gate, self.stamp, lap=lap).because("no source file is left unnamed")

    def _each(self, verb: str, retry: Callable[..., Transition], lap: int, ask: Callable[[str], BookGate]) -> tuple[BookGate, Continue[...] | Await[...] | None]:
        gate = BookGate(exit_code=0)
        for module in self.modules:
            gate = ask(module)
            if gate.exit_code != 0:
                return gate, self._judged(verb, module, gate, lap, retry)
        return gate, None

    def _checked(self, lap: int) -> tuple[BookGate, Continue[...] | Await[...] | None]:
        return self._each("check", self.check, lap, lambda module: self.call(python_book_check, self.root, module, self.code_root))

    def _played(self, lap: int) -> tuple[BookGate, Continue[...] | Await[...] | None]:
        return self._each("run", self.play, lap, lambda module: self.call(python_book_run, self.code_root, module, self.run_dir / "book-run" / module, run_flags(self.stack_copy, fresh=True)))

    def _accounted(self, lap: int) -> tuple[BookGate, Continue[...] | Await[...] | None]:
        return self._each("missing", self.account, lap, lambda module: self.call(python_book_missing, self.root, module, self.code_root, self.source_folder))

    def _replayed(self, lap: int) -> Continue[...] | Await[...] | None:
        return next(filter(None, (judge(lap)[1] for judge in (self._checked, self._played, self._accounted))), None)

    def stamp(self, lap: int) -> Continue[...] | Await[...]:
        """Record the app's HEAD as the commit each of the book's modules is verified at, so a later catch-up knows where the book was judged, and the commit of the writer's instructions it was written against. A module that refuses sends the owner another lap with what it printed. A format history that cannot be read waits for the operator."""
        gate, red = self._each("verified", self.stamp, lap, lambda module: self.call(python_book_verified, self.root, module, self.code_root))
        if red:
            return red
        delta = self.call(book_format_delta, self.root, self.package, self.format_history)
        if delta.unreadable and (self.run_dir / FIRST_BOOK_MARK).is_file():
            (self.run_dir / FORMAT_UNMARKED).write_text(delta.unreadable, encoding="utf-8")
        elif delta.unreadable:
            return Await(self.run_dir / FORMAT_GATE, format_question(self.service, delta.unreadable), self.stamp, lap=lap).because("the format history could not be read")
        elif delta.head:
            _ = self.call(mark_book_format, self.root, self.service, self.package, delta.head)
        return Continue(gate, self.render, lap=lap).because("the book is stamped")

    @staticmethod
    def _said(verb: str, module: str, gate: BookGate) -> str:
        return f"`python -m ostler.book {verb} {module}` exited {gate.exit_code}:\n\n{gate.output}"

    def _judged(self, verb: str, module: str, gate: BookGate, lap: int, retry: Callable[..., Transition]) -> Continue[...] | Await[...]:
        said = self._said(verb, module, gate)
        if verb == "missing" and gate.exit_code == 1 and self.screen_modules and lap < MAX_LAPS:
            return Continue(gate, self.survey, gate=said, lap=lap).because("survey the files left")
        if gate.exit_code == COULD_NOT_JUDGE:
            return Await(self.run_dir / ENVIRONMENT_GATE, environment_question(self.service, verb, said), retry, lap=lap).because("the book could not be judged")
        if lap >= MAX_LAPS:
            question = red_question(self.service, lap, said)
            return Await(self.run_dir / RED_GATE, question, self.heard, question=question, gate_name=RED_GATE, lap=lap).because(
                "the book is still red after the last lap"
            )
        return Continue(said, self.write, gate=said, lap=lap + 1).because("the book is red")

    def render(self, lap: int) -> Continue[...] | Await[...]:
        """Render the repo's agent files before the book is committed. A failed render waits for the operator."""
        waiting = self._render_agent_files_or_await(self.render, lap=lap)
        if waiting:
            return waiting
        return Continue(lap, self.commit, lap=lap).because("commit the book")

    def commit(self, lap: int) -> Done | Continue[...] | Await[...]:
        """Commit the book's package. A turn that fixed a refused commit and changed the book sends it through the check, the play and the list again first. A retry after the commit landed finds nothing to commit."""
        waiting = self._commit_or_await(book_commit_subject(self.service), self._paths(self.service), lambda: self._replayed(lap), self.commit, lap=lap)
        if waiting:
            return waiting
        unmarked = self.run_dir / FORMAT_UNMARKED
        why = unmarked.read_text(encoding="utf-8") if unmarked.is_file() else ""
        said = f"the format mark was not written, because the format history could not be read: {why}" if why else ""
        return Done(PythonBookOutcome(service=self.service, laps=lap, unmarked=said)).because("the book is committed")
