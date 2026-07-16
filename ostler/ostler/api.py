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

from . import backlog as backlog_mod
from . import crud, doctor
from . import path as path_mod
from . import query as query_mod
from . import select, todo as todo_mod
from .crud import Result
from .model import Graph, load

if TYPE_CHECKING:
    from .edit import EditPlan
    from .qa import QaOutcome


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

    def search(self, q: str, *, etype: str | None = None,
               owner: str | None = None, tag: str | None = None) -> list[dict]:
        """Full-text search over Concepts (``ostler search``)."""
        return query_mod.search(self.graph, q, etype, owner, tag)

    def query(self, name: str, arg: str) -> list[dict]:
        """A named reverse-index query (``ostler query``)."""
        return query_mod.query(self.graph, name, arg)

    def next_epic(self) -> dict | None:
        """The next epic with unfinished work, or ``None`` (``ostler next-epic``)."""
        return select.next_epic(self.graph)

    def next_story(self, epic: str) -> dict | None:
        """The next runnable story in ``epic``, or ``None`` (``ostler next-story``)."""
        return select.next_story(self.graph, epic)

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

    # -- path resolution ----------------------------------------------------
    def spec_path(self, slug: str) -> str:
        """Spec directory for a story slug (``ostler path spec``)."""
        return path_mod.resolve_spec(self.graph, slug)

    def story_path(self, epic: str, slug: str) -> str:
        """``story.md`` path for an epic + slug (``ostler path story``)."""
        return path_mod.resolve_story(self.graph, epic, slug)

    def branch(self, slug: str, *, epic: bool = False) -> str:
        """Git branch name for a slug (``ostler path branch``); no graph needed."""
        return path_mod.resolve_branch(slug, epic=epic)

    # -- mutation (each invalidates the cached snapshot) --------------------
    def create_epic(self, name: str, title: str, *, prefix: str | None = None) -> Result:
        """Create an epic, allocating its id (``ostler create epic``)."""
        return self._apply(crud.create_epic(self._fresh(), name, title, prefix))

    def create_story(self, epic: str, slug: str, title: str, *,
                     covers: list[str] | None = None,
                     depends: list[str] | None = None,
                     prefix: str | None = None) -> Result:
        """Create a story under ``epic`` (``ostler create story``)."""
        return self._apply(crud.create_story(
            self._fresh(), epic, slug, title,
            covers or [], depends or [], prefix))

    def add_seed(self, epic: str, seed_id: str, *, status: str, summary: str = "",
                 meta: dict | None = None) -> Result:
        """Add a seed to ``epic`` (``ostler seed add``)."""
        return self._apply(crud.add_seed(
            self._fresh(), epic, seed_id, status, summary, meta or {}))

    def set_status(self, slug: str, status: str) -> Result:
        """Set a story's status (``ostler set-status``)."""
        return self._apply(crud.set_status(self._fresh(), slug, status))

    def backlog_add(self, item_id: str, text: str, section: str = "") -> Result:
        """Append a backlog item (``ostler backlog add``)."""
        return self._apply(backlog_mod.add(self._fresh(), item_id, text, section))

    def backlog_prune(self, item_id: str) -> Result:
        """Remove a backlog item (``ostler backlog prune``)."""
        return self._apply(backlog_mod.prune(self._fresh(), item_id))

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
                   features_root: str = "docs/features",
                   story_file: str | Path | None = None) -> dict:
        """Build the base/head changed-code→OKF obligation packet and write it into
        ``spec`` (``ostler qa context``); returns the packet."""
        from .qa import build_context, write_context

        packet = build_context(
            self.root, base=base, head=head, source_roots=source_roots or {},
            features_root=features_root,
            story_file=self._resolve(story_file) if story_file else None)
        write_context(packet, self._resolve(spec))
        return packet

    def qa_context_validate(self, *, spec: str | Path) -> list[str]:
        """Validate ``qa-okf-context.json`` in ``spec``; returns problem strings, empty
        if valid (``ostler qa context-validate``)."""
        from .qa import validate_context

        context_file = self._resolve(spec) / "qa-okf-context.json"
        packet = json.loads(context_file.read_text(encoding="utf-8"))
        return validate_context(packet)

    def qa_validate(self, plan_file: str | Path, *, spec: str | Path | None = None) -> QaOutcome:
        """Validate a ``qa-plan.yml`` without executing it (``ostler qa validate``)."""
        from .qa import cmd_validate

        return cmd_validate(Path(plan_file),
                            self._resolve(spec) if spec else None, root=self.root)

    def qa_run(self, plan_file: str | Path, *, spec: str | Path | None = None,
               stop_on_fail: bool = False) -> QaOutcome:
        """Execute a ``qa-plan.yml`` in batch mode (``ostler qa run``)."""
        from .qa import cmd_run

        return cmd_run(Path(plan_file), self._resolve(spec) if spec else None,
                       stop_on_fail=stop_on_fail, root=self.root)

    # -- schema-checked artifacts (ostler ``artifact …``) -------------------
    def artifact_vet(self, kind: str, spec: str | Path) -> dict:
        """Validate a workflow artifact against its contract; returns the outcome dict
        (``{"kind","path","status",["problems"],["error"]}`` — ``ostler artifact vet``)."""
        from .artifact import vet

        return vet(kind, self._resolve(spec), self.root).to_dict()

    # -- structured edits (ostler ``edit …``) -------------------------------
    def settle_review(self, slug: str, *, write: bool = False) -> EditPlan:
        """Settle a story's status from its ``review-resolution.json``, gated on the
        artifacts/assertions the verdict cites (``ostler edit settle-review``). Applies
        the transition when ``write=True``; the returned plan carries ``.error`` and the
        per-finding ledger the caller inspects."""
        from . import edit as edit_mod

        plan = edit_mod.settle_review(self._fresh(), slug)
        if write and not plan.error:
            plan.apply()
            self._graph = None
        return plan
