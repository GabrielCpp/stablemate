"""One command of a program, declared once and run through the declaration.

A service writes one subclass of `Command` per command a user can type. The
class body is the whole contract: the program, the argv template that turns the
declared arguments into words, the text it may read on stdin, and every exit it
may give with the shape of what it prints. `exchange` builds the argv from the
declaration, runs the program in a sandbox, and `send` refuses an exit the
declaration does not list or a stdout that does not fit the shape declared for
that exit. Everything else an endpoint has follows: journeys, cells, input
classes, twins, the witness and the run report.

State a command changes lives in the sandbox, a fresh directory per world made
from a `Seed`. The program runs with that directory as its working directory
and a clean environment the book declares. A `Files` read lists the paths the
book watches, each with the declared strings it holds, and the model's rows are
compared against it the way an HTTP book compares them against a list.

The sandbox path is `<sandbox>` wherever the program prints it and wherever the
book writes it, so a message the program builds from a path is the same text
in every world.
"""

from __future__ import annotations

import fnmatch
import json
import os
import shlex
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar, Mapping, cast

from ostler.book.arrange import Arrange
from ostler.book.errors import BookError
from ostler.book.http import Answer, Client, Endpoint, Field, List, Object, Shape, Str
from ostler.book.httpsurface import HttpSurface
from ostler.book.outcome import Done, Outcome
from ostler.book.status import Exited, Status

SANDBOX = "<sandbox>"

STDERR = Object("Stderr", message=Field(Str()))
"""The body of an exit that is read from stderr: the message the program gave."""


def Exit(code: int, shape: Shape | None, means: str, *, why: str = "") -> Answer:
    """One exit the command may give. A zero exit is a success and any other a
    refusal. `shape` describes stdout: an `Object` or `List` for JSON, `Lines`
    for text, `STDERR` to read the message from stderr, None for no output."""
    return Answer(Exited(code), shape, means, why=why)


@dataclass(frozen=True)
class Lines(List):
    """Text printed one line per item. A line that starts with one of `opaque`
    is one the model cannot predict and is left out of the comparison."""

    of: Shape = Str()
    opaque: tuple[str, ...] = ()

    def read(self, text: str) -> list[str]:
        return [line for line in text.splitlines() if not line.startswith(self.opaque)]

    def describe(self) -> str:
        shown = "lines of text"
        return f"{shown} (not compared: lines starting {', '.join(repr(p) for p in self.opaque)})" if self.opaque else shown


@dataclass(frozen=True)
class Flag:
    """`--name value` when the argument is set. A list argument repeats the flag
    once per item. `fmt` shapes the value, such as `dir={}` for `--param dir=x`."""

    flag: str
    arg: str
    fmt: str = "{}"

    def render(self, value: object) -> list[str]:
        if value is None:
            return []
        items = value if isinstance(value, (list, tuple)) else [value]
        return [word for item in cast("list[object]", items) for word in (self.flag, self.fmt.format(_text(item)))]

    def describe(self) -> str:
        return f"{self.flag} {self.fmt.format('{' + self.arg + '}')}"


@dataclass(frozen=True)
class Switch:
    """`--name` when the argument is true."""

    flag: str
    arg: str

    def render(self, value: object) -> list[str]:
        return [self.flag] if value is True else []

    def describe(self) -> str:
        return f"[{self.flag}]"


@dataclass(frozen=True)
class Positional:
    """The argument's value as a word of its own."""

    arg: str

    def render(self, value: object) -> list[str]:
        return [] if value is None else [_text(value)]

    def describe(self) -> str:
        return "{" + self.arg + "}"


Token = str | Flag | Switch | Positional


def _text(value: object) -> str:
    return str(value).lower() if isinstance(value, bool) else str(value)


