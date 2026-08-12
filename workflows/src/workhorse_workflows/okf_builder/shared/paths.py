"""Where things are: the docs-repo root, and every path derived from it.

The YAML computed these in three places that had to agree without being able to check
each other — `prepare.py` (the build worklist, the features root, the build directory),
`detect-webapp.py` (the same features root again, plus the walk worklist and the
screenshots directory), and the workflow document itself, which built two more by string
concatenation in an argument list (`"{{ worklist_path }}.source.json"`,
`"{{ features_root }}/coverage-waivers.json"`). A derivation a template owns is a
derivation no test can reach, so all of them are here.

**Where a document lives is ostler's answer, not this module's.** The book, its waivers
and its screenshots come from `ostler.path`, so a repo that moved `docs/features` with
`docRoots:` is followed and the builder writes where `ostler coverage` reads. What is
genuinely this workflow's stays here: `.agents/okf-build` and the worklist filenames
under it are run artifacts, not documents, and ostler has no opinion about them.

**These are absolute paths, as strings.** `author`'s are repo-relative because its
checkpoint carries them across machines; okf-builder's `prepare` emitted `str(root)` and
every downstream node consumed it as an absolute path, and the walk sub-flow re-derives
its own from `docs_path` rather than being handed them. Keeping the spelling avoids a
whole class of "which root is this relative to" question that the YAML did not have.
"""
from __future__ import annotations

from pathlib import Path

from ostler import path as okf_path
from workhorse.scratch import scratch_dir
from workhorse_workflows.kit import find_docs_root

#: The build's run state under the docs repo: worklists and the source inventory.
#: Machine scratch is NOT here — see :func:`walkthrough_scratch`.
BUILD_DIRNAME = ".agents/okf-build"


def docs_root(docs_path: str = "", repo_dir: str = "") -> Path:
    """The docs repo root: the explicit path, else the walk up from `repo_dir`.

    Both entry points resolve it this way — the main graph's `prepare` and the walk's
    `detect_webapp` — which is what lets the walk run standalone against a book the main
    graph built in an earlier run.

    Neither argument is read from the environment: both are run inputs that travel down
    from the workflow, per the rule in `workflows/README.md`.
    """
    return Path(find_docs_root(docs_path, repo_dir))


def features_root(root: Path, service: str) -> Path:
    """One service's book, or the whole book tree when `service` is empty — ostler's answer."""
    return okf_path.features_root_in(root, service)


def book_scope(root: Path, service: str) -> str:
    """One service's book as a repo-relative prefix, for matching node paths against.

    The graph reports node paths relative to the docs root, so a substring test needs the
    book spelled the same way — derived here rather than written out, so a repo that moved
    its book still matches instead of silently walking nothing.
    """
    book = features_root(root, service)
    try:
        return f"{book.resolve().relative_to(Path(root).resolve()).as_posix()}/"
    except ValueError:
        return f"{book.as_posix()}/"


def build_dir(root: Path) -> Path:
    """Where the worklists live. The caller creates it; this only names it."""
    return root / BUILD_DIRNAME


def ensure_build_dir(root: Path) -> Path:
    """Create the build directory and make it ignore itself. Returns it.

    The self-ignore is load-bearing, not tidiness. What is left here after the browser
    profile moved to the cache is still run state, not documents — worklists, the source
    inventory — and it still lives *inside* the docs repo. A coder run in the same
    checkout commits with `commit_all` (`git add -A`), so anything here that the repo
    does not ignore gets swept into a story commit and is then in every clone's history
    forever, where only a rewrite removes it. Writing the `.gitignore` here means a repo
    is protected the first time okf-builder runs in it, rather than after someone
    notices.
    """
    build = build_dir(root)
    build.mkdir(parents=True, exist_ok=True)
    marker = build / ".gitignore"
    if not marker.exists():
        marker.write_text("*\n", encoding="utf-8")
    return build


def worklist_path(root: Path, service: str) -> Path:
    """The drain loop's memory. `all` when no service is named, matching the book."""
    return build_dir(root) / f"{service or 'all'}.worklist.json"


def walk_worklist_path(root: Path, service: str) -> Path:
    """The walk's own worklist — a separate memory, so a walk re-run is not a re-build."""
    return build_dir(root) / f"{service}.walkthrough.json"


def walkthrough_scratch(root: Path) -> Path:
    """Where the shared browser keeps its profile and its log — outside the repo entirely.

    A Chrome profile is tens of thousands of files that no resume needs and no reader
    wants: pure machine state, which is the stablemate cache's definition. Keeping it in
    the docs repo meant every process sharing that checkout had to be trusted not to
    commit it, and `commit_all`'s `git add -A` is not that. Out here the question does not
    arise — there is nothing in the repo to ignore, and deleting the cache is free.
    """
    return scratch_dir("okf-walkthrough", root)


def source_inventory_path(worklist: str | Path) -> Path:
    """The mechanical source inventory, parked beside the worklist that describes it."""
    return Path(f"{worklist}.source.json")


def waivers_path(features: str | Path) -> Path:
    """The committed coverage waivers: which uncovered units are deliberate, and why.

    Takes the book rather than the root because both callers already hold one, resolved
    by :func:`features_root`; the filename inside it is ostler's too.
    """
    return okf_path.waivers_path_under(Path(features))


def screenshots_dir(features: str | Path) -> Path:
    """Where a walkthrough turn parks what it saw, inside the book it documents."""
    return okf_path.screenshots_dir_under(Path(features))


__all__ = [
    "BUILD_DIRNAME",
    "book_scope",
    "build_dir",
    "docs_root",
    "features_root",
    "screenshots_dir",
    "source_inventory_path",
    "waivers_path",
    "walk_worklist_path",
    "walkthrough_scratch",
    "worklist_path",
]
