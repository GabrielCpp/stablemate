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

Outcome contract — a *check* answers, it does not raise. :meth:`doctor`,
:meth:`coverage` and the whole qa/artifact family return a
:class:`~ostler.qa.QaOutcome` (``ok``/``status``/``message``/``data``), and a
data-shaped failure is part of that answer: an unreadable inventory, a malformed
plan, a context file that will not parse, a book that will not load all come back
as ``ok=False, status="invalid"``. The normalization is here rather than in each
caller because it *was* in every caller — ``cli.py`` and the coder workflow's
``ostler_qa`` adapter each wrapped these calls in the same
``except (OSError, ValueError, RuntimeError)``, and a translation two call sites
reimplement belongs one layer down.

A **call-site** mistake still raises, and should: an unknown ``etype``, a ``need``
that is neither ``"build"`` nor ``"author"``, a bad argument type is a bug where it
was made, and returning it as an outcome would hide it. The name-taking reads
(:meth:`list`/:meth:`search`/:meth:`query`, the ``*_path`` resolvers,
:meth:`expand`) have no data-shaped raises to convert at all — an unmatched name
comes back as ``[]``, as ``None``, or as the name itself, which is already the
answer an outcome would carry.
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
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
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
    cmd_context,
    cmd_context_validate,
    cmd_lint,
    cmd_frames,
    cmd_report,
    cmd_run,
    cmd_validate,
    tools as qa_tools_mod,
)
from ostler.model import Epic, Graph, Story, find_root, load
from ostler.qa.source_context import SourceRepository

if TYPE_CHECKING:
    from ostler.edit import EditPlan



#: The namespace whole-graph snapshots live under, so a snapshot key can never collide with
#: a document product's under :meth:`IndexStore.content_key`. Bump the number for any change
#: to what :class:`Snapshot` records or to how it is validated — an older entry validated by
#: newer rules is exactly the wrong answer this cache may not give. A snapshot holds the whole
#: `Graph`, so a new `doc_roots` key is such a change: the stored graph has no entry under it
#: and every reader that indexes the mapping raises `KeyError` on a repo that did nothing wrong.
SNAPSHOT_NAMESPACE = "graph-snapshot/2"

#: The doc roots :func:`ostler.model.load` reads. Their recursive `*.md` listing is what tells
#: a snapshot that a document has been added, removed or renamed since it was taken — the
#: per-file digests below can only speak for files that already existed.
LOADED_DOC_ROOTS = ("features", "epics", "milestones")


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
            names.extend(sorted(p.as_posix() for p in root.rglob("*.md")))
    return index_mod.content_sha("\n".join(names).encode("utf-8"))


