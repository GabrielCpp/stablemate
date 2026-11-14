"""One service's Python book. A book reached by a screen surface first gets a breadth pass, one skeleton screen per entry file the book names nowhere. Then one owner turn per lap writes `services/<service>/`, the run judges it with the book's own check and run, and a green book is committed."""
from __future__ import annotations

import logging
import sys
import time
from collections.abc import Callable
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field
from workhorse.pyflow import AgentTimeout, AgentTurnFailed, Await, Continue, Done, Transition, dry_run
from workhorse.runner.failure import OutputParseError
from workhorse_workflows.kit.schema import schema_block
from workhorse_workflows.kit.answer import answer_below
from workhorse_workflows.kit.tools import run_tool
from workhorse_workflows.okf_book.shared.blockers import Phase
from workhorse_workflows.okf_book.shared.blueprint import blueprint
from workhorse_workflows.okf_book.shared.book_commits import book_commit_subject
from workhorse_workflows.okf_book.shared.book_flow import BookFlow
from workhorse_workflows.okf_book.main.nodes.passes import BREADTH_DIR, Skeletons, pass_handed, record_pass
from workhorse_workflows.okf_book.shared.metrics import record_turn, turn_metric

WRITE_PROMPT = "main/prompts/write-python-book.md"
INVENTORY_PROMPT = "main/prompts/list-book-entries.md"
SKELETON_PROMPT = "main/prompts/write-screen-skeletons.md"
SCREEN_KINDS = frozenset({"web", "mobile"})
BATCH_SIZE = 8
UNNAMED_HEADING = "## Files no element names"
MAX_LAPS = 3
GATE_TAIL_LINES = 200
ANSWER_LIMIT_CHARS = 8000
RED_GATE = "python-book-red.md"
BLOCKED_GATE = "python-book-blocked.md"
ENVIRONMENT_GATE = "python-book-environment.md"
COULD_NOT_JUDGE = 3


class BookGate(BaseModel):
    """What one of the book's own commands said: its exit code and the tail of its output."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    exit_code: int
    output: str = ""


class MissingList(BookGate):
    """What the book's missing said, with the files no element names."""

    unnamed: tuple[str, ...] = ()


class BookEntries(BaseModel):
    """The entry files of the app that the book does not describe yet."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    entries: list[str] = Field(default_factory=list, description="Each entry file, spelled exactly as the list above spells it.")
    how: str = Field(default="", description="The file of the app that declares its pages.")


class PythonBookReply(BaseModel):
    """What the owner's turn says it did, or what stopped it."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    done: str = ""
    blocked: str = ""


class PythonBookOutcome(BaseModel):
    """The book the run committed, and how many laps it took."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    service: str
    laps: int


def book_module(service: str) -> str:
    return f"services.{service}"


def book_command(*verb: str) -> list[str]:
    return [sys.executable, "-m", "ostler.book", *verb]


def _green(_logger: logging.Logger, *_args: object) -> BookGate:
    return BookGate(exit_code=0, output="dry run")


def _tail(text: str) -> str:
    return "\n".join(text.splitlines()[-GATE_TAIL_LINES:])


def _unnamed(stdout: str) -> tuple[str, ...]:
    found: list[str] = []
    inside = False
    for line in stdout.splitlines():
        if line == UNNAMED_HEADING:
            inside = True
        elif line.startswith("## "):
            inside = False
        elif inside and line.startswith("- "):
            found.append(line[2:])
    return tuple(found)


def _missing_green(_logger: logging.Logger, *_args: object) -> MissingList:
    return MissingList(exit_code=0, output="dry run")


@blueprint.node(stub=_green)
def python_book_check(logger: logging.Logger, root: Path, module: str, app: Path) -> BookGate:
    """Run the check of one of the book's modules from the book root, with the source pointers read under the app's root, and keep the tail of what it printed."""
    done = run_tool(book_command("check", module, "--app", str(app)), cwd=root, logger=logger)
    return BookGate(exit_code=done.returncode, output=_tail(f"{done.stdout}\n{done.stderr}".strip()))


@blueprint.node(stub=_missing_green)
def python_book_missing(logger: logging.Logger, root: Path, module: str, app: Path, under: str) -> MissingList:
    """List the tracked source files of the app, under the folder the run names, that no element of one of the book's modules names, and keep the tail of what it printed."""
    where = ("--under", under) if under else ()
    done = run_tool(book_command("missing", module, "--app", str(app), *where), cwd=root, logger=logger)
    return MissingList(exit_code=done.returncode, output=_tail(f"{done.stdout}\n{done.stderr}".strip()), unnamed=_unnamed(done.stdout))


