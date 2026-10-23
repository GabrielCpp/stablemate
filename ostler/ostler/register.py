"""The Register — one ``record.md`` per proposed improvement, shelved by repository, area and id in the artifacts dir."""

from __future__ import annotations

import re
import subprocess
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import pydantic

from ostler import crud, ids, markdown, path as path_mod
from ostler._vendor.stablemate_core import config as core_config
from ostler.model import Graph
from ostler.result import Result

RECORD_FILE = "record.md"
_SEGMENT = re.compile(r"[a-z0-9][a-z0-9-]*")
ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
_FRONTMATTER = re.compile(r"---\n.*?\n---\n", re.DOTALL)

FiledBy = Literal["coder", "qa", "qa-deferred", "person", "survey", "parity"]
Status = Literal["open", "done", "dropped", "promoted"]


class Record(pydantic.BaseModel):
    """One proposed improvement as stored: who filed it, where it sits, what fix it calls for, and how it ended."""

    model_config = pydantic.ConfigDict(frozen=True)

    id: str
    repo: str
    area: str
    pattern: str
    symbols: list[str] = []
    filed_by: FiledBy
    source_story: str = ""
    summary: str
    status: Status = "open"
    decision: str = ""
    reason: str = ""
    body: str = ""

    @pydantic.field_validator("id")
    @classmethod
    def _id_is_one_path_segment(cls, value: str) -> str:
        """An id names a folder, so it is one non-empty path-safe segment."""
        if not ID_PATTERN.fullmatch(value):
            raise ValueError(f"id {value!r} must be one path-safe segment")
        return value

    @pydantic.field_validator("repo", "area")
    @classmethod
    def _segment_is_lowercase_kebab(cls, value: str, info: pydantic.ValidationInfo) -> str:
        """A repository and an area are each one lowercase kebab segment, and never empty."""
        if not _SEGMENT.fullmatch(value):
            raise ValueError(f"{info.field_name} {value!r} must be one lowercase kebab segment")
        return value

    @pydantic.field_validator("summary")
    @classmethod
    def _summary_is_one_line(cls, value: str) -> str:
        """The summary is the listing line: non-empty and on one line."""
        if not value.strip() or "\n" in value or "\r" in value:
            raise ValueError("summary must be one non-empty line")
        return value.strip()

    @pydantic.field_validator("body")
    @classmethod
    def _body_has_no_edge_newlines(cls, value: str) -> str:
        """The body is stored between blank lines, so its edge newlines are not part of it."""
        return value.strip("\n")

    def folder(self, shelf: Path) -> Path:
        """Where this record lives under *shelf*: ``<repo>/<area>/<id>``."""
        return shelf / self.repo / self.area / self.id

    def render(self) -> str:
        """The text of ``record.md``: frontmatter in field order, then the body."""
        front = self.model_dump(exclude={"body"})
        text = f"---\n{crud.dump_frontmatter(front)}---\n"
        return f"{text}\n{self.body}\n" if self.body else text

    @classmethod
    def parse(cls, text: str) -> Record:
        """The record in *text*; raises ``ValueError`` (or its pydantic subclass) when it is not one."""
        doc = markdown.split(text)
        if not doc.frontmatter:
            raise ValueError("record.md has no frontmatter")
        return cls.model_validate({**doc.frontmatter, "body": doc.body})

    @classmethod
    def read(cls, path: Path) -> Record:
        """The record stored in the file at *path*."""
        return cls.parse(path.read_text(encoding="utf-8"))


@dataclass(frozen=True, slots=True)
class RegisterRead:
    """Every record that parsed, sorted by repo, area and id, and the ``record.md`` files that did not."""

    records: tuple[Record, ...]
    unreadable: tuple[Path, ...]


@dataclass(frozen=True, slots=True)
class Filing:
    """The outcome of filing one record: the record and its file when it was written."""

    ok: bool
    message: str
    record: Record | None = None
    path: Path | None = None


def _record_files(graph: Graph) -> list[Path]:
    """Every ``record.md`` on the shelf, in path order."""
    shelf = path_mod.register_root(graph)
    return sorted(shelf.glob(f"*/*/*/{RECORD_FILE}")) if shelf.is_dir() else []


def records(graph: Graph) -> RegisterRead:
    """Read the whole shelf; a record that fails to parse is reported, never listed."""
    good: list[Record] = []
    bad: list[Path] = []
    for file in _record_files(graph):
        try:
            good.append(Record.read(file))
        except (ValueError, OSError):
            bad.append(file)
    good.sort(key=lambda r: (r.repo, r.area, r.id))
    return RegisterRead(tuple(good), tuple(bad))


def listing(items: Iterable[Record]) -> list[str]:
    """One line per record, tab-separated: id, repo, area, status, pattern, summary."""
    return [
        "\t".join((r.id, r.repo, r.area, r.status, r.pattern, r.summary)) for r in items
    ]


def locate(graph: Graph, token: str) -> Path | None:
    """The folder of the record named by a full id or a short handle, or None."""
    wanted = ids.resolve(graph, token)
    for file in _record_files(graph):
        if file.parent.name == wanted:
            return file.parent
    return None


def open_records(graph: Graph, repo: str) -> list[Record]:
    """The open records of *repo*."""
    return [r for r in records(graph).records if r.repo == repo and r.status == "open"]


def write(graph: Graph, record: Record, *, own: frozenset[str] = frozenset()) -> Result:
    """Shelve *record* in the artifacts repo; refuse an id the workspace already uses, except the ids in *own*."""
    shelf = path_mod.register_root(graph)
    folder = record.folder(shelf)
    if (record.id in ids.known(graph) and record.id not in own) or folder.exists():
        return Result(False, f"record id '{record.id}' is already taken")
    core_config.ensure_artifacts_repo()
    folder.mkdir(parents=True)
    target = folder / RECORD_FILE
    target.write_text(record.render(), encoding="utf-8")
    return Result(True, f"filed record '{record.id}'", [target], entity_id=record.id)


