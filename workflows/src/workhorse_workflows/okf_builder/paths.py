"""Where things are: the docs-repo root, and every path derived from it.

The YAML computed these in three places that had to agree without being able to check
each other — `prepare.py` (the build worklist, the features root, the build directory),
`detect-webapp.py` (the same features root again, plus the walk worklist and the
screenshots directory), and the workflow document itself, which built two more by string
concatenation in an argument list (`"{{ worklist_path }}.source.json"`,
`"{{ features_root }}/coverage-waivers.json"`). A derivation a template owns is a
derivation no test can reach, so all of them are here.

**These are absolute paths, as strings.** `author`'s are repo-relative because its
checkpoint carries them across machines; okf-builder's `prepare` emitted `str(root)` and
every downstream node consumed it as an absolute path, and the walk sub-flow re-derives
its own from `docs_path` rather than being handed them. Keeping the spelling avoids a
whole class of "which root is this relative to" question that the YAML did not have.
"""
from __future__ import annotations

from pathlib import Path

from workhorse.scriptutil import find_docs_root

#: The build's scratch directory under the docs repo: worklists, walkthrough logs.
BUILD_DIRNAME = ".agents/okf-build"


def docs_root(docs_path: str = "") -> Path:
    """The docs repo root: the explicit path, else `CODER_DOCS_PATH`, else the repo walk.

    Both entry points resolve it this way — the main graph's `prepare` and the walk's
    `detect_webapp` — which is what lets the walk run standalone against a book the main
    graph built in an earlier run.
    """
    return Path(find_docs_root(docs_path))


def features_root(root: Path, service: str) -> Path:
    """One service's book, or the whole `docs/features` tree when `service` is empty."""
    base = root / "docs" / "features"
    return base / service if service else base


def build_dir(root: Path) -> Path:
    """Where the worklists live. The caller creates it; this only names it."""
    return root / BUILD_DIRNAME


def worklist_path(root: Path, service: str) -> Path:
    """The drain loop's memory. `all` when no service is named, matching the book."""
    return build_dir(root) / f"{service or 'all'}.worklist.json"


def walk_worklist_path(root: Path, service: str) -> Path:
    """The walk's own worklist — a separate memory, so a walk re-run is not a re-build."""
    return build_dir(root) / f"{service}.walkthrough.json"


def walkthrough_scratch(root: Path) -> Path:
    """Where the shared browser keeps its profile and its log."""
    return build_dir(root) / "walkthrough"


def source_inventory_path(worklist: str | Path) -> Path:
    """The mechanical source inventory, parked beside the worklist that describes it."""
    return Path(f"{worklist}.source.json")


def waivers_path(features: str | Path) -> Path:
    """The committed coverage waivers: which uncovered units are deliberate, and why."""
    return Path(features) / "coverage-waivers.json"


def screenshots_dir(features: str | Path) -> Path:
    """Where a walkthrough turn parks what it saw."""
    return Path(features) / "gui" / "screenshots"


__all__ = [
    "BUILD_DIRNAME",
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
