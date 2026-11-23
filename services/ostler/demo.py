"""The book of a small service, `demo`, that the sandbox holds so `ostler book` has a book to check, index, search, explain,
walk and run, and `ostler env` has a stack to list and render. The service prints the word hello, lists a notes file and
declares one web container."""

from __future__ import annotations

FILES: dict[str, str] = {
    "services/__init__.py": r'''''',
    "services/demo/__init__.py": r'''''',
    "services/demo/commands.py": r'''from __future__ import annotations

from ostler.book import Command, Exit, Files, Lines, Mark, Object

from .model.actions import ListFiles, Say
from .model.files import MARKS


class Echo(Command):
    does = "Print the word hello."
    program = "echo"
    argv = ("hello",)
    args = Object("EchoArgs")
    answers = (Exit(0, Lines(), "the word"),)
    carries = Say
    source = ("services/demo/surface.py",)


class Look(Files):
    does = "List the notes."
    marks = MARKS
    carries = ListFiles
    source = ("services/demo/surface.py",)


ALL = (Echo, Look)
''',
    "services/demo/decisions/say-hello.md": r'''story: none
date: 2026-11-17
elements: Echo

The demo book greets with the word hello and nothing else.
''',
    "services/demo/fixtures.py": r'''from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from ostler.book import Actor, Fixture


@dataclass
class EchoArgs(Fixture):
    @classmethod
    def examples(cls, state: Any, by: Actor | None) -> Iterable[EchoArgs]:
        return (EchoArgs(),)


__all__ = ["EchoArgs"]
''',
    "services/demo/journeys/__init__.py": r'''from .greet import Greet

ALL = (Greet,)
''',
    "services/demo/journeys/greet.py": r'''from __future__ import annotations

from datetime import date
from typing import Iterable

from ostler.book import Journey

from ..commands import Echo, Look
from ..fixtures import EchoArgs


class Greet(Journey):
    """A person says hello and looks at the notes."""

    alone = True

    def steps(self, today: date) -> Iterable[object]:
        return (Echo(EchoArgs()), Look())
''',
    "services/demo/model/__init__.py": r'''from .files import FileRecord
from .state import Repo

__all__ = ["FileRecord", "Repo"]
''',
    "services/demo/model/actions.py": r'''from __future__ import annotations

from ostler.book import Action, Actor, Select, Transaction

from ..fixtures import EchoArgs
from .files import FileRecord
from .state import Repo


class Say(Action[EchoArgs, Repo]):
    accept = EchoArgs

    @staticmethod
    def reduce(a: EchoArgs, s: Repo, by: Actor | None) -> Transaction:
        return Transaction(says=("hello",))


class ListFiles(Action[object, Repo]):
    @staticmethod
    def reduce(a: object, s: Repo, by: Actor | None) -> Select[FileRecord]:
        return Select(s.files, where=lambda f: bool(f.path), order=lambda f: f.path)
''',
    "services/demo/model/files.py": r'''from __future__ import annotations

from ostler.book import Mark, Watched

MARKS = (Mark("notes.txt", "hello"),)


class FileRecord(Watched):
    marks = MARKS
    source = ("services/demo/surface.py",)
''',
    "services/demo/model/lifecycle.py": r'''from __future__ import annotations

from datetime import date

from ostler.book import Axes, Scene

from ..commands import Echo, Look
from ..fixtures import EchoArgs
from .state import Repo, stage

MATRICES = (
    Axes[Repo]("notes", date(2026, 1, 1), (Scene("notes", "the notes file", lambda today: ()),),
               {"echo": lambda m: Echo(EchoArgs()), "look": lambda m: Look()}, stage, state_of=lambda m, _: stage(m)),
)
''',
    "services/demo/model/state.py": r'''from __future__ import annotations

from datetime import date
from typing import cast

from ostler.book import Collection, State, Unique

from .files import FileRecord


class Repo(State):
    files = Collection(FileRecord, Unique("path"))

    def __init__(self, today: date):
        super().__init__(today)
        notes = FileRecord.holding("notes.txt", "hello")
        self.files.items[notes.path] = notes

    def row(self, entity: object) -> FileRecord:
        return cast(FileRecord, entity)

    def rows(self) -> tuple[FileRecord, ...]:
        return tuple(sorted(self.files, key=lambda f: f.path))


def stage(model: Repo) -> str:
    return "notes"
''',
    "services/demo/ops/stack.yml": r'''services:
  web:
    about: a static page server
    address: demo-web
    port: 80
    host-port: 18080
    define: web.yml.j2
''',
    "services/demo/ops/web.yml.j2": r'''image: nginx:alpine
''',
    "services/demo/service.py": r'''"""demo, as ostler loads it."""

from __future__ import annotations

from ostler.book import Environment, Service, Stack

from .commands import ALL, Look
from .journeys import ALL as JOURNEYS
from .model import FileRecord, Repo
from .model.lifecycle import MATRICES
from .surface import DemoCli

service = Service[Repo](
    name="demo",
    environments={"local": Environment("local", {})},
    default_environment="local",
    new_model=Repo,
    surface=DemoCli,
    journeys=JOURNEYS,
    stack=lambda log_dir: Stack((), log_dir),
    endpoints=ALL,
    matrices=MATRICES,
    watch=(Look(),),
    records=(FileRecord,),
)
''',
    "services/demo/surface.py": r'''from __future__ import annotations

from ostler.book import CommandSurface, Environment, Seed

SEED = Seed({"notes.txt": "hello\n"}, name="demo")


class DemoCli(CommandSurface):
    def __init__(self, environment: Environment):
        super().__init__(SEED, {})
''',
}
