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

import json
from pathlib import Path
from typing import TYPE_CHECKING

from ostler import backlog as backlog_mod
from ostler import coverage as coverage_mod
from ostler import crud, doctor
from ostler import ids as ids_mod
from ostler import path as path_mod
from ostler import query as query_mod
from ostler import select, todo as todo_mod
from ostler import waivers as waivers_mod
from ostler.crud import Result
from ostler.model import Graph, load

if TYPE_CHECKING:
    from ostler.edit import EditPlan
    from ostler.qa import QaOutcome


class Ostler:
    """A loaded OKF graph plus the operations the ``ostler`` CLI exposes.

    :param root: any path inside the repo (the graph root is discovered upward,
        as the CLI's ``-C`` does); ``None`` uses the current working directory.
    """

    def __init__(self, root: str | Path | None = None) -> None:
        self._root = Path(root) if root is not None else None
        self._graph: Graph | None = None

    # -- graph lifecycle ----------------------------------------------------
    @property
    def graph(self) -> Graph:
        """The cached graph snapshot, loaded on first access."""
        if self._graph is None:
            self._graph = load(self._root)
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
        self._graph = load(self._root)
        return self._graph

    # -- retrieval ----------------------------------------------------------
    def list(self, etype: str, *, epic: str | None = None,
             status: str | None = None) -> list[dict]:
        """Concepts of ``etype`` (``ostler list --type``), optionally filtered."""
        return query_mod.list_entities(self.graph, etype, epic, status)

    def search(self, q: str, *, etype: str | None = None) -> list[dict]:
        """Full-text search over Concepts (``ostler search``)."""
        return query_mod.search(self.graph, q, etype)

    def query(self, name: str, arg: str) -> list[dict]:
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

    def todo(self) -> list[str]:
        """The epics queue, front-first (``ostler todo list``)."""
        return todo_mod.list_epics(self.graph)

    def backlog(self) -> list[dict]:
        """Backlog items as ``{"id", "text"}`` dicts (``ostler backlog list``)."""
        return [{"id": i, "text": t} for i, t in backlog_mod.items(self.graph)]

    def doctor(self, *, epic: str | None = None, check_schema: bool = True) -> dict:
        """The referential-integrity report as a dict (``ostler doctor --json``)."""
        return doctor.run(self.graph, epic_filter=epic,
                          check_schema=check_schema).as_dict()

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

    def create_story(self, epic: str, slug: str, title: str, *,
                     covers: list[str] | None = None,
                     depends: list[str] | None = None,
                     prefix: str | None = None) -> Result:
        """Create a story under ``epic`` (``ostler create story``).

        ``covers`` may name seeds by short handle; what is written into the epic is always the
        full id, so the coverage edge does not go stale when a handle later lengthens.
        """
        graph = self._fresh()
        return self._apply(crud.create_story(
            graph, epic, slug, title,
            [ids_mod.resolve(graph, c) for c in (covers or [])], depends or [], prefix))

    def create_spec(self, slug: str, doc: str, *, title: str = "") -> Result:
        """Create or retro-stamp a spec doc (``ostler create spec``). Idempotent."""
        return self._apply(crud.create_spec(self._fresh(), slug, doc, title))

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

    def set_status(self, slug: str, status: str) -> Result:
        """Set a story's status (``ostler set-status``)."""
        return self._apply(crud.set_status(self._fresh(), slug, status))

    def backlog_add(self, item_id: str, text: str, section: str = "") -> Result:
        """Append a backlog item (``ostler backlog add``)."""
        return self._apply(backlog_mod.add(self._fresh(), item_id, text, section))

    def backlog_prune(self, item_id: str) -> Result:
        """Remove a backlog item (``ostler backlog prune``) — ``item_id`` may be a short handle."""
        graph = self._fresh()
        return self._apply(backlog_mod.prune(graph, ids_mod.resolve(graph, item_id)))

    def allocate_id(self) -> str:
        """Mint and persist the next repo-prefixed ostler id (``PRED-15``) — the same id space
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

    def todo_reorder(self, order: list[str]) -> Result:
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
                   source_roots: dict[str, list[str]] | None = None,
                   features_root: str = "",
                   story_file: str | Path | None = None) -> dict:
        """Build the base/head changed-code→OKF obligation packet and write it into
        ``spec`` (``ostler qa context``); returns the packet."""
        from ostler.qa import build_context, write_context

        packet = build_context(
            self.root, base=base, head=head, source_roots=source_roots or {},
            features_root=features_root,
            story_file=self._resolve(story_file) if story_file else None)
        write_context(packet, self._resolve(spec))
        return packet

    def qa_context_validate(self, *, spec: str | Path) -> list[str]:
        """Validate ``qa-okf-context.json`` in ``spec``; returns problem strings, empty
        if valid (``ostler qa context-validate``)."""
        from ostler.qa import validate_context

        context_file = self._resolve(spec) / "qa-okf-context.json"
        packet = json.loads(context_file.read_text(encoding="utf-8"))
        return validate_context(packet)

    def qa_validate(self, plan_file: str | Path, *, spec: str | Path | None = None) -> QaOutcome:
        """Validate a ``qa-plan.yml`` without executing it (``ostler qa validate``)."""
        from ostler.qa import cmd_validate

        return cmd_validate(Path(plan_file),
                            self._resolve(spec) if spec else None, root=self.root)

    def qa_run(self, plan_file: str | Path, *, spec: str | Path | None = None,
               stop_on_fail: bool = False) -> QaOutcome:
        """Execute a ``qa-plan.yml`` in batch mode (``ostler qa run``)."""
        from ostler.qa import cmd_run

        return cmd_run(Path(plan_file), self._resolve(spec) if spec else None,
                       stop_on_fail=stop_on_fail, root=self.root)

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
