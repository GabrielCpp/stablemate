"""``ostler path`` — resolve slugs to canonical filesystem paths.

Uses the configured ``doc_roots`` from ostler.yml / agents.yml, so a repo that moved its
epics out of ``docs/`` is followed rather than assumed away. The ``resolve_*`` functions
the CLI prints return paths relative to the repo root; everything else returns an absolute
path built on the root it was handed.

**This module is where a doc-tree path is derived, for every caller including the
workflows.** A workflow that needs the epics index, an epic folder, a story folder, the
backlog file or a feature book joins a *filename it owns* onto a directory from here; it
does not spell ``docs/epics`` itself. Two derivations of the same location is the failure
this avoids — the second one does not learn about ``docRoots:``, and the symptom is a run
writing into a directory nothing reads.

Each derivation comes in up to three spellings, and which one a caller wants is decided by
what it already holds:

* ``<name>_in(root, ...)`` — graph-free, taking the **repo root**. Loading the graph reads
  every markdown file under every doc root; deriving a path may not cost that.
* ``<name>(graph, ...)`` — the same answer against an already-loaded graph, so a caller
  that has one does not re-read the config.
* ``<name>_under(container, ...)`` — taking the containing directory itself, for a caller
  that was *told* which one to use: a workflow run with an operator-supplied ``epics_dir``,
  or a caller already holding the feature book. The override still gets ostler's rules
  applied inside it — an epic is still matched by number-or-slug — which is what keeps an
  override from becoming a second, dumber derivation.
"""

from __future__ import annotations

from pathlib import Path

from ostler import model, registry
from ostler.model import Graph


def doc_root_in(root: Path, kind: str) -> Path:
    """The configured directory for doc kind *kind* (``epics``, ``features``, …) under *root*.

    ``kinds=()`` skips the template registry: the four built-in keys are always present, and
    a path derivation should not pay for reading ``.agents/templates.yml`` to learn that.
    """
    return model.doc_roots(root, kinds=())[kind]


def epics_root_in(root: Path) -> Path:
    """Where epics live under *root* — ``docs/epics`` unless ``docRoots:`` says otherwise."""
    return doc_root_in(root, "epics")


def epics_root(graph: Graph) -> Path:
    """Where epics live in this graph."""
    return graph.doc_roots["epics"]


def features_root_in(root: Path, service: str = "") -> Path:
    """The feature book under *root*, scoped to one *service* when the repo has several.

    A multi-repo workspace books each service separately (``docs/features/api-service``);
    a single-service repo passes no service and books straight into ``docs/features``.
    """
    base = doc_root_in(root, "features")
    return base / service if service else base


def features_root(graph: Graph, service: str = "") -> Path:
    """The feature book in this graph, scoped to one *service* when there is one."""
    base = graph.doc_roots.get("features") or (graph.root / "docs" / "features")
    return base / service if service else base


def specs_root_in(root: Path) -> Path:
    """Where story specs live under *root*."""
    return doc_root_in(root, "specs")


def roadmaps_root_in(root: Path) -> Path:
    """Where roadmaps live under *root* — ``docs/roadmaps`` unless ``docRoots:`` says otherwise."""
    return doc_root_in(root, "roadmaps")


def roadmaps_root(graph: Graph) -> Path:
    """Where roadmaps live in this graph."""
    return graph.doc_roots["roadmaps"]


def backlog_path_in(root: Path) -> Path:
    """The intake list, ``docs/backlog.md`` under *root* unless ``docRoots:`` says otherwise.

    The one ``docRoots:`` entry naming a file rather than a directory, because there is one
    backlog and not a tree of them. It is configured there rather than fixed here for the
    reason every other location is: a run told to keep its own worklist somewhere else used
    to say so with a parameter, and then wrote a list ``ostler backlog`` and ``doctor`` could
    not see. An intake list being *unfiled* — nobody has decided which epic an item belongs
    to — is a fact about the items, not about where the file sits.
    """
    return doc_root_in(root, "backlog")


def backlog_path(graph: Graph) -> Path:
    """The intake list for this graph."""
    return graph.doc_roots["backlog"]


def epics_index_in(root: Path) -> Path:
    """The epic queue, ``index.md`` in the epics root — its front entry is the current epic."""
    return epics_root_in(root) / "index.md"


def epics_index(graph: Graph) -> Path:
    """The epic queue for this graph."""
    return epics_root(graph) / "index.md"


def resolve_spec(graph: Graph, story: str) -> str:
    """Resolve a story (slug or minted id) to its spec directory path (relative to root).

    The directory is keyed by the **minted id** (``ACME-01H…``) — the identity that survives
    a slug rename and matches the trailer a commit carries — not the slug the caller may
    have handed in. Two fallbacks keep old trees readable: a story that predates minted ids
    keys by its slug, and a spec already on disk under the slug stays where its readers know
    it rather than being shadowed by an empty id-keyed path.
    """
    specs_root = graph.doc_roots["specs"]
    key = story
    found = graph.find_story(story)
    if found is not None:
        _, s = found
        key = s.eid or s.slug
        if key != s.slug and not (specs_root / key).is_dir() and (specs_root / s.slug).is_dir():
            key = s.slug
    return str(specs_root.relative_to(graph.root) / key)


