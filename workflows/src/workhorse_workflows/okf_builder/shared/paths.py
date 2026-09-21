"""Where things are: the docs-repo root, and every path derived from it."""
from __future__ import annotations

from pathlib import Path

from ostler import path as okf_path
from workhorse_workflows.kit import find_docs_root

BUILD_DIRNAME = ".agents/okf-build"


def docs_root(docs_path: str = "", repo_dir: str = "") -> Path:
    """The docs repo root: the explicit path, else the walk up from `repo_dir`."""
    return Path(find_docs_root(docs_path, repo_dir))


def features_root(root: Path, service: str) -> Path:
    """One service's book, or the whole book tree when `service` is empty — ostler's answer."""
    return okf_path.features_root_in(root, service)


def book_scope(root: Path, service: str) -> str:
    """One service's book as a repo-relative prefix, for matching node paths against."""
    book = features_root(root, service)
    try:
        return f"{book.resolve().relative_to(Path(root).resolve()).as_posix()}/"
    except ValueError:
        return f"{book.as_posix()}/"


def build_dir(root: Path) -> Path:
    """Where the worklists live."""
    return root / BUILD_DIRNAME


def ensure_build_dir(root: Path) -> Path:
    """Create the build directory and make it ignore itself."""
    build = build_dir(root)
    build.mkdir(parents=True, exist_ok=True)
    marker = build / ".gitignore"
    if not marker.exists():
        marker.write_text("*\n", encoding="utf-8")
    return build


def worklist_path(root: Path, service: str, scope_id: str = "") -> Path:
    """The drain memory, optionally isolated to one deterministic build scope."""
    name = service or "all"
    suffix = f".{scope_id}" if scope_id else ""
    return build_dir(root) / f"{name}{suffix}.worklist.json"


def ledger_path(root: Path, service: str) -> Path:
    """The result ledger: run state beside the worklist, not a document."""
    return build_dir(root) / f"{service or 'all'}.ledger.json"


def operator_context_path(root: Path, service: str, scope_id: str = "") -> Path:
    """Where a budget stop parks its questions, and where an answer resumes the run."""
    suffix = f".{scope_id}" if scope_id else ""
    return build_dir(root) / f"{service or 'all'}{suffix}.context.md"


def source_inventory_path(worklist: str | Path) -> Path:
    """The mechanical source inventory, parked beside the worklist that describes it."""
    return Path(f"{worklist}.source.json")


def waivers_path(features: str | Path) -> Path:
    """The committed coverage waivers: which uncovered units are deliberate, and why."""
    return okf_path.waivers_path_under(Path(features))


__all__ = [
    "BUILD_DIRNAME",
    "book_scope",
    "build_dir",
    "docs_root",
    "features_root",
    "ledger_path",
    "operator_context_path",
    "source_inventory_path",
    "waivers_path",
    "worklist_path",
]