class Command(Endpoint, abstract=True):
    """Subclass per command. `argv` is the template: a plain string is a word
    sent as it is, the other tokens read an argument by name. An instance is one
    call, `Install(fixture)`."""

    program: ClassVar[str] = ""
    argv: ClassVar[tuple[Token, ...]] = ()
    args: ClassVar[Object] = Object()
    stdin: ClassVar[str] = ""
    method: ClassVar[str] = "POST"
    typed_wire: ClassVar[bool] = True
    typed_away: ClassVar[tuple[str, ...]] = ("wrong type", "null")

    def __init_subclass__(cls, abstract: bool = False) -> None:
        if abstract:
            return
        name = cls.__name__
        if not cls.program:
            raise BookError(f"{name}: declares no program")
        named = {t.arg for t in cls.argv if not isinstance(t, str)}
        unknown = sorted(named - set(cls.args.fields))
        if unknown:
            raise BookError(f"{name}: the argv template reads {unknown}, which args does not declare")
        if cls.stdin and cls.stdin not in cls.args.fields:
            raise BookError(f"{name}: stdin reads {cls.stdin!r}, which args does not declare")
        unreached = sorted(set(cls.args.fields) - named - {cls.stdin})
        if unreached:
            raise BookError(f"{name}: {unreached} are declared but no token of the argv template sends them")
        cls.body = cls.args
        cls.path = "/" + "/".join([cls.program, *(t for t in cls.argv if isinstance(t, str))])
        super().__init_subclass__()

    @classmethod
    def route(cls) -> str:
        return " ".join([cls.program, *(t for t in cls.argv if isinstance(t, str))])

    @classmethod
    def read(cls, answer: Answer, raw: bytes) -> object:
        said = json.loads(raw)
        shape = answer.body
        if shape is None:
            return said["stdout"] or None
        if shape is STDERR:
            return {"message": said["stderr"].strip()}
        if isinstance(shape, Lines):
            return shape.read(said["stdout"])
        return json.loads(said["stdout"])

    def __init__(self, of: object = None, **kept: Any):
        super().__init__({} if of is None else of, **kept)

    def words(self, values: Mapping[str, Any]) -> list[str]:
        """The argv after the program, as the template builds it from the arguments."""
        out: list[str] = []
        for token in type(self).argv:
            out += [token] if isinstance(token, str) else token.render(values.get(token.arg))
        return out

    def exchange(self, client: Client) -> tuple[Status, bytes]:
        cls = type(self)
        run = getattr(client, "run", None)
        if run is None:
            raise BookError(f"{cls.__name__} is a command and the client cannot run one: reach it through a CommandSurface")
        values = cast("Mapping[str, Any]", self.payload(client.ids, client.resolve))
        piped = values.get(cls.stdin) if cls.stdin else None
        return run([cls.program, *self.words(values)], None if piped is None else str(piped))

    def __str__(self) -> str:
        cls = type(self)
        values = cast("Mapping[str, Any]", self.payload())
        return shlex.join([cls.program, *self.words(values)]) + (f" < {values[cls.stdin]!r}" if values.get(cls.stdin) else "")

    @classmethod
    def describe(cls) -> str:
        lines = [line for line in super().describe().splitlines() if line != "  auth: none"]
        runs = " ".join([cls.program, *(t if isinstance(t, str) else t.describe() for t in cls.argv)])
        lines.insert(2, f"  runs: {runs}")
        return "\n".join(lines)


@dataclass(frozen=True, init=False)
class Mark:
    """The files the watch reads under one glob, relative to the sandbox, and the
    strings it looks for in each of them. A row lists the strings the file holds,
    in the order declared here."""

    glob: str
    holds: tuple[str, ...] = ()

    def __init__(self, glob: str, *holds: str):
        object.__setattr__(self, "glob", glob)
        object.__setattr__(self, "holds", holds)


FILE = Object("File", path=Field(Str(), does="the path from the sandbox root"),
              holds=Field(List(Str()), does="the declared strings the file contains"))


class Files(Endpoint, abstract=True):
    """Subclass once per watch. The class body names the `marks`; the read lists
    every file under them, sorted by path."""

    marks: ClassVar[tuple[Mark, ...]] = ()

    def __init_subclass__(cls, abstract: bool = False) -> None:
        if abstract:
            return
        if not cls.marks:
            raise BookError(f"{cls.__name__}: declares no mark, so it watches nothing")
        cls.method = "GET"
        cls.path = "/files"
        if not cls.answers:
            cls.answers = (Exit(0, List(FILE), "every watched file with the strings it holds"),)
        super().__init_subclass__()

    @classmethod
    def route(cls) -> str:
        return "sandbox files"

    def exchange(self, client: Client) -> tuple[Status, bytes]:
        look = getattr(client, "look", None)
        if look is None:
            raise BookError(f"{type(self).__name__} reads a sandbox and the client has none: reach it through a CommandSurface")
        return look(type(self).marks)

    def __str__(self) -> str:
        return "read " + ", ".join(m.glob for m in type(self).marks)


@dataclass(frozen=True)
class Seed:
    """What a fresh sandbox holds: files by path (text may name `<sandbox>`), and
    whether it is a git repository with that content committed. `name` is the
    directory's own name, which programs read."""

    files: Mapping[str, str] = field(default_factory=dict)
    git: bool = False
    name: str = "sandbox"


