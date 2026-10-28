"""Programmatic (in-process) entry point to a repository's OKF graph."""

from __future__ import annotations

import builtins
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from ostler import adr as adr_mod
from ostler import book_reach
from ostler import coverage as coverage_mod
from ostler import crud, doctor
from ostler import decisions as decisions_mod
from ostler import milestones as milestones_mod
from ostler import fmt as fmt_mod
from ostler import ids as ids_mod
from ostler import index as index_mod
from ostler import path as path_mod
from ostler import query as query_mod
from ostler import register as register_mod
from ostler import register_import
from ostler import registry, select, todo as todo_mod
from ostler.crud import Result
from ostler.qa import (
    QaOutcome,
    cmd_context,
    cmd_context_validate,
    cmd_lint,
    cmd_frames,
    cmd_report,
    cmd_run,
    cmd_validate,
    tools as qa_tools_mod,
)
from ostler.finding import Finding
from ostler.model import Epic, Graph, Milestone, Story, find_root, load
from ostler.pages import files_in_book
from ostler.qa.source_context import SourceRepository

if TYPE_CHECKING:
    from ostler.edit import EditPlan



SNAPSHOT_NAMESPACE = "graph-snapshot/3"

LOADED_DOC_ROOTS = ("services", "epics", "milestones")


def _file_sha(path: Path) -> str | None:
    """The content digest of *path*, or ``None`` when it cannot be read (absent included)."""
    try:
        return index_mod.content_sha(path.read_bytes())
    except OSError:
        return None


def _listing(roots: Iterable[Path]) -> str:
    """A digest of every markdown path under *roots* — the shape of the book, not its content."""
    names: builtins.list[str] = []
    for root in roots:
        if root.is_dir():
            names.extend(p.as_posix() for p in files_in_book(root))
    return index_mod.content_sha("\n".join(names).encode("utf-8"))


@dataclass
class Snapshot:
    """A loaded :class:`Graph` together with everything it was read from."""

    graph: Graph
    listing: str
    files: dict[str, str] = field(default_factory=dict)
    absent: tuple[str, ...] = ()

    def holds(self, roots: Iterable[Path]) -> bool:
        """Whether every dependency this snapshot recorded still reads exactly as it did."""
        if self.listing != _listing(roots):
            return False
        if any(_file_sha(Path(name)) != sha for name, sha in self.files.items()):
            return False
        return not any(Path(name).exists() for name in self.absent)


def _story_candidates(graph: Graph, epic: Epic, story: Story) -> builtins.list[Path]:
    """The paths `model._attach_story_md` tries, in its order."""
    candidates = []
    if story.path:
        candidates.append(graph.root / story.path)
    candidates.append(epic.directory / "stories" / story.slug / "story.md")
    return candidates


def _snapshot_of(graph: Graph, roots: Iterable[Path]) -> Snapshot:
    """Record what *graph* was read from, so a later load can check the reading still holds."""
    files: dict[str, str] = {}
    absent: builtins.list[str] = []

    def record(path: Path) -> None:
        sha = _file_sha(path)
        if sha is None:
            absent.append(str(path))
        else:
            files[str(path)] = sha

    record(graph.root / ".agents" / "ids.json")
    for feature in graph.features:
        record(feature.path)
    for node in graph.ui_nodes:
        record(node.path)
    for milestone in graph.milestones:
        record(milestone.path)
    for epic in graph.epics:
        if epic.epic_md is not None:
            record(epic.epic_md)
        for story in epic.stories:
            for candidate in _story_candidates(graph, epic, story):
                record(candidate)
                if candidate == story.story_md:
                    break
    return Snapshot(graph=graph, listing=_listing(roots), files=files,
                    absent=tuple(sorted(set(absent))))


def _unreadable(check: str, exc: Exception) -> QaOutcome:
    """A book that would not load, as the failed outcome of the check that asked for it."""
    message = f"{check} could not run: {exc}"
    return QaOutcome(ok=False, message=message, status="invalid",
                     data={"status": "invalid", "message": message})