@blueprint.node(stub=_green)
def python_book_run(logger: logging.Logger, root: Path, module: str, out_dir: Path, stack_copy: str = "") -> BookGate:
    """Play one of the book's modules against the live app from the book root, on the stack copy the run names, and keep the tail of what it printed."""
    on_copy = ("--copy", stack_copy) if stack_copy else ()
    done = run_tool(book_command("run", module, "--out", str(out_dir), *on_copy), cwd=root, logger=logger)
    return BookGate(exit_code=done.returncode, output=_tail(f"{done.stdout}\n{done.stderr}".strip()))


def owner_chain(service: str) -> str:
    return f"pybook:{service}"


def finished_books(root: Path, service: str) -> list[str]:
    """The repo's other book packages, which the owner reads for the shape of each file."""
    patterns = ("services/*/service.py", "services/*/*/service.py")
    found = {path.relative_to(root).parts[1] for pattern in patterns for path in root.glob(pattern)}
    return [f"services/{name}" for name in sorted(found - {service})]


@dry_run(service="dry-run")
class WritePythonBook(BookFlow):
    """Surveys the entry files a screen-reached book names nowhere and has a skeleton screen written for each, eight to a turn. Then sends the book's owner until the book's check and run both pass and no source file is left unnamed, and commits the book's package. A missing list still red on a screen-reached book goes through the survey again before the owner."""

    service: str = ""
    kind: str = "cli"
    source_folder: str = ""
    stack_copy: str = ""

    @property
    def code_root(self) -> Path:
        return Path(self.repo_dir).resolve()

    @property
    def source_root(self) -> Path:
        return self.code_root / self.source_folder

    @property
    def package(self) -> str:
        return f"services/{self.service}"

    @property
    def kinds(self) -> tuple[str, ...]:
        return tuple(kind.strip() for kind in self.kind.split(",") if kind.strip())

    @property
    def modules(self) -> tuple[str, ...]:
        """One module per surface the service is reached by. A book with one surface is its package's module."""
        base = book_module(self.service)
        return (base,) if len(self.kinds) <= 1 else tuple(f"{base}.{kind}" for kind in self.kinds)

    @property
    def screen_modules(self) -> tuple[str, ...]:
        """The modules whose surface is a screen."""
        if len(self.kinds) <= 1:
            return self.modules if SCREEN_KINDS & set(self.kinds) else ()
        base = book_module(self.service)
        return tuple(f"{base}.{kind}" for kind in self.kinds if kind in SCREEN_KINDS)

    def start(self) -> Continue[...]:
        """Survey a book reached by a screen surface, and send the owner its first lap otherwise."""
        if self.screen_modules:
            return Continue(None, self.survey, gate="", lap=0).because("survey the screens")
        return Continue(None, self.write, gate="", lap=1).because("send the owner")

    def survey(self, gate: str, lap: int) -> Continue[...]:
        """List the entry files each screen module names nowhere. The first module with entries not yet handed to a skeleton turn gets them, and none left sends the owner."""
        for module in self.screen_modules:
            missing = self.call(python_book_missing, self.root, module, self.code_root, self.source_folder)
            if missing.exit_code != 1:
                continue
            entries = self._entries(module, missing.unnamed)
            if entries:
                return Continue(None, self.skeleton, module=module, entries=entries, gate=gate, lap=lap).because("write the skeletons")
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

    def skeleton(self, module: str, entries: list[str], gate: str, lap: int) -> Continue[...]:
        """One turn writes a skeleton screen for each of the next eight entry files. The batch is recorded as handed, and the files left go to another turn."""
        batch, rest = entries[:BATCH_SIZE], entries[BATCH_SIZE:]
        args = {**self._turn_args(module), "files": batch, "result_schema": schema_block(Skeletons)}
        reply = self._timed(
            SKELETON_PROMPT,
            Skeletons(),
            lambda: self.agent(SKELETON_PROMPT, returns=Skeletons, power="medium", timeout=float("inf"), args=args, cwd=self.root, add_dirs=self._add_dirs()),
        )
        sections = {"Written": reply.written, "Left": reply.left, "Odd for a user": reply.odd}
        self.call(record_pass, self.run_dir, BREADTH_DIR, batch, sections)
        if rest:
            return Continue(reply, self.skeleton, module=module, entries=rest, gate=gate, lap=lap).because("write the next batch")
        return Continue(reply, self.check, lap=lap).because("check the book")

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
        started = time.monotonic()
        reply = empty
        try:
            reply = ask()
        except (OutputParseError, AgentTurnFailed, AgentTimeout) as ended:
            self.logger.warning("the turn %s on %s ended without a reply: %s", prompt, self.service, ended)
            if session:
                self.reset_session(session)
        node = Path(prompt).stem
        record_turn(self.records_dir, turn_metric(Phase.WRITE, node, (self.service,), (time.monotonic() - started) / 60, self.turn_usage(node)))
        return reply

    def _add_dirs(self) -> list[Path] | None:
        return [self.code_root] if self.code_root != self.root else None

    def write(self, gate: str, lap: int) -> Continue[...] | Await[...]:
        """One owner turn writes the book's package until its check and run pass, opening on what the last gate printed. A turn that ends without a reply starts the next one fresh, and the gates judge what it left."""
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
            question = f"The owner of the {self.service} book stopped:\n\n{reply.blocked}\n\nAnswer here, and the owner reads your answer on its next turn."
            return Await(self.run_dir / BLOCKED_GATE, question, self.heard, question=question, gate_name=BLOCKED_GATE, lap=lap).because(
                "the owner is blocked"
            )
        return Continue(reply, self.check, lap=lap).because("check the book")

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
            "references": finished_books(self.root, self.service),
            "stack_copy": self.stack_copy,
            "gate": gate,
        }

    def heard(self, question: str, gate_name: str, lap: int) -> Continue[...]:
        """Hand the operator's answer to the owner's next turn."""
        text = (self.run_dir / gate_name).read_text(encoding="utf-8") if (self.run_dir / gate_name).is_file() else ""
        said = answer_below(text, question, ANSWER_LIMIT_CHARS)
        gate = f"{question}\n\nThe operator answered:\n\n{said}" if said else question
        return Continue(said, self.write, gate=gate, lap=lap).because("the operator answered")

    def check(self, lap: int) -> Continue[...] | Await[...]:
        """Run the check of each of the book's modules. A pass plays the book, and the first fail sends the owner another lap."""
        gate = BookGate(exit_code=0)
        for module in self.modules:
            gate = self.call(python_book_check, self.root, module, self.code_root)
            if gate.exit_code != 0:
                return self._judged("check", module, gate, lap, self.check)
        return Continue(gate, self.play, lap=lap).because("the check passes")

    def play(self, lap: int) -> Continue[...] | Await[...]:
        """Play each of the book's modules against the live app. A pass commits the book, and the first fail sends the owner another lap."""
        gate = BookGate(exit_code=0)
        for module in self.modules:
            gate = self.call(python_book_run, self.root, module, self.run_dir / "book-run" / module, self.stack_copy)
            if gate.exit_code != 0:
                return self._judged("run", module, gate, lap, self.play)
        return Continue(gate, self.account, lap=lap).because("the book plays green")

    def account(self, lap: int) -> Continue[...] | Await[...]:
        """List the app's source files each of the book's modules names nowhere. An empty list renders the book, and the first module with a file left sends a screen-reached book through the survey again, or any other book the owner, for another lap."""
        gate = BookGate(exit_code=0)
        for module in self.modules:
            gate = self.call(python_book_missing, self.root, module, self.code_root, self.source_folder)
            if gate.exit_code == 1 and self.screen_modules and lap < MAX_LAPS:
                return Continue(gate, self.survey, gate=self._said("missing", module, gate), lap=lap).because("survey the files left")
            if gate.exit_code != 0:
                return self._judged("missing", module, gate, lap, self.account)
        return Continue(gate, self.render, lap=lap).because("no source file is left unnamed")

    @staticmethod
    def _said(verb: str, module: str, gate: BookGate) -> str:
        return f"`python -m ostler.book {verb} {module}` exited {gate.exit_code}:\n\n{gate.output}"

    def _judged(self, verb: str, module: str, gate: BookGate, lap: int, retry: Callable[..., Transition]) -> Continue[...] | Await[...]:
        said = self._said(verb, module, gate)
        if gate.exit_code == COULD_NOT_JUDGE:
            question = f"The book's {verb} could not judge the {self.service} book, which is the environment's side:\n\n{said}\n\nFix the environment, then answer here to {verb} again."
            return Await(self.run_dir / ENVIRONMENT_GATE, question, retry, lap=lap).because("the book could not be judged")
        if lap >= MAX_LAPS:
            question = f"The {self.service} book is still red after {lap} laps:\n\n{said}\n\nAnswer here, and the owner takes one more lap with your answer."
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

    def commit(self, lap: int) -> Done | Await[...]:
        """Commit the book's package. A retry after the commit landed finds nothing to commit."""
        waiting = self._commit_or_await(book_commit_subject(self.service), (self.package,), self.commit, lap=lap)
        if waiting:
            return waiting
        return Done(PythonBookOutcome(service=self.service, laps=lap)).because("the book is committed")
