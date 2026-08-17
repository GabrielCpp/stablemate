"""Programmatic (in-process) entry point to a repository's OKF graph.

This is the *library* face of the ``ostler`` CLI — the analog of GitPython's
``Repo`` or PyGithub's ``Github``. A caller loads a graph once and commands it
through method calls that return plain Python objects (``dict``/``list``/``str``
and ``Result``), instead of spawning ``ostler`` as a subprocess and scraping JSON
out of its stdout::

    from ostler import Ostler

    okf = Ostler(root)
    queue   = okf.todo()                       # ["epic-a", "epic-b"]
    stories = okf.list("story", epic="epic-a") # [{"slug": ..., "status": ...}, ...]
    spec    = okf.spec_path("01-foo")          # "docs/specs/01-foo"

Every method here is a thin binding over the same functional core the CLI
dispatches to (``ostler.query``/``select``/``path``/``backlog``/``todo``/
``doctor``/``crud``); the CLI merely ``json.dumps`` what these return.

Staleness contract — the graph is a *snapshot* read from disk at load time, so a
mutation invalidates it (exactly as the CLI reloads on every invocation). Read
methods reuse one cached snapshot (the whole point over per-call subprocesses);
mutation methods apply against a freshly reloaded graph and then invalidate the
cache, so the next read re-loads. Call :meth:`reload` to force a refresh.
"""

from __future__ import annotations

# `Ostler.list` (the method behind `ostler list --type`) shadows the builtin for the
# whole class body, so a bare `list[dict]` annotation in here resolves to that method
# rather than to the type. `from __future__ import annotations` hides the damage —
# annotations are never evaluated, so nothing raises — but every such annotation is
# wrong to anything that does resolve it, from `typing.get_type_hints` to a type
# checker. Naming the builtin through `builtins` is what makes them mean what they read
# as. The method keeps its name: it is the public API spelling of the CLI verb.
import builtins
import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import TYPE_CHECKING

from ostler import backlog as backlog_mod
from ostler import coverage as coverage_mod
from ostler import crud, doctor
from ostler import fmt as fmt_mod
from ostler import ids as ids_mod
from ostler import index as index_mod
from ostler import path as path_mod
from ostler import query as query_mod
from ostler import registry, select, todo as todo_mod
from ostler import waivers as waivers_mod
from ostler.crud import Result
from ostler.qa import (
    QaOutcome,
    build_context,
    cmd_lint,
    cmd_run,
    cmd_validate,
    tools as qa_tools_mod,
    validate_context,
    write_context,
)
from ostler.model import Graph, find_root, load

if TYPE_CHECKING:
    from ostler.edit import EditPlan