def file_record(
    graph: Graph,
    *,
    repo: str,
    area: str,
    pattern: str,
    summary: str,
    filed_by: FiledBy,
    symbols: Iterable[str] = (),
    source_story: str = "",
    body: str = "",
    status: Status = "open",
    record_id: str = "",
    prefix: str | None = None,
) -> Filing:
    """Build a record, minting its id when none is given, and shelve it."""
    try:
        record = Record(
            id=record_id or ids.allocate(graph, prefix),
            repo=repo, area=area, pattern=pattern, symbols=list(symbols),
            filed_by=filed_by, source_story=source_story, summary=summary, body=body, status=status,
        )
    except pydantic.ValidationError as exc:
        first = exc.errors()[0]
        return Filing(False, f"invalid record: {'.'.join(map(str, first['loc']))}: {first['msg']}")
    result = write(graph, record)
    if not result.ok:
        return Filing(False, result.message)
    return Filing(True, result.message, record, result.paths[0])


def filing_result(filing: Filing) -> Result:
    """A filing as the Result every ostler writer returns."""
    paths = [filing.path] if filing.path else []
    return Result(filing.ok, filing.message, paths, entity_id=filing.record.id if filing.record else "")


def close(graph: Graph, token: str, status: Status, reason: str) -> Result:
    """End a record: rewrite only its ``status`` and ``reason``; closing at the status it already has is a no-op that writes nothing."""
    if status == "open":
        return Result(False, "a record is closed as done, dropped or promoted, never as open")
    folder = locate(graph, token)
    if folder is None:
        return Result(False, f"no record '{token}'")
    target = folder / RECORD_FILE
    text = target.read_text(encoding="utf-8")
    try:
        current = Record.parse(text)
    except ValueError as exc:
        return Result(False, f"record '{folder.name}' cannot be read: {exc}")
    if current.status != "open":
        if current.status == status:
            return Result(True, f"record '{current.id}' is already {status}", [], entity_id=current.id)
        return Result(False, f"record '{current.id}' is already {current.status}, not {status}")
    head = _FRONTMATTER.match(text)
    front = markdown.split(text).frontmatter
    if head is None or front is None:
        return Result(False, f"record '{folder.name}' has no frontmatter")
    front = {**front, "status": status, "reason": reason.strip()}
    target.write_text(f"---\n{crud.dump_frontmatter(front)}---\n{text[head.end():]}", encoding="utf-8")
    return Result(True, f"closed record '{current.id}' as {status}", [target], entity_id=current.id)


def close_and_commit(graph: Graph, token: str, status: Status, reason: str) -> Result:
    """:func:`close` a record and commit it in the artifacts repo; a close whose commit fails leaves the old text."""
    folder = locate(graph, token)
    before = (folder / RECORD_FILE).read_text(encoding="utf-8") if folder else ""
    result = close(graph, token, status, reason)
    if not result.ok or not result.paths:
        return result
    target = result.paths[0]
    try:
        commit(graph, [target], f"chore({Record.read(target).repo}): close {result.entity_id} as {status}")
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
        target.write_text(before, encoding="utf-8")
        return Result(False, f"record '{result.entity_id}' was not closed: the artifacts commit failed: {exc}")
    return result


def commit(graph: Graph, paths: Iterable[Path], message: str) -> bool:
    """Commit exactly *paths* in the artifacts repo, hooks off; False when there was nothing new to commit."""
    root = path_mod.register_root(graph).parent
    rels = [str(Path(p).relative_to(root)) for p in paths]
    if not rels or not (root / ".git").exists():
        return False
    git = ["git", "-C", str(root)]
    subprocess.run([*git, "add", "--", *rels], check=True, capture_output=True, timeout=60)
    if subprocess.run([*git, "diff", "--cached", "--quiet", "--", *rels], check=False, capture_output=True, timeout=60).returncode == 0:
        return False
    try:
        subprocess.run(
            [*git, "-c", "core.hooksPath=/dev/null", "commit", "--no-verify", "-m", message, "--only", "--", *rels],
            check=True, capture_output=True, timeout=60,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        subprocess.run([*git, "reset", "--quiet", "--", *rels], check=False, capture_output=True, timeout=60)
        raise
    return True


def file_person(
    graph: Graph,
    *,
    summary: str,
    repo: str,
    area: str,
    pattern: str = "untriaged",
    symbols: Iterable[str] = (),
    body: str = "",
    record_id: str = "",
    prefix: str | None = None,
) -> Filing:
    """File a record a person wrote and commit it in the artifacts repo; a record whose commit fails is taken off the shelf."""
    filing = file_record(
        graph, repo=repo, area=area, pattern=pattern, summary=summary, filed_by="person",
        symbols=symbols, body=body, record_id=record_id, prefix=prefix,
    )
    if filing.record is None or filing.path is None:
        return filing
    try:
        commit(graph, [filing.path], f"chore({filing.record.repo}): file {filing.record.id}")
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
        discard(filing.path)
        return Filing(False, f"record '{filing.record.id}' was not filed: the artifacts commit failed: {exc}")
    return filing


def discard(file: Path) -> None:
    """Take a record this process just wrote off the shelf, with the folders it left empty."""
    file.unlink(missing_ok=True)
    for folder in (file.parent, file.parent.parent, file.parent.parent.parent):
        try:
            folder.rmdir()
        except OSError:
            return