class Ostler:
    """A loaded OKF graph plus the operations the ``ostler`` CLI exposes."""

    def __init__(
        self,
        root: str | Path | None = None,
        *,
        doc_roots: Mapping[str, str | Path] | None = None,
        use_index: bool = True,
        index_dir: str | Path | None = None,
    ) -> None:
        self._root = Path(root) if root is not None else None
        self._doc_roots = dict(doc_roots or {})
        self._graph: Graph | None = None
        self._use_index = use_index
        self._index_dir = index_dir
        self._index: index_mod.IndexStore | None = None
        self.snapshot_hits = 0
        self.snapshot_misses = 0

    @property
    def index(self) -> index_mod.IndexStore:
        """The store this instance loads through, resolved on first access."""
        if self._index is None:
            self._index = index_mod.IndexStore(
                find_root(self._root if self._root is not None else Path.cwd()),
                directory=self._index_dir,
                enabled=self._use_index,
            )
        return self._index

    def index_stats(self) -> dict:
        """The hit/miss line, in the shape ``doctor --json`` prints under ``index``."""
        return self.index.stats()

    def _load(self) -> Graph:
        """Read the graph from disk with this instance's store active."""
        with index_mod.use(self.index):
            key = self._snapshot_key()
            roots = self._loaded_doc_roots()
            snapshot = self._recall(key, roots)
            if snapshot is not None:
                return snapshot.graph
            graph = load(self._root, root_overrides=self._doc_roots)
            self.index.put_key(key, _snapshot_of(graph, roots))
            return graph

    def _loaded_doc_roots(self) -> tuple[Path, ...]:
        """The doc roots :func:`load` reads, resolved without loading anything."""
        return tuple(self._doc_root(kind) for kind in LOADED_DOC_ROOTS)

    def _snapshot_key(self) -> str | None:
        """The index key this book's graph snapshot is stored under, or ``None`` for no cache."""
        if not self.index.enabled:
            return None
        try:
            root = find_root(self._root if self._root is not None else Path.cwd())
            material = [SNAPSHOT_NAMESPACE, str(root)]
            material += [f"{kind}={self._doc_root(kind)}" for kind in sorted(LOADED_DOC_ROOTS)]
        except OSError:
            return None
        return self.index.content_key(*material)

    def _recall(self, key: str | None, roots: Iterable[Path]) -> Snapshot | None:
        """The stored snapshot when it still holds, counted — ``None`` for every other case."""
        if key is None:
            return None
        snapshot = self.index.read_key(key)
        if isinstance(snapshot, Snapshot) and snapshot.holds(roots):
            self.snapshot_hits += 1
            return snapshot
        self.snapshot_misses += 1
        return None

    def snapshot_stats(self) -> dict:
        """How often this instance was handed a whole graph rather than loading one."""
        return {"hits": self.snapshot_hits, "misses": self.snapshot_misses}

    @property
    def graph(self) -> Graph:
        """The cached graph snapshot, loaded on first access."""
        if self._graph is None:
            self._graph = self._load()
        return self._graph

    @property
    def root(self) -> Path:
        """The discovered graph root."""
        return self.graph.root

    def reload(self) -> Ostler:
        """Drop the cached snapshot; the next access re-reads from disk."""
        self._graph = None
        return self

    def _fresh(self) -> Graph:
        """A freshly loaded graph for a mutation to read current state from."""
        self._graph = self._load()
        return self._graph

    def _doc_root(self, kind: str) -> Path:
        """One configured doc root, derived the way :func:`load` derives it — without the load."""
        root = find_root(self._root or Path.cwd())
        configured = self._doc_roots.get(kind)
        if configured is None:
            return path_mod.doc_root_in(root, kind)
        path = Path(configured)
        return path if path.is_absolute() else root / path

    def list(self, etype: str, *, epic: str | None = None,
             status: str | None = None) -> builtins.list[dict]:
        """Concepts of ``etype`` (``ostler list --type``), optionally filtered."""
        return query_mod.list_entities(self.graph, etype, epic, status)

    def approved_milestone(self) -> Milestone:
        """The one milestone with `status: approved`; raises `MilestoneSelectionError` for none or several."""
        return milestones_mod.approved_milestone(self.graph)

    def milestone_readiness(self, name: str) -> builtins.list[Finding]:
        """The readiness findings of milestone *name*: errors once approved, warnings while proposed."""
        milestone = self.graph.milestone_by_name(name)
        if milestone is None:
            raise KeyError(f"no milestone '{name}'")
        return milestones_mod.check_milestone(self.graph, milestone)

    def service_books(self) -> builtins.set[str]:
        """The names of the books under ``docs/services/`` (a story's ``services`` name these)."""
        return milestones_mod.service_books(self.graph)

    def ui_services(self, names: Iterable[str]) -> builtins.set[str]:
        """The books among *names* whose driver is ``web`` or ``mobile`` (a story with one needs a mockup)."""
        return milestones_mod.ui_services(self.graph, names)

    def search(self, q: str, *, etype: str | None = None) -> builtins.list[dict]:
        """Ranked full-text search over every document root (``ostler search``)."""
        return query_mod.search(self.graph, q, etype)

    def query(
        self,
        name: str,
        arg: str,
        *,
        checkouts: dict[str, str | Path] | None = None,
    ) -> builtins.list[dict]:
        """A named reverse-index query (``ostler query``) — ``arg`` may be a short handle."""
        return query_mod.query(
            self.graph,
            name,
            ids_mod.resolve(self.graph, arg),
            {name: Path(value) for name, value in (checkouts or {}).items()},
        )

    def next_epic(self) -> dict | None:
        """The next epic with unfinished work, or ``None`` (``ostler next-epic``)."""
        return select.next_epic(self.graph)

    def next_story(self, epic: str,
                   skip: frozenset[str] | set[str] | None = None,
                   need: str = "build") -> dict | None:
        """The next runnable story in ``epic``, or ``None`` (``ostler next-story``)."""
        return select.next_story(self.graph, epic, skip=skip, need=need)

    def open_stories(self, epic: str) -> builtins.list[dict]:
        """The epic's stories that are not done, in dependency order, each with its spec dir and open deps."""
        return select.open_stories(self.graph, epic)

    def story(self, story_id: str) -> dict | None:
        """One story in the :meth:`open_stories` entry shape, by id, or ``None`` when unknown."""
        return select.story_entry(self.graph, story_id)

    def next_story_report(self, epic: str,
                          skip: frozenset[str] | set[str] | None = None,
                          need: str = "build") -> dict:
        """Why there is (or is not) a next story in ``epic`` — a ``state``, not an absence."""
        return select.next_story_report(self.graph, epic, skip=skip, need=need)

    def epic_authored(self, epic: str) -> bool:
        """Whether every story in ``epic`` has a written story.md (not merely a scaffolded one)."""
        found = select.epic_by_name(self.graph, epic)
        return found is not None and select.epic_authored(found)

    def todo(self) -> builtins.list[str]:
        """The epics queue, front-first (``ostler todo list``)."""
        return todo_mod.list_epics(self.graph)

    def register_root(self) -> Path:
        """The shelf the Register's records live on: ``backlog/`` in the artifacts dir."""
        return self._doc_root("register")

    def records(self) -> register_mod.RegisterRead:
        """Every record on the shelf, sorted by repo, area and id, and the files that did not parse."""
        return register_mod.records(self._fresh())

    def open_records(self, repo: str) -> builtins.list[register_mod.Record]:
        """The open records of *repo*."""
        return register_mod.open_records(self._fresh(), repo)

    def record_listing(self, repo: str = "", status: str = "") -> builtins.list[str]:
        """The one-line-per-record listing (``ostler backlog list``), optionally for one repo or status."""
        return register_mod.listing(
            r for r in self.records().records
            if (not repo or r.repo == repo) and (not status or r.status == status)
        )

    def file_record(
        self,
        *,
        repo: str,
        area: str,
        pattern: str,
        summary: str,
        filed_by: register_mod.FiledBy,
        symbols: Iterable[str] = (),
        source_story: str = "",
        body: str = "",
        status: register_mod.Status = "open",
        record_id: str = "",
        prefix: str | None = None,
    ) -> register_mod.Filing:
        """Shelve one record, minting its id when *record_id* is empty."""
        filing = register_mod.file_record(
            self._fresh(), repo=repo, area=area, pattern=pattern, summary=summary,
            filed_by=filed_by, symbols=symbols, source_story=source_story, body=body,
            status=status, record_id=record_id, prefix=prefix,
        )
        self._graph = None
        return filing

    def propose_decision(
        self,
        *,
        title: str,
        context: str,
        decision: str,
        consequences: str,
        evidence: Iterable[str],
        prefix: str | None = None,
    ) -> Result:
        """Propose a decision from *evidence* records, bind them to it and commit all of it in the artifacts repo."""
        return self._apply(adr_mod.propose(
            self._fresh(), title=title, context=context, decision=decision,
            consequences=consequences, evidence=evidence, prefix=prefix,
        ))

    def doctor(self, *, epic: str | None = None, check_schema: bool = True) -> QaOutcome:
        """The referential-integrity check (``ostler doctor``); ``data`` is the report dict."""
        try:
            graph = self.graph
        except (OSError, ValueError, RuntimeError) as exc:
            return _unreadable("doctor", exc)
        return doctor.cmd_doctor(graph, epic=epic, check_schema=check_schema)

    def fmt(self, *paths: str | Path, check: bool = False) -> builtins.list[str]:
        """Canonicalize the book's shape; the repo-relative paths that were not already so."""
        result = fmt_mod.run_fmt(self.graph, [str(p) for p in paths], check=check)
        return [path_mod.display_path(self.graph.root, p) for p in result.changed]

    def gc(self, *, write: bool = False) -> builtins.list[str]:
        """The pages no link path from their service's entries page reaches, deleted when *write* (``ostler gc``)."""
        dead = book_reach.dead_pages(self.graph)
        if write and dead:
            book_reach.delete_pages(dead)
            self._graph = None
        return [page.rel for page in dead]

    def coverage(self, *, inventory: str | Path, surface: str | None = None,
                 waivers: str | Path | None = None) -> QaOutcome:
        """The coverage join (``ostler coverage``); ``data`` is ``{covered, total, waived, missing, errors, ...}``."""
        try:
            graph = self.graph
        except (OSError, ValueError, RuntimeError) as exc:
            return _unreadable("coverage", exc)
        return coverage_mod.cmd_coverage(graph, surface=surface, inventory=inventory,
                                         waivers=waivers)

    def spec_path(self, story: str) -> str:
        """Absolute spec directory for a story id (``ostler path spec``); ``ValueError`` for an unknown id."""
        return path_mod.resolve_spec(self.graph, story)

    def epic_path(self, epic: str) -> str:
        """Directory of an epic, by number or bare slug (``ostler path epic``)."""
        return path_mod.resolve_epic(self.graph, epic)

    def story_path(self, story: str) -> str:
        """``story.md`` path for a story id (``ostler path story``)."""
        return path_mod.resolve_story(self.graph, story)

    def branch(self, ref: str, *, epic: bool = False) -> str:
        """Git branch name for a story id, or an epic name with *epic* (``ostler path branch``)."""
        return path_mod.resolve_branch(self.graph, ref, epic=epic)

    def epics_dir(self) -> Path:
        """Where epics live — ``docs/epics`` unless the repo configures otherwise."""
        return path_mod.epics_root(self.graph)

    def epics_index(self) -> Path:
        """The epic queue file, whose front entry is the current epic."""
        return path_mod.epics_index(self.graph)

    def epic_dir(self, epic: str) -> Path:
        """The folder of *epic*, resolved by number or bare slug (absolute)."""
        return path_mod.epic_dir(self.graph, epic)

    def story_dir(self, epic: str, slug: str) -> Path:
        """The folder of story *slug* in *epic* — join a filename onto this, not a path."""
        return path_mod.story_dir(self.graph, epic, slug)

    def services_dir(self, service: str = "") -> Path:
        """The feature book, scoped to one *service* in a multi-service workspace."""
        return path_mod.services_root(self.graph, service)

    def waivers_file(self, service: str = "") -> Path:
        """A book's ``coverage-waivers.json`` — what :meth:`coverage` takes as ``waivers``."""
        return path_mod.waivers_path(self.graph, service)

    def screenshots_dir(self, service: str = "") -> Path:
        """Where a walkthrough's registered screenshots live under a book."""
        return path_mod.screenshots_dir(self.graph, service)

    def handle(self, identifier: str) -> str:
        """The short handle for *identifier* — what to show a person, never what to store."""
        return self.handles().get(identifier, identifier)

    def handles(self) -> dict[str, str]:
        """``{id: handle}`` for every id in the repo — the whole table in one pass."""
        return ids_mod.table(ids_mod.known(self.graph))

    def expand(self, token: str) -> str:
        """*token* as a full id: a short handle is expanded, anything else returned untouched."""
        return ids_mod.resolve(self.graph, token)

    def create_epic(
        self, name: str, title: str, *, prefix: str | None = None, followups: bool = False,
    ) -> Result:
        """Create an epic, allocating its id (``ostler create epic``)."""
        return self._apply(crud.create_epic(self._fresh(), name, title, prefix, followups=followups))

    def create_milestone(
        self,
        name: str,
        title: str,
        *,
        source_items: builtins.list[str] | None = None,
        prefix: str | None = None,
    ) -> Result:
        """Create a milestone with a generated full id and backlog ownership."""
        graph = self._fresh()
        return self._apply(crud.create_milestone(
            graph,
            name,
            title,
            [ids_mod.resolve(graph, item) for item in (source_items or [])],
            prefix,
        ))

    def create_backlog_item(
        self,
        summary: str,
        *,
        repo: str,
        area: str,
        pattern: str = "untriaged",
        symbols: Iterable[str] = (),
        body: str = "",
        record_id: str = "",
        prefix: str | None = None,
    ) -> Result:
        """File a person's record on the Register and commit it in the artifacts repo (``ostler create backlog-item``)."""
        return self.backlog_add(
            summary, repo=repo, area=area, pattern=pattern, symbols=symbols, body=body,
            record_id=record_id, prefix=prefix,
        )

    def set_milestone_source_items(
        self,
        name: str,
        source_items: builtins.list[str],
    ) -> Result:
        """Replace a milestone's owned backlog ids, accepting short handles as input."""
        graph = self._fresh()
        return self._apply(crud.set_milestone_source_items(
            graph,
            name,
            [ids_mod.resolve(graph, item) for item in source_items],
        ))

    def create_story(self, epic: str, slug: str, title: str, *,
                      covers: builtins.list[str] | None = None,
                      depends: builtins.list[str] | None = None,
                      prefix: str | None = None) -> Result:
        """Create a story under ``epic`` (``ostler create story``)."""
        graph = self._fresh()
        return self._apply(crud.create_story(
            graph, epic, slug, title,
            [ids_mod.resolve(graph, c) for c in (covers or [])], depends or [], prefix))

    def delete_story(self, story: str) -> Result:
        """Delete a story by id (``ostler delete story``)."""
        return self._apply(crud.delete_story(self._fresh(), story))

    def update_story(
        self,
        story: str,
        *,
        title: str,
        covers: builtins.list[str],
        depends: builtins.list[str],
    ) -> Result:
        """Replace a story's graph metadata while preserving its authored document."""
        graph = self._fresh()
        return self._apply(
            crud.update_story(
                graph,
                story,
                title=title,
                covers=[ids_mod.resolve(graph, cover) for cover in covers],
                depends=depends,
            )
        )

    def scaffold_missing_sections(self, story: str) -> Result:
        """Add every required story section this story lacks, in contract order (idempotent)."""
        return self._apply(crud.scaffold_missing_sections(self._fresh(), story))

    def delete_epic(self, name: str) -> Result:
        """Delete an epic and remove its milestone and legacy queue references."""
        return self._apply(crud.delete_epic(self._fresh(), name))

    def create_spec(self, story: str, doc: str, *, title: str = "") -> Result:
        """Create or retro-stamp a spec doc (``ostler create spec``)."""
        return self._apply(crud.create_spec(self._doc_root("specs"), story, doc, title))

    def add_seed(self, epic: str, seed_id: str, *, status: str, summary: str = "",
                  meta: dict | None = None) -> Result:
        """Add a seed to ``epic`` (``ostler seed add``)."""
        graph = self._fresh()
        return self._apply(crud.add_seed(
            graph, epic, ids_mod.resolve(graph, seed_id), status, summary, meta or {}))

    def remove_seed(self, epic: str, seed_id: str) -> Result:
        """Remove a seed from ``epic`` (``ostler seed remove``)."""
        graph = self._fresh()
        return self._apply(crud.remove_seed(graph, epic, ids_mod.resolve(graph, seed_id)))

    def set_status(self, story: str, status: str) -> Result:
        """Set a story's status (``ostler set-status``)."""
        return self._apply(crud.set_status(self._fresh(), story, status))

    def set_conflict(self, story: str, conflict: str) -> Result:
        """Record or clear a story's acceptance-criteria conflict (``ostler conflict``)."""
        return self._apply(crud.set_conflict(self._fresh(), story, conflict))

    def unblock(self, *, story: str = "", epic: str = "",
                status: str = registry.DEFAULT_STORY_STATUS) -> Result:
        """Clear give-up stamps off stories (``ostler unblock``)."""
        return self._apply(crud.unblock(self._fresh(), story=story, epic=epic, status=status))

    def backlog_add(
        self,
        summary: str,
        *,
        repo: str,
        area: str,
        pattern: str = "untriaged",
        symbols: Iterable[str] = (),
        body: str = "",
        record_id: str = "",
        prefix: str | None = None,
    ) -> Result:
        """File a person's record on the Register and commit it in the artifacts repo (``ostler backlog add``)."""
        filing = register_mod.file_person(
            self._fresh(), summary=summary, repo=repo, area=area, pattern=pattern,
            symbols=symbols, body=body, record_id=record_id, prefix=prefix,
        )
        return self._apply(register_mod.filing_result(filing))

    def decision_add(self, slug: str, *, summary: str, repo: str = "") -> Result:
        """File an empty decision under ``docs/decisions/<slug>/`` of the docs home (``ostler decisions add``); *repo* defaults to the repository holding this instance's root."""
        start = self._root if self._root is not None else Path.cwd()
        return decisions_mod.add(
            self._fresh(), slug, repo=repo or decisions_mod.default_repo(start), summary=summary,
        )

    def backlog_import(
        self, source: str | Path, *, repo: str, prefix: str | None = None
    ) -> register_import.Imported:
        """Turn an old bullet list into records of *repo*, commit them in the artifacts repo, and delete the list (``ostler backlog adopt``)."""
        outcome = register_import.import_list(self._fresh(), self._resolve(source), repo, prefix)
        self._graph = None
        return outcome

    def close_record(self, token: str, status: register_mod.Status, reason: str) -> Result:
        """End a record as *status* with *reason* and commit it in the artifacts repo (``ostler backlog prune``); *token* may be a short handle."""
        return self._apply(register_mod.close_and_commit(self._fresh(), token, status, reason))

    def allocate_id(self) -> str:
        """Mint and persist the next repo-prefixed ostler id (``ACME-15``) — the same id space stories/epics/seeds draw from, so a backlog IOU is a first-class, numbered work item."""
        return ids_mod.allocate(self.graph)

    def todo_add(self, name: str, *, front: bool = False) -> Result:
        """Enqueue an epic (``ostler todo add``)."""
        return self._apply(todo_mod.add(self._fresh(), name, front=front))

    def todo_prune(self, name: str) -> Result:
        """Dequeue an epic (``ostler todo prune``)."""
        return self._apply(todo_mod.prune(self._fresh(), name))

    def todo_reorder(self, order: builtins.list[str]) -> Result:
        """Reorder the epics queue (``ostler todo reorder``)."""
        return self._apply(todo_mod.reorder(self._fresh(), order))

    def _apply(self, result: Result) -> Result:
        self._graph = None
        return result

    def _resolve(self, path: str | Path) -> Path:
        """A spec/plan path, taken relative to the graph root unless absolute."""
        p = Path(path)
        return p if p.is_absolute() else self.root / p

    def qa_context(self, *, base: str, spec: str | Path, head: str = "WORKTREE",
                   source_roots: dict[str, builtins.list[str]] | None = None,
                   services_root: str = "",
                   story_file: str | Path | None = None,
                   exclude_paths: Iterable[str] = (),
                   repositories: Iterable[SourceRepository] = ()) -> QaOutcome:
        """Build the base/head changed-code→OKF obligation packet and write it into ``spec`` (``ostler qa context``); ``data`` is the packet."""

        return cmd_context(
            self.root, self._resolve(spec), base=base, head=head,
            source_roots=source_roots or {}, services_root=services_root,
            story_file=self._resolve(story_file) if story_file else None,
            exclude_paths=exclude_paths, repositories=tuple(repositories))

    def qa_context_validate(self, *, spec: str | Path) -> QaOutcome:
        """Validate ``qa-okf-context.json`` in ``spec`` (``ostler qa context-validate``); ``data["problems"]`` holds the problem strings and is empty when it is valid."""

        return cmd_context_validate(self._resolve(spec))

    def qa_lint(self, plan_file: str | Path) -> QaOutcome:
        """Statically lint a ``qa_plan.py``'s AST without importing or executing it (``ostler qa lint``)."""

        return cmd_lint(Path(plan_file), root=self.root)

    def qa_validate(self, plan_file: str | Path, *, spec: str | Path | None = None) -> QaOutcome:
        """Validate a ``qa_plan.py`` without executing it (``ostler qa validate``)."""

        return cmd_validate(Path(plan_file),
                            self._resolve(spec) if spec else None, root=self.root)

    def qa_run(self, plan_file: str | Path, *, spec: str | Path | None = None,
               stop_on_fail: bool = False, only: builtins.list[str] | None = None,
               label: str | None = None) -> QaOutcome:
        """Execute a ``qa_plan.py`` in batch mode (``ostler qa run``)."""

        return cmd_run(Path(plan_file), self._resolve(spec) if spec else None,
                       stop_on_fail=stop_on_fail, only=only, label=label, root=self.root)

    def qa_report(self, spec: str | Path, *, label: str | None = None,
                  ledger: bool = False) -> QaOutcome:
        """Render a run per acceptance criterion and obligation (``ostler qa report``)."""

        return cmd_report(self._resolve(spec), label=label, ledger=ledger)

    def qa_frames(self, spec: str | Path, *, step: str | None = None,
                  at: float | None = None, target: str | None = None,
                  around: float = 1.0, fps: float = 10.0,
                  label: str | None = None) -> QaOutcome:
        """Write the frames of a run's recording around ``step`` — a step id from the report, or a unique fragment of its label — or around the position ``at`` (``ostler qa frames``)."""

        return cmd_frames(self._resolve(spec), step=step, at=at, target=target,
                          around=around, fps=fps, label=label)

    def qa_tools_catalog(self) -> QaOutcome:
        """This repo's opted-in QA tools, resolved against the machine's stablemate config (``ostler qa tools list``)."""

        return qa_tools_mod.cmd_catalog(self.root)

    def artifact_vet(self, kind: str, spec: str | Path) -> QaOutcome:
        """Validate a workflow artifact against its contract (``ostler artifact vet``)."""
        from ostler.artifact import cmd_vet

        return cmd_vet(kind, self._resolve(spec), self.root)

    def settle_review(self, story: str, *, write: bool = False,
                      status_write: bool = True) -> EditPlan:
        """Settle a story's status from its ``review-resolution.json``, gated on the artifacts/assertions the verdict cites (``ostler edit settle-review``); ``status_write=False`` writes the ledger alone."""
        from ostler import edit as edit_mod

        plan = edit_mod.settle_review(self._fresh(), story, status_write=status_write)
        if write and not plan.error:
            plan.apply()
            self._graph = None
        return plan

    def settle_answers(self, story: str, filed: Sequence[str], *,
                       filename: str = "review-answers.md", write: bool = False) -> dict:
        """Settle a story's markdown Answer list against the filed finding ids into its ``review-settlement.json`` ledger; never touches ``story.md``."""
        from ostler import edit as edit_mod

        ledger = edit_mod.settle_answers(self._fresh(), story, filed, filename=filename, write=write)
        if write:
            self._graph = None
        return ledger