class Ostler:
    """A loaded OKF graph plus the operations the ``ostler`` CLI exposes.

    :param root: any path inside the repo (the graph root is discovered upward,
        as the CLI's ``-C`` does); ``None`` uses the current working directory.
    :param use_index: consult the persistent parse index (the library face of
        ``--no-index``; ``False`` forces the uncached path both ways).
    :param index_dir: an explicit index directory, overriding the resolved one
        (the library face of ``--index-dir``).
    """

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

    # -- the parse index ----------------------------------------------------
    @property
    def index(self) -> index_mod.IndexStore:
        """The store this instance loads through, resolved on first access.

        One store for the object's whole life rather than one per load, so the hit/miss
        counts read as this caller's totals — an in-process caller reloads many times, and
        per-load counts would answer a question nobody asked.
        """
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
            return load(self._root, root_overrides=self._doc_roots)

    # -- graph lifecycle ----------------------------------------------------
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
        """Drop the cached snapshot; the next access re-reads from disk. Returns
        ``self`` so it can chain (``okf.reload().list("story")``)."""
        self._graph = None
        return self

    def _fresh(self) -> Graph:
        """A freshly loaded graph for a mutation to read current state from."""
        self._graph = self._load()
        return self._graph

    def _doc_root(self, kind: str) -> Path:
        """One configured doc root, derived the way :func:`load` derives it — without the load.

        A mutation that needs a *directory* and no graph content must not pay for parsing every
        markdown file in the book to learn it. That parse is tens of seconds on a real repo, and
        :meth:`create_spec` — the one such mutation — is called once per file by the coder's
        `stamp_specs` after every writer phase.

        The `root_overrides` half of :func:`load` is repeated here rather than shared because it
        is three lines and the alternative is a load-shaped helper that takes a config; if a
        third caller appears, hoist it.
        """
        root = find_root(self._root or Path.cwd())
        configured = self._doc_roots.get(kind)
        if configured is None:
            return path_mod.doc_root_in(root, kind)
        path = Path(configured)
        return path if path.is_absolute() else root / path

    # -- retrieval ----------------------------------------------------------
    def list(self, etype: str, *, epic: str | None = None,
             status: str | None = None) -> builtins.list[dict]:
        """Concepts of ``etype`` (``ostler list --type``), optionally filtered."""
        return query_mod.list_entities(self.graph, etype, epic, status)

    def search(self, q: str, *, etype: str | None = None) -> builtins.list[dict]:
        """Full-text search over Concepts (``ostler search``)."""
        return query_mod.search(self.graph, q, etype)

    def query(self, name: str, arg: str) -> builtins.list[dict]:
        """A named reverse-index query (``ostler query``) — ``arg`` may be a short handle."""
        return query_mod.query(self.graph, name, ids_mod.resolve(self.graph, arg))

    def next_epic(self) -> dict | None:
        """The next epic with unfinished work, or ``None`` (``ostler next-epic``)."""
        return select.next_epic(self.graph)

    def next_story(self, epic: str,
                   skip: frozenset[str] | set[str] | None = None,
                   need: str = "build") -> dict | None:
        """The next runnable story in ``epic``, or ``None`` (``ostler next-story``).

        ``skip`` — slugs given up this run — are excluded without counting as done, so one
        story failing QA does not strand the rest of the epic. See ``select.next_story``.
        ``need="author"`` asks the other question: which story still needs writing.
        """
        return select.next_story(self.graph, epic, skip=skip, need=need)

    def next_story_report(self, epic: str,
                          skip: frozenset[str] | set[str] | None = None,
                          need: str = "build") -> dict:
        """Why there is (or is not) a next story in ``epic`` — a ``state``, not an absence.

        ``next_story``'s ``None`` conflates "the epic is finished" with "its remaining stories
        are blocked or were given up on". A caller that acts on that absence — the coder
        workflow prunes and merges the epic — must call this instead. See
        ``select.next_story_report`` for the states and for ``need``.
        """
        return select.next_story_report(self.graph, epic, skip=skip, need=need)

    def epic_authored(self, epic: str) -> bool:
        """Whether every story in ``epic`` has a written story.md (not merely a scaffolded one).

        The authoring counterpart to ``next_epic``'s done-ness: this is what tells an author
        rerun that an epic still needs work. Unknown epics are not authored.
        """
        found = select.epic_by_name(self.graph, epic)
        return found is not None and select.epic_authored(found)

    def todo(self) -> builtins.list[str]:
        """The epics queue, front-first (``ostler todo list``)."""
        return todo_mod.list_epics(self.graph)

    def backlog(self) -> builtins.list[dict]:
        """Backlog items as ``{"id", "text"}`` dicts (``ostler backlog list``)."""
        return [{"id": i, "text": t} for i, t in backlog_mod.items(self.graph)]

    def doctor(self, *, epic: str | None = None, check_schema: bool = True) -> dict:
        """The referential-integrity report as a dict (``ostler doctor --json``)."""
        return doctor.run(self.graph, epic_filter=epic,
                          check_schema=check_schema).as_dict()

    def fmt(self, *paths: str | Path, check: bool = False) -> builtins.list[str]:
        """Canonicalize the book's shape; the repo-relative paths that were not already so.

        ``check=True`` writes nothing, which is the mode a test wants: a non-canonical book
        makes every diff against it unreadable, because the next tool through converges on
        the canonical shape and buries the semantic change in bullet reordering.
        """
        result = fmt_mod.run_fmt(self.graph, [str(p) for p in paths], check=check)
        return [str(p.relative_to(self.graph.root)) for p in result.changed]

    def coverage(self, *, inventory: str | Path, surface: str | None = None,
                 waivers: str | Path | None = None) -> dict:
        """The coverage join as ``{covered, total, waived, missing, errors}``.

        Raises on an unreadable inventory rather than reporting zero units — an empty unit
        list reads downstream as "everything is covered" (``ostler coverage``).
        """
        return coverage_mod.run(self.graph, surface=surface, inventory=inventory,
                                waivers=waivers)

    # -- path resolution ----------------------------------------------------
    def spec_path(self, slug: str) -> str:
        """Spec directory for a story slug (``ostler path spec``)."""
        return path_mod.resolve_spec(self.graph, slug)

    def epic_path(self, epic: str) -> str:
        """Directory of an epic, by number or bare slug (``ostler path epic``).

        The one place a caller should learn where an epic lives: the directory is numbered
        (`docs/epics/0001-checkout-flow`), so building the path by joining the epics root
        with a slug now names a directory that does not exist.
        """
        return path_mod.resolve_epic(self.graph, epic)

    def story_path(self, epic: str, slug: str) -> str:
        """``story.md`` path for an epic + slug (``ostler path story``)."""
        return path_mod.resolve_story(self.graph, epic, slug)

    def branch(self, slug: str, *, epic: bool = False) -> str:
        """Git branch name for a slug (``ostler path branch``); no graph needed."""
        return path_mod.resolve_branch(slug, epic=epic)

    # -- doc-tree locations (absolute; the ``resolve_*`` pair above is CLI parity) ---
    # A caller that holds an ``Ostler`` reaches the doc tree here rather than joining
    # ``docs/<something>`` onto a root of its own: these follow ``docRoots:`` config, a
    # hand-built join does not, and the symptom of the second derivation is a workflow
    # writing into a directory nothing reads. A caller holding only a repo root gets the
    # same answers, graph-free, from ``ostler.path``'s ``*_in`` functions.
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

    def backlog_file(self) -> Path:
        """The intake list, ``docs/backlog.md`` — the file :meth:`backlog` reads."""
        return path_mod.backlog_path(self.graph)

    def features_dir(self, service: str = "") -> Path:
        """The feature book, scoped to one *service* in a multi-service workspace."""
        return path_mod.features_root(self.graph, service)

    def waivers_file(self, service: str = "") -> Path:
        """A book's ``coverage-waivers.json`` — what :meth:`coverage` takes as ``waivers``."""
        return path_mod.waivers_path(self.graph, service)

    def screenshots_dir(self, service: str = "") -> Path:
        """Where a walkthrough's registered screenshots live under a book."""
        return path_mod.screenshots_dir(self.graph, service)

    # -- ids and their short handles ----------------------------------------
    def handle(self, identifier: str) -> str:
        """The short handle for *identifier* — what to show a person, never what to store.

        Abbreviated against every id in the repo, so the handle is unambiguous now; it can
        lengthen once a colliding id is minted, which is why the full id is what gets written
        into a document (``ostler --handles``).
        """
        return self.handles().get(identifier, identifier)

    def handles(self) -> dict[str, str]:
        """``{id: handle}`` for every id in the repo — the whole table in one pass."""
        return ids_mod.table(ids_mod.known(self.graph))

    def expand(self, token: str) -> str:
        """*token* as a full id: a short handle is expanded, anything else returned untouched.

        Every ostler entry point that takes an id already does this, so a node only needs it
        when it accepts an id from somewhere ostler is not (an operator answer, a prompt).
        """
        return ids_mod.resolve(self.graph, token)

    # -- mutation (each invalidates the cached snapshot) --------------------
    def create_epic(self, name: str, title: str, *, prefix: str | None = None) -> Result:
        """Create an epic, allocating its id (``ostler create epic``).

        The directory is numbered in creation order, so the name that exists afterwards is
        ``result.entity_name`` (``0001-<name>``), not ``name``.
        """
        return self._apply(crud.create_epic(self._fresh(), name, title, prefix))

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
        text: str,
        *,
        section: str = "",
        prefix: str | None = None,
    ) -> Result:
        """File a backlog item with a generated full id."""
        return self._apply(backlog_mod.create(self._fresh(), text, section, prefix))

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
        """Create a story under ``epic`` (``ostler create story``).

        ``covers`` may name seeds by short handle; what is written into the epic is always the
        full id, so the coverage edge does not go stale when a handle later lengthens.
        """
        graph = self._fresh()
        return self._apply(crud.create_story(
            graph, epic, slug, title,
            [ids_mod.resolve(graph, c) for c in (covers or [])], depends or [], prefix))

    def delete_story(self, slug: str) -> Result:
        """Delete a story by slug (``ostler delete story``)."""
        return self._apply(crud.delete_story(self._fresh(), slug))

    def update_story(
        self,
        slug: str,
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
                slug,
                title=title,
                covers=[ids_mod.resolve(graph, cover) for cover in covers],
                depends=depends,
            )
        )

    def delete_epic(self, name: str) -> Result:
        """Delete an epic and remove its milestone and legacy queue references."""
        return self._apply(crud.delete_epic(self._fresh(), name))

    def create_spec(self, slug: str, doc: str, *, title: str = "") -> Result:
        """Create or retro-stamp a spec doc (``ostler create spec``). Idempotent.

        The one mutation that loads no graph: it needs the specs directory and nothing else.
        See :meth:`_doc_root`.
        """
        return self._apply(crud.create_spec(self._doc_root("specs"), slug, doc, title))

    def add_seed(self, epic: str, seed_id: str, *, status: str, summary: str = "",
                  meta: dict | None = None) -> Result:
        """Add a seed to ``epic`` (``ostler seed add``).

        ``seed_id`` may be a short handle. That matters here more than for a read: `seed add` is
        update-or-create, so a handle left unresolved would file a *second* seed under a name that
        only looked new instead of updating the one it names.
        """
        graph = self._fresh()
        return self._apply(crud.add_seed(
            graph, epic, ids_mod.resolve(graph, seed_id), status, summary, meta or {}))

    def remove_seed(self, epic: str, seed_id: str) -> Result:
        """Remove a seed from ``epic`` (``ostler seed remove``)."""
        graph = self._fresh()
        return self._apply(crud.remove_seed(graph, epic, ids_mod.resolve(graph, seed_id)))

    def set_status(self, slug: str, status: str) -> Result:
        """Set a story's status (``ostler set-status``)."""
        return self._apply(crud.set_status(self._fresh(), slug, status))

    def unblock(self, *, story: str = "", epic: str = "",
                status: str = registry.DEFAULT_STORY_STATUS) -> Result:
        """Clear give-up stamps off stories (``ostler unblock``).

        Named scope, no positional: ``unblock()`` with nothing sweeps the whole graph, and a
        caller that meant one story must not reach that by passing it in the wrong slot.
        """
        return self._apply(crud.unblock(self._fresh(), story=story, epic=epic, status=status))

    def backlog_add(self, item_id: str, text: str, section: str = "") -> Result:
        """Append a backlog item (``ostler backlog add``)."""
        return self._apply(backlog_mod.add(self._fresh(), item_id, text, section))

    def backlog_adopt(self, path: str = "", *, prefix: str | None = None) -> Result:
        """Assign ids to every unnamed bullet in an existing backlog."""
        return self._apply(backlog_mod.adopt(self._fresh(), path, prefix))

    def backlog_prune(self, item_id: str) -> Result:
        """Remove a backlog item (``ostler backlog prune``) — ``item_id`` may be a short handle."""
        graph = self._fresh()
        return self._apply(backlog_mod.prune(graph, ids_mod.resolve(graph, item_id)))

    def allocate_id(self) -> str:
        """Mint and persist the next repo-prefixed ostler id (``ACME-15``) — the same id space
        stories/epics/seeds draw from, so a backlog IOU is a first-class, numbered work item."""
        return ids_mod.allocate(self.graph)

    def add_doctor_waiver(self, code: str, ref: str, reason: str, backlog: str = "") -> Result:
        """Record an accepted-defect doctor waiver so the finding downgrades error→warn.

        The finding stays visible in ``doctor``; it just stops gating. Pairs with ``backlog_add``:
        the caller files the IOU that tracks the real fix and passes its id here as ``backlog``.
        """
        # Uses only ``graph.root`` (writes a JSON file beside docs/), so the cached graph is fine —
        # no ``_fresh()`` reload, which on a large book would cost seconds per waiver.
        changed = waivers_mod.add(self.graph, code, ref, reason, backlog)
        return Result(changed, "" if changed else "empty code or ref")

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
        # A mutation wrote to disk; the snapshot we loaded to run it is now stale.
        self._graph = None
        return result

    def _resolve(self, path: str | Path) -> Path:
        """A spec/plan path, taken relative to the graph root unless absolute."""
        p = Path(path)
        return p if p.is_absolute() else self.root / p

    # -- QA plans & obligation context (spec-oriented; ostler ``qa …``) ------
    # These operate on a spec dir + plan files rather than the graph snapshot, so
    # they are lazy-imported: the QA/vet machinery (browsers, image libs) never
    # loads for a script that only reads the graph.
    def qa_context(self, *, base: str, spec: str | Path, head: str = "WORKTREE",
                   source_roots: dict[str, builtins.list[str]] | None = None,
                   features_root: str = "",
                   story_file: str | Path | None = None,
                   exclude_paths: Iterable[str] = ()) -> dict:
        """Build the base/head changed-code→OKF obligation packet and write it into
        ``spec`` (``ostler qa context``); returns the packet.

        ``exclude_paths`` drops repo-relative paths from the diff before it is mapped —
        for a ``head="WORKTREE"`` caller that knows some of the dirt is not its own."""

        packet = build_context(
            self.root, base=base, head=head, source_roots=source_roots or {},
            features_root=features_root,
            story_file=self._resolve(story_file) if story_file else None,
            exclude_paths=exclude_paths)
        write_context(packet, self._resolve(spec))
        return packet

    def qa_context_validate(self, *, spec: str | Path) -> builtins.list[str]:
        """Validate ``qa-okf-context.json`` in ``spec``; returns problem strings, empty
        if valid (``ostler qa context-validate``)."""

        context_file = self._resolve(spec) / "qa-okf-context.json"
        packet = json.loads(context_file.read_text(encoding="utf-8"))
        return validate_context(packet)

    def qa_lint(self, plan_file: str | Path, *, spec: str | Path | None = None) -> QaOutcome:
        """Statically lint a ``qa_plan.py``'s AST without importing or executing it
        (``ostler qa lint``)."""

        return cmd_lint(Path(plan_file),
                        self._resolve(spec) if spec else None, root=self.root)

    def qa_validate(self, plan_file: str | Path, *, spec: str | Path | None = None) -> QaOutcome:
        """Validate a ``qa_plan.py`` without executing it (``ostler qa validate``)."""

        return cmd_validate(Path(plan_file),
                            self._resolve(spec) if spec else None, root=self.root)

    def qa_run(self, plan_file: str | Path, *, spec: str | Path | None = None,
               stop_on_fail: bool = False) -> QaOutcome:
        """Execute a ``qa_plan.py`` in batch mode (``ostler qa run``)."""

        return cmd_run(Path(plan_file), self._resolve(spec) if spec else None,
                       stop_on_fail=stop_on_fail, root=self.root)

    def qa_tools_catalog(self) -> dict:
        """This repo's opted-in QA tools, resolved against the machine's stablemate
        config (``ostler qa tools list``); same ``{"tools": [...], "errors": [...]}``
        shape the CLI prints."""

        specs, errors = qa_tools_mod.catalog(self.root)
        rows = [
            {
                "name": spec.name,
                "command": spec.command,
                "description": spec.description,
                "builtin": spec.builtin,
                "available": spec.available,
            }
            for spec in specs.values()
        ]
        return {"tools": rows, "errors": errors}

    # -- schema-checked artifacts (ostler ``artifact …``) -------------------
    def artifact_vet(self, kind: str, spec: str | Path) -> dict:
        """Validate a workflow artifact against its contract; returns the outcome dict
        (``{"kind","path","status",["problems"],["error"]}`` — ``ostler artifact vet``)."""
        from ostler.artifact import vet

        return vet(kind, self._resolve(spec), self.root).to_dict()

    # -- structured edits (ostler ``edit …``) -------------------------------
    def settle_review(self, slug: str, *, write: bool = False) -> EditPlan:
        """Settle a story's status from its ``review-resolution.json``, gated on the
        artifacts/assertions the verdict cites (``ostler edit settle-review``). Applies
        the transition when ``write=True``; the returned plan carries ``.error`` and the
        per-finding ledger the caller inspects."""
        from ostler import edit as edit_mod

        plan = edit_mod.settle_review(self._fresh(), slug)
        if write and not plan.error:
            plan.apply()
            self._graph = None
        return plan