@dataclass
class Snapshot:
    """A loaded :class:`Graph` together with everything it was read from.

    The parse index already saves the *parsing* of each document; what it cannot save is the
    walk, the frontmatter dispatch and the cross-linking that turn several thousand parsed
    documents into a graph, and that is what a fresh `Ostler` — or a fresh `ostler` process —
    pays again on every construction while nothing in the book has moved.

    Validation is by recorded dependency rather than by a key over the whole tree, because the
    two are not the same cache. A key over the tree would be invalidated by every write into
    `docs/specs/`, which is precisely what the coder workflow does between two loads that want
    the same graph. What the graph is actually a function of is: the documents it *read*
    (:attr:`files`), the candidate paths it probed and did not find (:attr:`absent` — a story
    file appearing where one was missing changes the graph), and the set of documents there
    were to read at all (:attr:`listing`). Everything global — ostler's version, the schemas,
    the kind registry, the config, the waivers, the freeze table — is already in the index
    epoch that the key is built from.
    """

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
    """The paths `model._attach_story_md` tries, in its order.

    Repeated here rather than shared because the loader's copy is a loop over two lines and
    what this needs is the *list* — including the entries it rejected, which the loader does
    not keep. A drift between the two costs a stale hit, which is why
    `test_snapshot_probe_order_matches_the_loader` pins them against each other.
    """
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
    """A book that would not load, as the failed outcome of the check that asked for it.

    The graph is loaded lazily by the first method that needs it, so an unreadable book
    surfaces at the call rather than at construction. For a check — `doctor`, `coverage` —
    that is data-shaped: the answer to "does this book hold" is no, and every caller was
    already wrapping the call in a try/except to say so in its own words.
    """
    message = f"{check} could not run: {exc}"
    return QaOutcome(ok=False, message=message, status="invalid",
                     data={"status": "invalid", "message": message})


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
        self.snapshot_hits = 0
        self.snapshot_misses = 0

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
        """Read the graph from disk with this instance's store active.

        A whole-graph :class:`Snapshot` short-circuits the read when every document it was
        built from still reads the same. That is a different saving from the parse index
        underneath it: the index makes each document cheap to re-parse, this makes the load
        itself unnecessary. `--no-index` (``use_index=False``) turns both off together — a
        run told to bisect against the cache must not be served a graph by it either.
        """
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
        """The index key this book's graph snapshot is stored under, or ``None`` for no cache.

        The absolute graph root is in the key, unlike every other entry in this store: a
        snapshot holds a `Graph` full of absolute `Path`s, so unlike a document's parse
        products it is *not* the same answer in a second worktree of the same repo, and the
        cross-worktree sharing that key deliberately buys would hand it the wrong tree.
        """
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
        """The stored snapshot when it still holds, counted — ``None`` for every other case.

        Every failure mode is a miss, exactly as in the store beneath: no key, no entry, a
        corrupt payload (the store already reads those as absent), a payload that is not a
        snapshot this build wrote, or one whose dependencies have moved. The cache is an
        optimisation and may only ever cost time, never correctness.
        """
        if key is None:
            return None
        snapshot = self.index.read_key(key)
        if isinstance(snapshot, Snapshot) and snapshot.holds(roots):
            self.snapshot_hits += 1
            return snapshot
        self.snapshot_misses += 1
        return None

    def snapshot_stats(self) -> dict:
        """How often this instance was handed a whole graph rather than loading one.

        Separate from :meth:`index_stats` because they answer different questions and a run
        can be fast for either reason: a snapshot hit means no document was consulted at all,
        so it shows up in the index counts as *silence*, which reads identically to a run that
        never loaded anything.
        """
        return {"hits": self.snapshot_hits, "misses": self.snapshot_misses}

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
        """The next runnable story in ``epic``, or ``None`` (``ostler next-story``).

        ``skip`` — slugs given up this run — are excluded without counting as done, so one
        story failing QA does not strand the rest of the epic. See ``select.next_story``.
        ``need="author"`` asks which story still needs writing — which here means "does not
        yet honor ``registry.STORY_SECTIONS``", read from the document itself.
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

    def doctor(self, *, epic: str | None = None, check_schema: bool = True) -> QaOutcome:
        """The referential-integrity check (``ostler doctor``); ``data`` is the report dict.

        ``ok`` is false when the report carries an error-severity finding — the same verdict
        the CLI's exit code gives. Warnings are findings doctor declined to make blocking.
        """
        try:
            graph = self.graph
        except (OSError, ValueError, RuntimeError) as exc:
            return _unreadable("doctor", exc)
        return doctor.cmd_doctor(graph, epic=epic, check_schema=check_schema)

    def fmt(self, *paths: str | Path, check: bool = False) -> builtins.list[str]:
        """Canonicalize the book's shape; the repo-relative paths that were not already so.

        ``check=True`` writes nothing, which is the mode a test wants: a non-canonical book
        makes every diff against it unreadable, because the next tool through converges on
        the canonical shape and buries the semantic change in bullet reordering.
        """
        result = fmt_mod.run_fmt(self.graph, [str(p) for p in paths], check=check)
        return [str(p.relative_to(self.graph.root)) for p in result.changed]

    def coverage(self, *, inventory: str | Path, surface: str | None = None,
                 waivers: str | Path | None = None) -> QaOutcome:
        """The coverage join (``ostler coverage``); ``data`` is
        ``{covered, total, waived, missing, errors, ...}``.

        ``ok`` is false for an incomplete book *and* for an unreadable inventory, which comes
        back as ``status="invalid"`` rather than as a raise. Never as a clean zero: an empty
        unit list reads downstream as "everything is covered".
        """
        try:
            graph = self.graph
        except (OSError, ValueError, RuntimeError) as exc:
            return _unreadable("coverage", exc)
        return coverage_mod.cmd_coverage(graph, surface=surface, inventory=inventory,
                                         waivers=waivers)

    # -- path resolution ----------------------------------------------------
    def spec_path(self, story: str) -> str:
        """Spec directory for a story, by slug or minted id (``ostler path spec``).

        Keyed by the minted id when the story has one — see :func:`ostler.path.resolve_spec`.
        """
        return path_mod.resolve_spec(self.graph, story)

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
        """The intake list — the file :meth:`backlog` reads, wherever ``docRoots:`` puts it."""
        return path_mod.backlog_path(self.graph)

    def roadmaps_dir(self) -> Path:
        """Where roadmaps live — join a filename onto this rather than spelling the path."""
        return path_mod.roadmaps_root(self.graph)

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

    def scaffold_missing_sections(self, slug: str) -> Result:
        """Add every required story section this story lacks, in contract order (idempotent)."""
        return self._apply(crud.scaffold_missing_sections(self._fresh(), slug))

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

    def set_conflict(self, slug: str, conflict: str) -> Result:
        """Record or clear a story's acceptance-criteria conflict (``ostler conflict``)."""
        return self._apply(crud.set_conflict(self._fresh(), slug, conflict))

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

    def backlog_adopt(self, *, prefix: str | None = None) -> Result:
        """Assign ids to every unnamed bullet in this repo's backlog."""
        return self._apply(backlog_mod.adopt(self._fresh(), prefix))

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
                   exclude_paths: Iterable[str] = (),
                   repositories: Iterable[SourceRepository] = ()) -> QaOutcome:
        """Build the base/head changed-code→OKF obligation packet and write it into
        ``spec`` (``ostler qa context``); ``data`` is the packet.

        ``ok`` is false when the packet carries a ``severity: error`` health finding, and
        when the build itself failed — an unreadable book or a diff git could not produce
        come back as ``status="invalid"`` rather than as a raise.

        ``exclude_paths`` drops repo-relative paths from the diff before it is mapped —
        for a ``head="WORKTREE"`` caller that knows some of the dirt is not its own."""

        return cmd_context(
            self.root, self._resolve(spec), base=base, head=head,
            source_roots=source_roots or {}, features_root=features_root,
            story_file=self._resolve(story_file) if story_file else None,
            exclude_paths=exclude_paths, repositories=tuple(repositories))

    def qa_context_validate(self, *, spec: str | Path) -> QaOutcome:
        """Validate ``qa-okf-context.json`` in ``spec`` (``ostler qa context-validate``);
        ``data["problems"]`` holds the problem strings and is empty when it is valid.

        A missing or unparseable file is one of those problems rather than a raise: the
        question asked is "does this packet hold", and both answers are "no"."""

        return cmd_context_validate(self._resolve(spec))

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
               stop_on_fail: bool = False, label: str | None = None) -> QaOutcome:
        """Execute a ``qa_plan.py`` in batch mode (``ostler qa run``).

        ``label`` makes it a dry run into ``<spec>/qa/<label>/`` that publishes no
        ``qa-evidence.json`` — what ``--out-dir`` does on the CLI."""

        return cmd_run(Path(plan_file), self._resolve(spec) if spec else None,
                       stop_on_fail=stop_on_fail, label=label, root=self.root)

    def qa_report(self, spec: str | Path, *, label: str | None = None,
                  ledger: bool = False) -> QaOutcome:
        """Render a run per acceptance criterion and obligation (``ostler qa report``).

        Rewrites ``<spec>/qa-report.md`` — or ``<spec>/qa/<label>/report.md`` for the dry
        run ``label`` names — and returns the markdown in ``data["report"]``. ``ledger``
        returns the flat time-ordered ledger listing instead and writes nothing."""

        return cmd_report(self._resolve(spec), label=label, ledger=ledger)

    def qa_frames(self, spec: str | Path, *, step: str | None = None,
                  at: float | None = None, target: str | None = None,
                  around: float = 1.0, fps: float = 10.0,
                  label: str | None = None) -> QaOutcome:
        """Write the frames of a run's recording around ``step`` — a step id from the
        report, or a unique fragment of its label — or around the position ``at``
        (``ostler qa frames``). ``data["frames"]`` lists them in order with their
        position in the recording."""

        return cmd_frames(self._resolve(spec), step=step, at=at, target=target,
                          around=around, fps=fps, label=label)

    def qa_tools_catalog(self) -> QaOutcome:
        """This repo's opted-in QA tools, resolved against the machine's stablemate
        config (``ostler qa tools list``). ``data`` is the same
        ``{"tools": [...], "errors": [...]}`` shape the CLI prints; ``ok`` is false when
        a name failed to resolve or a resolved command is not on PATH."""

        return qa_tools_mod.cmd_catalog(self.root)

    # -- schema-checked artifacts (ostler ``artifact …``) -------------------
    def artifact_vet(self, kind: str, spec: str | Path) -> QaOutcome:
        """Validate a workflow artifact against its contract (``ostler artifact vet``).

        ``data`` is the outcome dict (``{"kind","path","status",["problems"],["error"]}``)
        and ``status`` keeps the artifact vocabulary — ``clean`` / ``problems`` / ``error``,
        where ``error`` means the contract could not be evaluated at all, which is not the
        same answer as "no problems"."""
        from ostler.artifact import cmd_vet

        return cmd_vet(kind, self._resolve(spec), self.root)

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
