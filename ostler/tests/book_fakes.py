"""Doubles the book tests stand in for a surface."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Callable

from ostler.book import (Action, Answer, App, Arrange, Axes, CannotArrange, Collection, Create, Delete, Done, Endpoint, Environment, Event, Field, Journey,
                         Model, Object, Refusal, Rule, Scene, Service, Stack, State, Str, Unique, Unseen)
from ostler.book import cli


class Quiet:
    """A surface with nothing to start, stop or reset: a test overrides what it needs."""

    name = "fake"

    def start(self) -> None:
        return None

    def stop(self) -> None:
        return None

    def reset(self) -> None:
        return None

    def perform(self, step: Any) -> Done | Refusal:
        return Done()

    def rows(self) -> tuple[object, ...]:
        return ()


def no_stack(directory: str) -> Stack:
    return Stack((), directory)


class Counter(Model):
    """A model that keeps one number and adds one for every step `counts` accepts."""

    def __init__(self, today: date, n: int = 0) -> None:
        super().__init__(today)
        self.n = n

    def counts(self, request: object) -> bool:
        raise NotImplementedError

    def apply(self, request: object) -> tuple[object, ...] | None:
        if self.counts(request):
            self.n += 1
        return None

    def rows(self) -> tuple[object, ...]:
        return (self.n,)

    def copy(self) -> Counter:
        return type(self)(self.today, self.n)


class Plain(Model):
    def apply(self, request: object) -> None:
        return None

    def rows(self) -> tuple[object, ...]:
        return ()

    def copy(self) -> Plain:
        return Plain(self.today)


SHELF_DAY = date(2026, 11, 19)


@dataclass
class Item:
    id: str


class Shelf(State):
    items = Collection(Item, Unique("id"))

    def rows(self) -> tuple[object, ...]:
        return tuple(i.id for i in self.items)


class Stocked(Event):
    """An item was put on the shelf."""

    name = "shelf.stocked"
    source = "zeta.shelf"
    detail = Object(item=Field(Str()))


class Haunted(Event):
    """The shelf was haunted."""

    name = "shelf.haunted"
    source = "zeta.shelf"
    detail = Object(item=Field(Str()))


TAKEN = Rule[str, Shelf]("already on the shelf", lambda a, s, by: a in [i.id for i in s.items])
MISSING = Rule[str, Shelf]("not on the shelf", lambda a, s, by: a not in [i.id for i in s.items])


class Shelver(Action[str, Shelf]):
    pass


class Put(Shelver):
    rules = (TAKEN,)
    emits = (Stocked,)

    @staticmethod
    def reduce(a: str, s: Shelf, by: Any) -> Create:
        return Create(Shelf.items, Item(a))


class Restock(Action[str, Shelf]):
    rules = (TAKEN,)

    @staticmethod
    def reduce(a: str, s: Shelf, by: Any) -> Create:
        return Create(Shelf.items, Item(a))


class Remove(Action[str, Shelf]):
    rules = (MISSING,)

    @staticmethod
    def reduce(a: str, s: Shelf, by: Any) -> Delete:
        return Delete(Shelf.items, a)


class Haunt(Action[str, Shelf]):
    emits = (Haunted,)

    @staticmethod
    def reduce(a: str, s: Shelf, by: Any) -> Create:
        return Create(Shelf.items, Item(a))


class Sweep(Action[str, Shelf]):
    pass


class Step:
    by = None
    carries: Any = None

    def __init__(self, of: str) -> None:
        self.of = of

    def input(self) -> str:
        return self.of

    def __str__(self) -> str:
        return f"{type(self).__name__} {self.of}"


class Puts(Step):
    carries = Put


class Restocks(Step):
    carries = Restock


class Removes(Step):
    carries = Remove


class Arrives(Arrange[str]):
    does = "An item arrives."
    carries = Put


class Ghost(Arrange[str]):
    does = "An item appears by itself."
    carries = Haunt


class Echo(Quiet):
    """A surface that keeps a shelf and answers as the model does. A step of a kind in `cannot` cannot be arranged."""

    name = "echo"

    def __init__(self, cannot: tuple[type, ...] = ()) -> None:
        self.cannot = cannot
        self.shelf = Shelf(SHELF_DAY)

    def reset(self) -> None:
        self.shelf = Shelf(SHELF_DAY)

    def perform(self, step: Any) -> Any:
        if isinstance(step, self.cannot):
            raise CannotArrange(f"no way to arrange {type(step).__name__} here")
        return self.shelf.perform(step)

    def rows(self) -> tuple[object, ...]:
        return self.shelf.rows()


class Stocking(Journey):
    """An item arrives and is put again."""

    def steps(self, today: date) -> tuple[object, ...]:
        return (Arrives("a"), Puts("a"), Restocks("b"), Restocks("b"))


class Haunting(Journey):
    """An item appears by itself."""

    def steps(self, today: date) -> tuple[object, ...]:
        return (Ghost("x"),)


def shelf_matrices() -> tuple[Axes[Shelf], ...]:
    puts: dict[str, Callable[[Shelf], object]] = {"put": lambda m: Puts("z")}
    shelf = Axes[Shelf]("shelf", SHELF_DAY, (Scene("empty", "nothing on it", lambda today: ()),
                                             Scene("stocked", "one item on it", lambda today: (Puts("a"),))),
                        puts, lambda m: "empty")
    closet = Axes[Shelf]("closet", SHELF_DAY, (Scene("never", "no action is built for it", lambda today: ()),), {}, lambda m: "never")
    return shelf, closet


def shelf_book(journeys: tuple[type[Journey], ...] = (Stocking,), matrices: tuple[Axes[Shelf], ...] = (), delivery: Any = None,
               outside: tuple[type[Arrange[Any]], ...] = (Arrives, Ghost), cannot: tuple[type, ...] = (),
               unseen: tuple[Unseen, ...] = ()) -> Service[Shelf]:
    return Service(name="shelf", new_model=Shelf, surface=lambda environment: Echo(cannot), journeys=journeys, stack=no_stack,
                   matrices=matrices, outside=outside, environments={"local": Environment("local", {}, delivery=delivery)},
                   default_environment="local", unseen=unseen)


def run_shelf(monkeypatch: Any, service: Service[Any], out: Path, capsys: Any, *flags: str) -> tuple[int, str]:
    """The `run` command on a book, with its check and its loading stood in, and what it printed."""
    monkeypatch.setattr(cli, "load", lambda name: service)
    monkeypatch.setattr(cli, "broken", lambda found, module: False)
    monkeypatch.setattr(cli, "register_path", lambda module: str(out / "register.txt"))
    code = cli.main(["run", __name__, "--no-stack", "--out", str(out), *flags])
    return code, capsys.readouterr().out


def affected_report(monkeypatch: Any, tmp_path: Path, service: Any, capsys: Any, *arguments: str) -> tuple[int, dict[str, Any], str]:
    """The `affected` command on a book with its loading stood in, the report it wrote (empty when none) and what it printed."""
    monkeypatch.setattr(cli, "load", lambda name: service)
    monkeypatch.setattr(cli, "_package_dir", lambda args: str(tmp_path))
    out = tmp_path / "out"
    code = cli.main(["affected", "services.shelf", "--out", str(out), *arguments])
    report = out / "shelf-affected.json"
    return code, json.loads(report.read_text()) if report.exists() else {}, capsys.readouterr().out


def book_command(monkeypatch: Any, tmp_path: Path, service: Any, capsys: Any, *arguments: str) -> tuple[int, str]:
    """A command of the book CLI with its loading stood in and its package folder set to `tmp_path`, and what it printed."""
    monkeypatch.setattr(cli, "load", lambda name: service)
    monkeypatch.setattr(cli, "_package_dir", lambda args: str(tmp_path))
    code = cli.main([*arguments])
    return code, capsys.readouterr().out


def story_affected(root: Path, tmp_path: Path, capsys: Any, story: str = "ACME-1") -> tuple[int, dict[str, Any], list[str]]:
    """The `affected` command of the api book of the copied todo repository under a story, its report and the lines it printed."""
    out = tmp_path / "out"
    code = cli.main(["affected", "services.api", "--app", str(root), "--story", story, "--out", str(out)])
    return code, json.loads((out / "api-affected.json").read_text()), capsys.readouterr().out.splitlines()


def app_repo(tmp_path: Path, files: dict[str, str]) -> tuple[Path, str]:
    """A code repository under `tmp_path` holding the files, and its base commit."""
    return tmp_path / "app", code_repo(tmp_path / "app", files)


def git(folder: Path, *arguments: str) -> str:
    """What git prints for `arguments` run in `folder`, as a committer with a fixed name."""
    done = subprocess.run(["git", "-C", str(folder), "-c", "user.name=t", "-c", "user.email=t@example.com", *arguments],
                          check=True, capture_output=True, text=True)
    return done.stdout


def commit_files(folder: Path, files: dict[str, str], message: str = "change") -> str:
    """Writes the files, commits them and gives the short commit."""
    for name, text in files.items():
        (folder / name).parent.mkdir(parents=True, exist_ok=True)
        (folder / name).write_text(text)
    git(folder, "add", *files)
    git(folder, "commit", "--quiet", "-m", message)
    return git(folder, "rev-parse", "--short", "HEAD").strip()


def code_repo(folder: Path, files: dict[str, str]) -> str:
    """A new git repository holding the files in one commit, and that commit."""
    folder.mkdir(parents=True)
    git(folder, "init", "--quiet")
    return commit_files(folder, files, "base")


def committed_book(root: Path) -> str:
    """The copied todo book as the base commit of a new repository, and that commit."""
    (root / ".gitignore").write_text("__pycache__/\nnode_modules/\n")
    git(root, "init", "--quiet")
    git(root, "add", ".")
    git(root, "commit", "--quiet", "-m", "base")
    return git(root, "rev-parse", "--short", "HEAD").strip()


class Drawer:
    """A record of the shelf book."""


class PutItem(Endpoint):
    method = "POST"
    path = "/shelf/{id}"
    params = Object(id=Field(Str()))
    answers = (Answer(200, None, "ok"),)
    carries = Put
    does = "Puts an item on the shelf."


class RestockItem(Endpoint):
    method = "PUT"
    path = "/shelf/{id}"
    params = Object(id=Field(Str()))
    answers = (Answer(200, None, "ok"),)
    carries = Restock
    does = "Puts an item on the shelf again."


class RemoveItem(Endpoint):
    method = "DELETE"
    path = "/shelf/{id}"
    params = Object(id=Field(Str()))
    answers = (Answer(200, None, "ok"),)
    carries = Remove
    does = "Takes an item off the shelf."


class Shelving(Journey):
    """An item arrives and another is put."""

    def steps(self, today: date) -> tuple[object, ...]:
        return (Arrives("a"), PutItem("b"))


class Clearing(Journey):
    """An item is put and taken off."""

    def steps(self, today: date) -> tuple[object, ...]:
        return (PutItem("c"), RemoveItem("c"))


def sourced_book(sources: dict[str, tuple[str, ...]], ignore: tuple[str, ...] = ("*_test.go",)) -> Service[Shelf]:
    """The shelf book with calls, outside happenings, actions and a record, each naming the code `sources` gives for its name."""

    def named(cls: type, **extra: Any) -> Any:
        return type(cls.__name__, (cls,), {"source": sources.get(cls.__name__, ()), "__module__": cls.__module__, **extra})

    put, restock, remove, haunt = (named(a) for a in (Put, Restock, Remove, Haunt))
    book = shelf_book((Shelving, Clearing, Haunting), outside=(named(Arrives, carries=put), named(Ghost, carries=haunt)))
    book.endpoints = (named(PutItem, carries=put), named(RestockItem, carries=restock), named(RemoveItem, carries=remove))
    book.records = (named(Drawer),)
    book.app = App(roots=(".",), verified="VERIFIED", ignore=ignore)
    return book