class Sandbox:
    """One world's directory, made from a seed and removed with its parent."""

    def __init__(self, seed: Seed, environment: Mapping[str, str], inherit: tuple[str, ...]):
        self.parent = Path(tempfile.mkdtemp(prefix="book-")).resolve()
        self.root = self.parent / seed.name
        self.root.mkdir()
        self.env = {name: os.environ[name] for name in inherit if name in os.environ}
        self.env.update({name: self.written(value) for name, value in environment.items()})
        for path, text in seed.files.items():
            self.write(path, text)
        if seed.git:
            self.commit_all()

    def written(self, text: str) -> str:
        return text.replace(SANDBOX, str(self.root))

    def spoken(self, text: str) -> str:
        return text.replace(str(self.root), SANDBOX)

    def write(self, path: str, text: str) -> None:
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(self.written(text), encoding="utf-8")

    def append(self, path: str, text: str) -> None:
        with open(self.root / path, "a", encoding="utf-8") as kept:
            kept.write(self.written(text))

    def read(self, path: str) -> str:
        return (self.root / path).read_text(encoding="utf-8", errors="replace")

    def remove(self, path: str) -> None:
        target = self.root / path
        shutil.rmtree(target) if target.is_dir() else target.unlink()

    def commit_all(self) -> None:
        for words in (["init", "-q"], ["add", "-A"], ["-c", "user.name=book", "-c", "user.email=book@example.invalid",
                                                       "commit", "-q", "--allow-empty", "-m", "seed"]):
            self.run(["git", *words], None)

    def run(self, argv: list[str], stdin: str | None) -> tuple[int, str, str]:
        try:
            done = subprocess.run(argv, cwd=self.root, env=self.env, check=False, capture_output=True,
                                  input=None if stdin is None else stdin.encode(),
                                  stdin=subprocess.DEVNULL if stdin is None else None)
        except FileNotFoundError:
            raise BookError(f"{argv[0]} is not on PATH; a command is run through it") from None
        return done.returncode, done.stdout.decode(errors="replace"), done.stderr.decode(errors="replace")

    def look(self, marks: tuple[Mark, ...]) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        for path in sorted(p for p in self.root.rglob("*") if p.is_file() and ".git" not in p.relative_to(self.root).parts):
            name = path.relative_to(self.root).as_posix()
            matched = [m for m in marks if fnmatch.fnmatchcase(name, m.glob)]
            if not matched:
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            wanted = dict.fromkeys(s for m in matched for s in m.holds)
            rows.append({"path": name, "holds": [s for s in wanted if s in text]})
        return rows

    def discard(self) -> None:
        shutil.rmtree(self.parent, ignore_errors=True)


def said(body: object) -> str:
    """The message of a refusal: stderr's, or the lines the program printed."""
    if isinstance(body, dict):
        return str(cast("dict[str, object]", body).get("message", ""))
    if isinstance(body, list):
        return "\n".join(str(line) for line in cast("list[object]", body))
    return str(body or "")


class CommandClient(Client):
    """Where commands run: the sandbox of the current world."""

    def __init__(self) -> None:
        super().__init__("", message_of=said)
        self.sandbox: Sandbox | None = None

    def sandboxed(self) -> Sandbox:
        if self.sandbox is None:
            raise BookError("there is no sandbox yet: the surface makes one when it is reset")
        return self.sandbox

    def run(self, argv: list[str], stdin: str | None) -> tuple[Status, bytes]:
        sandbox = self.sandboxed()
        code, out, err = sandbox.run(argv, stdin)
        return Exited(code), json.dumps({"stdout": sandbox.spoken(out), "stderr": sandbox.spoken(err)}).encode()

    def look(self, marks: tuple[Mark, ...]) -> tuple[Status, bytes]:
        sandbox = self.sandboxed()
        rows = sandbox.look(marks)
        return Exited(0), json.dumps(rows).encode()


class Outside(Arrange[Any]):
    """Something that happens in the sandbox from outside the program: a person
    edits a file. `happen` does it; the action the class carries says what the
    model makes of it."""

    def happen(self, sandbox: Sandbox) -> None:
        raise NotImplementedError


class CommandSurface(HttpSurface):
    """Every step is a command run as declared in a sandbox, and after it the
    watch reads are taken. A book keeps only its seed and its environment."""

    name = "command"

    def __init__(self, seed: Seed, environment: Mapping[str, str] | None = None, inherit: tuple[str, ...] = ("PATH",)):
        self.command_client = CommandClient()
        super().__init__(self.command_client)
        self.seed = seed
        self.environment = dict(environment or {})
        self.inherit = inherit

    def restore(self) -> None:
        self.stop()
        self.command_client.sandbox = Sandbox(self.seed, self.environment, self.inherit)

    def stop(self) -> None:
        if self.command_client.sandbox is not None:
            self.command_client.sandbox.discard()
            self.command_client.sandbox = None

    def perform(self, step: Any) -> Outcome:
        if isinstance(step, Outside):
            step.happen(self.command_client.sandboxed())
            return Done(self.rows(), ())
        return super().perform(step)

    def express(self, request: Any, outcome: Done) -> tuple[object, ...]:
        return () if isinstance(request, Outside) else super().express(request, outcome)
