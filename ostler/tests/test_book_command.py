"""A command declared like an endpoint: its argv, its exits, the files it writes, its input classes and twins, and the farrier book that plays three of them."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, cast

import pytest

from ostler.book import (STDERR, Action, Actor, BookError, Collection, Command, CommandSurface, Create, Done, Enum, Exit,
                         Exited, Field, Files, Fixture, Flag, Lines, Mark, Object, Refusal, Rule, Sandbox, Seed, Select,
                         State, Str, Switch, Transaction, Undeclared, Unique, Watched)
from ostler.book.inputs import classes, twin_classes, vary
from ostler.book.runner import attempt
from ostler._vendor.stablemate_core import books

ROOT = Path(__file__).resolve().parents[2]
DAY = date(2026, 11, 4)

SCRIPT = """
import pathlib, sys
args = sys.argv[1:]
if "--fail" in args:
    sys.stderr.write("error: nope\\n")
    sys.exit(2)
if "--odd" in args:
    sys.exit(9)
name = args[args.index("--name") + 1] if "--name" in args else "world"
if "--write" in args:
    pathlib.Path("out.txt").write_text("hello " + name + "\\n")
if "--where" in args:
    print(pathlib.Path.cwd())
else:
    print("hello", name)
"""


@dataclass
class Hello(Fixture):
    name: str | None = None
    write: bool | None = None
    fail: bool | None = None
    tags: list[str] | None = None
    odd: bool | None = None
    where: bool | None = None


@dataclass
class Pick(Fixture):
    kind: str | None = None
    name: str | None = None


@dataclass
class Out:
    path: str
    holds: tuple[str, ...] = ()


class Tree(State):
    files = Collection(Out, Unique("path"))

    def rows(self) -> tuple[Out, ...]:
        return tuple(sorted(self.files, key=lambda f: f.path))


class Say(Action[Hello, Tree]):
    accept = Hello
    rules = (Rule[Hello, Tree]("error: nope", lambda a, s, by: a.fail is True, Exited(2)),)

    @staticmethod
    def reduce(a: Hello, s: Tree, by: Actor | None) -> Transaction:
        name = a.name or "world"
        made = (Create(s.files, Out("out.txt", (f"hello {name}",))),) if a.write and "out.txt" not in s.files else ()
        return Transaction(*made, says=(f"hello {name}",))


class SayNothingWritten(Say):
    @staticmethod
    def reduce(a: Hello, s: Tree, by: Actor | None) -> Transaction:
        return Transaction(says=(f"hello {a.name or 'world'}",))


class Choose(Action[Pick, Tree]):
    accept = Pick

    @staticmethod
    def reduce(a: Pick, s: Tree, by: Actor | None) -> Transaction:
        return Transaction(says=("chosen",))


class Ls(Action[object, Tree]):
    @staticmethod
    def reduce(a: object, s: Tree, by: Actor | None) -> Select[Out]:
        return Select(s.files, order=lambda f: f.path)


class Greet(Command):
    does = "Greet someone, and write the greeting down when asked."
    program = sys.executable
    argv = ("-c", SCRIPT, Flag("--name", "name"), Switch("--write", "write"), Switch("--fail", "fail"),
            Flag("--tag", "tags"), Switch("--odd", "odd"), Switch("--where", "where"))
    args = Object("Hello", name=Field(Str(), required=False), write=Field(Str(), required=False),
                  fail=Field(Str(), required=False), tags=Field(Str(), required=False), odd=Field(Str(), required=False),
                  where=Field(Str(), required=False))
    answers = (Exit(0, Lines(), "greeted"), Exit(2, STDERR, "refused"))
    carries = Say


class GreetAndWriteNothing(Greet):
    carries = SayNothingWritten


class Choosy(Command):
    does = "Take a kind and a name."
    program = sys.executable
    argv = ("-c", "print('chosen')", Flag("--kind", "kind"), Flag("--name", "name"))
    args = Object("Pick", kind=Field(Enum(("a", "b"))), name=Field(Str()))
    answers = (Exit(0, Lines(), "chosen"),)
    carries = Choose


class Look(Files):
    does = "List out.txt."
    marks = (Mark("out.txt", "hello Ann", "hello Bo"),)
    carries = Ls


def _surface() -> CommandSurface:
    surface = CommandSurface(Seed({"seed.txt": "kept"}))
    surface.follow((Look(),))
    surface.reset()
    return surface


@pytest.fixture
def surface() -> Any:
    made = _surface()
    yield made
    made.stop()


def test_argv_is_built_from_the_template():
    call = Greet(Hello(name="Ann", write=True, tags=["a", "b"], fail=False))
    values = call.payload()
    assert call.words(values) == ["-c", SCRIPT, "--name", "Ann", "--write", "--tag", "a", "--tag", "b"]


def test_a_template_word_that_reads_no_argument_is_a_mistake():
    with pytest.raises(BookError, match="reads"):
        class Wrong(Command):
            program = "x"
            argv = ("a", Flag("--b", "nope"))
            args = Object("Wrong", real=Field(Str()))
            answers = (Exit(0, None, "ok"),)


def test_an_argument_no_template_word_sends_is_a_mistake():
    with pytest.raises(BookError, match="no token"):
        class Unsent(Command):
            program = "x"
            argv = ("a",)
            args = Object("Unsent", real=Field(Str()))
            answers = (Exit(0, None, "ok"),)


def test_an_exit_the_model_expects_agrees(surface):
    taken = attempt(Greet(Hello(name="Ann")), Tree(DAY), surface)
    assert taken.ok, taken.note
    assert isinstance(taken.app, Done)
    assert taken.app.view == ("hello Ann",)


def test_a_refusal_is_the_exit_and_the_message_on_stderr(surface):
    taken = attempt(Greet(Hello(fail=True)), Tree(DAY), surface)
    assert taken.ok, taken.note
    assert taken.app == Refusal("error: nope", Exited(2))


def test_a_refusal_the_model_words_differently_is_a_failure(surface):
    class Mute(Say):
        rules = (Rule[Hello, Tree]("error: something else", lambda a, s, by: a.fail is True, Exited(2)),)

    class Quiet(Greet):
        carries = Mute

    taken = attempt(Quiet(Hello(fail=True)), Tree(DAY), surface)
    assert not taken.ok
    assert "error: something else" in taken.note


def test_an_exit_the_declaration_does_not_list_is_undeclared(surface):
    with pytest.raises(Undeclared, match="9"):
        surface.perform(Greet(Hello(odd=True)))


def test_the_sandbox_path_is_written_sandbox(surface):
    assert surface.send(Greet(Hello(where=True))).body == ["<sandbox>"]


def test_a_file_the_command_writes_is_judged_through_the_watch(surface):
    taken = attempt(Greet(Hello(name="Ann", write=True)), Tree(DAY), surface)
    assert taken.ok, taken.note
    assert [str(r) for r in taken.app_rows] == ["{path: out.txt, holds: ('hello Ann',)}"]


def test_a_file_the_model_does_not_expect_turns_the_step_red(surface):
    taken = attempt(GreetAndWriteNothing(Hello(name="Ann", write=True)), Tree(DAY), surface)
    assert not taken.ok
    assert "rows differ" in taken.note


def test_a_file_that_holds_other_text_turns_the_step_red(surface):
    taken = attempt(Greet(Hello(name="Cy", write=True)), Tree(DAY), surface)
    assert not taken.ok
    assert "rows differ" in taken.note


def test_an_input_class_is_derived_from_an_argument_and_a_typed_wire_drops_wrong_type_and_null():
    found = classes(Choosy(Pick(kind="a", name="Ann")), Tree(DAY), None)
    labels = {c.label for c in found}
    assert {"kind out of enum", "name blank", "kind missing", "name missing"} <= labels
    assert not {c.kind for c in found} & {"wrong type", "null"}


def test_an_argument_with_a_missing_value_leaves_its_flag_out():
    found = {c.label: c for c in classes(Choosy(Pick(kind="a", name="Ann")), Tree(DAY), None)}
    varied = cast(Choosy, vary(Choosy(Pick(kind="a", name="Ann")), found["name missing"]))
    assert varied.words(varied.payload()) == ["-c", "print('chosen')", "--kind", "a"]


def test_a_text_argument_has_twins():
    pairs = {(t.name, t.dimension) for t in twin_classes(Greet(Hello(name="Ann")), Tree(DAY))}
    assert ("name", "surrounding spaces") in pairs
    assert ("name", "case") in pairs


def test_a_seed_with_git_holds_a_committed_repository():
    sandbox = Sandbox(Seed({"a.txt": "x"}, git=True, name="kept"), {}, ("PATH",))
    try:
        code, out, _ = sandbox.run(["git", "log", "--format=%s"], None)
        assert (code, out.strip(), sandbox.root.name) == (0, "seed", "kept")
    finally:
        sandbox.discard()


def test_the_environment_the_book_declares_is_all_the_program_sees():
    sandbox = Sandbox(Seed(), {"HOME": "<sandbox>/home"}, ())
    try:
        code, out, _ = sandbox.run([sys.executable, "-c", "import os; print(sorted(os.environ)); print(os.environ['HOME'])"], None)
        assert code == 0
        assert out.splitlines()[1] == str(sandbox.root / "home")
        assert "PATH" not in out.splitlines()[0]
    finally:
        sandbox.discard()


def _own_book_home() -> Path | None:
    try:
        home = books.book_home(ROOT)
    except Exception:
        return None
    return home if (home / "services" / "stablemate" / "farrier").is_dir() else None


OWN_BOOK_HOME = _own_book_home()
own_book = pytest.mark.skipif(OWN_BOOK_HOME is None, reason="stablemate's own book is not in the artifacts folder of this machine")


def _book(arguments: list[str], extra: str = "") -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    if OWN_BOOK_HOME is not None:
        env["STABLEMATE_ARTIFACTS_DIR"] = str(OWN_BOOK_HOME)
    env["PATH"] = extra + str(Path(sys.executable).parent) + os.pathsep + env.get("PATH", "")
    return subprocess.run([sys.executable, "-m", "ostler.book", *arguments], cwd=ROOT, env=env, capture_output=True, text=True,
                          check=False)


@own_book
def test_the_farrier_book_checks_clean():
    done = _book(["check", "services.stablemate.farrier"])
    assert done.returncode == 0, done.stdout + done.stderr
    assert done.stdout.strip().endswith("check: 0 findings")


@own_book
@pytest.mark.parametrize("module", ["services.stablemate.groom.http", "services.stablemate.groom.web"])
def test_a_book_whose_fixtures_mint_names_checks_clean(module: str):
    done = _book(["check", module])
    assert done.returncode == 0, done.stdout + done.stderr
    assert "check: 0 findings" in done.stdout


@own_book
@pytest.mark.whole_run
def test_the_farrier_book_runs_green_against_the_current_farrier(tmp_path: Path):
    done = _book(["run", "services.stablemate.farrier", "--out", str(tmp_path / "out")])
    assert done.returncode == 0, done.stdout + done.stderr
    assert " pass, 0 known defects, 0 fail" in done.stdout
    assert "Every declared answer and field was seen." in done.stdout


@own_book
def test_a_starter_config_with_a_wrong_default_turns_the_farrier_book_red(tmp_path: Path):
    copy = tmp_path / "copy"
    shutil.copytree(ROOT / "farrier" / "farrier", copy / "farrier")
    init = copy / "farrier" / "init.py"
    init.write_text(init.read_text().replace("  claude: true\n", "  claude: false\n"))
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    wrapper = bin_dir / "farrier"
    wrapper.write_text(f'#!/bin/sh\nPYTHONPATH={copy} exec {sys.executable} -c "import sys; from farrier.cli import main; sys.exit(main())" "$@"\n')
    wrapper.chmod(0o755)
    done = _book(["run", "services.stablemate.farrier", "--journey", "SetUpARepo", "--partial", "--out", str(tmp_path / "out")],
                 extra=f"{bin_dir}{os.pathsep}")
    assert done.returncode == 1, done.stdout + done.stderr
    assert "at: farrier init --repo ." in done.stdout
    assert "rows differ" in done.stdout


class Row(Watched):
    marks = (Mark("*.txt", "b", "a"), Mark("out.*", "a", "c"))


def test_watched_declares_the_strings_in_mark_order_without_duplicates():
    assert Row.declared("out.txt") == ("b", "a", "c")
    assert Row.declared("other.md") == ()


def test_watched_holding_keeps_mark_order_and_the_subclass():
    row = Row.holding("out.txt", "c", "b")
    assert isinstance(row, Row)
    assert row == Row("out.txt", ("b", "c"))


def test_watched_row_prints_its_path_and_holds():
    assert str(Row("out.txt", ("b", "a"))) == "out.txt [b; a]"
