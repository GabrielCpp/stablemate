"""The Decision record — ``docs/adrs/<slug>/adr.md`` under the docs home, proposed from a cluster of Register records."""

from __future__ import annotations

import re
import subprocess
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import pydantic

from ostler import crud, decisions as decisions_mod, ids, markdown, path as path_mod, register
from ostler._vendor.stablemate_core import config as core_config
from ostler.model import Graph
from ostler.result import Result

ADR_FILE = "adr.md"
Status = Literal["proposed", "accepted", "rejected", "superseded"]

SECTIONS = ("Context", "Decision", "Consequences")
_SECTION = re.compile(r"^## (Context|Decision|Consequences)[ \t]*$", re.MULTILINE)


class Decision(pydantic.BaseModel):
    """One architecture decision as stored: where it came from, what it says, and the records that are its evidence."""

    model_config = pydantic.ConfigDict(frozen=True)

    id: str
    title: str
    status: Status = "proposed"
    repos: list[str] = []
    evidence: list[str] = []
    context: str = ""
    decision: str = ""
    consequences: str = ""

    @pydantic.field_validator("id")
    @classmethod
    def _id_is_one_path_segment(cls, value: str) -> str:
        """An id names a folder, so it is one non-empty path-safe segment."""
        if not register.ID_PATTERN.fullmatch(value):
            raise ValueError(f"id {value!r} must be one path-safe segment")
        return value

    @pydantic.field_validator("title")
    @classmethod
    def _title_is_one_line(cls, value: str) -> str:
        """The title is non-empty and on one line."""
        if not value.strip() or "\n" in value or "\r" in value:
            raise ValueError("title must be one non-empty line")
        return value.strip()

    @pydantic.field_validator("context", "decision", "consequences")
    @classmethod
    def _section_has_no_edge_newlines(cls, value: str) -> str:
        """A section is stored between headings, so its edge newlines are not part of it."""
        return value.strip("\n")

    def render(self) -> str:
        """The text of the decision file: frontmatter in field order, then the three sections."""
        front = self.model_dump(exclude={"context", "decision", "consequences"})
        parts = [f"---\n{crud.dump_frontmatter(front)}---\n"]
        for name in SECTIONS:
            text = getattr(self, name.lower())
            parts.append(f"\n## {name}\n\n{text}\n" if text else f"\n## {name}\n")
        return "".join(parts)

    @classmethod
    def parse(cls, text: str) -> Decision:
        """The decision in *text*; raises ``ValueError`` (or its pydantic subclass) when it is not one."""
        doc = markdown.split(text)
        if not doc.frontmatter:
            raise ValueError("decision file has no frontmatter")
        pieces = _SECTION.split(doc.body)
        sections = {pieces[n].lower(): pieces[n + 1].strip("\n") for n in range(1, len(pieces) - 1, 2)}
        return cls.model_validate({**doc.frontmatter, **sections})

    @classmethod
    def read(cls, path: Path) -> Decision:
        """The decision stored in the file at *path*."""
        return cls.parse(path.read_text(encoding="utf-8"))


@dataclass(frozen=True, slots=True)
class DecisionRead:
    """Every decision that parsed, sorted by id, and the files that did not."""

    decisions: tuple[Decision, ...]
    unreadable: tuple[Path, ...]


def decisions(graph: Graph) -> DecisionRead:
    """Read every decision file; one that fails to parse is reported, never listed."""
    good: list[Decision] = []
    bad: list[Path] = []
    for file in ids.decision_files(graph):
        try:
            good.append(Decision.read(file))
        except (ValueError, OSError):
            bad.append(file)
    good.sort(key=lambda d: d.id)
    return DecisionRead(tuple(good), tuple(bad))


def _refusal(message: str) -> Result:
    return Result(False, message)


def _commit(graph: Graph, target: Path, message: str) -> bool:
    """Commit exactly *target* in the artifacts repo, hooks off; False when the docs home is not that repo or there was nothing new to commit."""
    root = core_config.resolve_artifacts_dir()
    if graph.root.resolve() != root.resolve() or not (root / ".git").exists():
        return False
    rel = str(target.resolve().relative_to(root.resolve()))
    git = ["git", "-C", str(root)]
    subprocess.run([*git, "add", "--", rel], check=True, capture_output=True, timeout=60)
    if subprocess.run([*git, "diff", "--cached", "--quiet", "--", rel], check=False, capture_output=True, timeout=60).returncode == 0:
        return False
    try:
        subprocess.run(
            [*git, "-c", "core.hooksPath=/dev/null", "commit", "--no-verify", "-m", message, "--only", "--", rel],
            check=True, capture_output=True, timeout=60,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        subprocess.run([*git, "reset", "--quiet", "--", rel], check=False, capture_output=True, timeout=60)
        raise
    return True


def propose(
    graph: Graph,
    *,
    slug: str,
    title: str,
    context: str,
    decision: str,
    consequences: str,
    evidence: Iterable[str],
) -> Result:
    """Write a proposed decision named *slug* for *evidence* and bind each record to it; the decision file alone is committed, and only where the docs home is the artifacts repo."""
    problem = decisions_mod.slug_problem(slug)
    if problem:
        return _refusal(problem)
    wanted = list(dict.fromkeys(evidence))
    if not wanted:
        return _refusal("a decision needs evidence: name at least one record")
    home = path_mod.adr_root(graph) / slug
    if home.exists():
        return _refusal(f"decision '{slug}' already exists at {home / ADR_FILE}: read it, or pick a different slug")
    found: list[register.Record] = []
    shelved: list[Path] = []
    for token in wanted:
        folder = register.locate(graph, token)
        if folder is None:
            return _refusal(f"no record '{token}' to cite as evidence")
        try:
            record = register.Record.read(folder / register.RECORD_FILE)
        except (ValueError, OSError) as exc:
            return _refusal(f"record '{token}' cannot be read: {exc}")
        if record.decision:
            return _refusal(f"record '{record.id}' is already bound to decision '{record.decision}'")
        found.append(record)
        shelved.append(folder / register.RECORD_FILE)
    try:
        written = Decision(
            id=slug, title=title, repos=sorted({r.repo for r in found}),
            evidence=[r.id for r in found], context=context, decision=decision, consequences=consequences,
        )
    except pydantic.ValidationError as exc:
        first = exc.errors()[0]
        return _refusal(f"invalid decision: {'.'.join(map(str, first['loc']))}: {first['msg']}")
    core_config.ensure_artifacts_repo()
    target = home / ADR_FILE
    before = {path: path.read_text(encoding="utf-8") for path in shelved}
    home.mkdir(parents=True)
    target.write_text(written.render(), encoding="utf-8")
    try:
        for path in shelved:
            register.bind(path, written.id)
        _commit(graph, target, f"docs: propose {written.id} from {len(found)} records")
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
        for path, text in before.items():
            path.write_text(text, encoding="utf-8")
        target.unlink(missing_ok=True)
        home.rmdir()
        return Result(False, f"decision '{written.id}' was not proposed: the artifacts commit failed: {exc}")
    return Result(True, f"proposed decision '{written.id}' from {len(found)} records", [target, *shelved], entity_id=written.id)