def epic_dirs_under(epics_root: Path) -> list[Path]:
    """Every epic directory directly under *epics_root*, in name order.

    The ``_under`` family takes the epics directory itself rather than the repo root, for
    the one caller that has been *told* which directory to use — a workflow whose operator
    passed an explicit epics path. It is still ostler's rule being applied to it; what the
    caller overrides is which directory, never how a name resolves inside it.
    """
    if not epics_root.is_dir():
        return []
    return [d for d in sorted(epics_root.iterdir()) if (d / "epic.md").is_file()]


def epic_dirs_in(root: Path) -> list[Path]:
    """Every epic directory under *root*, in name order — creation order, once numbered."""
    return epic_dirs_under(epics_root_in(root))


def epic_dirs(graph: Graph) -> list[Path]:
    """Every epic directory on disk, in name order — creation order, once numbered."""
    return epic_dirs_under(epics_root(graph))


def epic_dir_under(epics_root: Path, name: str) -> Path:
    """:func:`epic_dir_in`'s resolution against an epics directory the caller names."""
    name = name.strip()
    if (not name or (epics_root / name / "epic.md").is_file()
            or registry.epic_seq(name) is not None):
        return epics_root / name
    slug = registry.epic_slug(name)
    return next((d for d in epic_dirs_under(epics_root) if registry.epic_slug(d.name) == slug),
                epics_root / name)


def epic_dir_in(root: Path, name: str) -> Path:
    """The directory of epic *name* under *root*, by number or by bare slug.

    Epic directories are created numbered (`0001-checkout-flow`, see
    :func:`registry.epic_dir_name`), but the number is presentation, not identity: a bare
    `checkout-flow` still names that epic here, which is what keeps older un-numbered
    epics, hand-written `index.md` lines and slug-only prompts working. A numbered name is
    taken literally — it already says which epic it means, and silently re-pointing
    `0002-x` at `0001-x` would hide a typo. A name that resolves to nothing comes back as
    ``epics_root / name`` so callers keep reporting "no epic '<name>'" against the name
    they were handed.

    Graph-free so that a caller holding only a repo root — a workflow resolving a gate's
    context file, say — resolves an epic folder by the same rule rather than re-deriving a
    second, subtly different one. :func:`epic_dir` is this function against an already
    loaded graph.
    """
    return epic_dir_under(epics_root_in(root), name)


def epic_dir(graph: Graph, name: str) -> Path:
    """The directory of epic *name*, whether or not the caller knows its number."""
    return epic_dir_under(epics_root(graph), name)


def story_dir_in(root: Path, epic: str, slug: str) -> Path:
    """The folder of story *slug* in *epic*: ``<epic-dir>/stories/<slug>``.

    The story's own files — ``story.md``, the run's context and feedback notes — are joined
    onto this by whoever owns their names; the *location* is not theirs to spell.
    """
    return epic_dir_in(root, epic) / "stories" / slug


def story_dir(graph: Graph, epic: str, slug: str) -> Path:
    """The folder of story *slug* in *epic* for this graph."""
    return epic_dir(graph, epic) / "stories" / slug


def story_dir_under(epic_dir_path: Path, slug: str) -> Path:
    """The folder of story *slug* under an epic directory the caller already holds."""
    return epic_dir_path / "stories" / slug


def waivers_path_under(features_root_path: Path) -> Path:
    """A book's coverage waivers, for a caller that already holds the book directory.

    Inside the book on purpose: a waiver is a claim about *these* features, and a book moved
    or copied to another repo has to carry its waivers with it or come back red.
    """
    return features_root_path / "coverage-waivers.json"


def waivers_path_in(root: Path, service: str = "") -> Path:
    """A feature book's coverage waivers, ``coverage-waivers.json`` beside the book itself."""
    return waivers_path_under(features_root_in(root, service))


def waivers_path(graph: Graph, service: str = "") -> Path:
    """This graph's coverage waivers, for one *service*'s book when there is one."""
    return waivers_path_under(features_root(graph, service))


def screenshots_dir_under(features_root_path: Path) -> Path:
    """A book's registered screenshots, for a caller that already holds the book directory."""
    return features_root_path / "gui" / "screenshots"


def screenshots_dir_in(root: Path, service: str = "") -> Path:
    """Where a walkthrough's registered screenshots live: ``<book>/gui/screenshots``."""
    return screenshots_dir_under(features_root_in(root, service))


def screenshots_dir(graph: Graph, service: str = "") -> Path:
    """This graph's registered screenshots, for one *service*'s book when there is one."""
    return screenshots_dir_under(features_root(graph, service))


def resolve_epic(graph: Graph, name: str) -> str:
    """Resolve an epic name to its directory path (relative to root)."""
    return str(epic_dir(graph, name).relative_to(graph.root))


def resolve_story(graph: Graph, epic: str, slug: str) -> str:
    """Resolve an epic + story slug to the story.md path (relative to root)."""
    return str(epic_dir(graph, epic).relative_to(graph.root) / "stories" / slug / "story.md")


def resolve_branch(slug: str, *, epic: bool = False) -> str:
    """Resolve a slug to its git branch name.

    An epic branches under ``feat/`` — the one prefix in the system. A story
    branches on its bare id: ids are minted by ostler and carry a repo prefix,
    so they are already globally unique and need no namespace of their own.

    An epic's *sequence number* is dropped: `0003-checkout-flow` branches as
    `feat/checkout-flow`. The number orders the folder listing and says nothing a branch
    name needs, and leaving it in would give the same epic two branch names depending on
    whether the caller had resolved the directory yet.
    """
    if epic:
        return f"feat/{registry.epic_slug(slug)}"
    return slug
