"""Resolving the run's setting: the book, the source subtree, and the drain's memory.

Ported from `base-library/workflows/okf-builder/scripts/prepare.py`. The four positional
`sys.argv` entries become typed parameters and the JSON envelope becomes a `Prepared`,
which the workflow's `setup()` returns — so this is the one node whose result every
state can read.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from ostler import Ostler
from workhorse.manifest import BACKEND_SKILL_DIR
from workhorse_workflows.okf_builder.shared import paths
from workhorse_workflows.okf_builder.shared import stubs
from workhorse_workflows.okf_builder.shared.blueprint import blueprint
from workhorse_workflows.okf_builder.shared.schemas import Prepared


def _book_has_docs(features: Path) -> bool:
    """Whether the book exists as more than a directory entry."""
    return features.is_dir() and any(features.rglob("*.md"))


def _load_worklist(wl: Path, service: str, features: Path) -> tuple[dict, bool]:
    """The worklist to drain, and whether a stale one was discarded.

    The worklist is keyed to the book it remembers: it is a memory of work whose product
    is the book, so a worklist carrying `done` items for a book that no longer exists is
    not a resume but a false memory — and its `done` counter makes a bounded run
    instantly over-budget and hand out zero items. Reuse therefore requires the stamped
    service to match and the remembered work to still have a product.
    """
    fresh: dict = {"service": service, "book": str(features), "items": []}
    if not wl.exists():
        return fresh, False
    try:
        data = json.loads(wl.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return fresh, True
    if not isinstance(data, dict) or not isinstance(data.get("items"), list):
        return fresh, True
    if data.get("service", service) != service:
        return fresh, True
    done = sum(1 for i in data["items"] if i.get("status") == "done")
    if done and not _book_has_docs(features):
        return fresh, True
    data.setdefault("service", service)
    data["book"] = str(features)
    return data, False


def _ostler_loads(root: Path) -> tuple[bool, str]:
    """Whether ostler can load an OKF graph at this root, and why not if it cannot.

    This is about the *graph*, not about ostler: an interpreter that cannot import ostler
    never gets here, because the workflow declares `dist: ostler` in `requires:` and
    workhorse refuses to start the run. What remains — a root with no book, an unreadable
    one — is a real, reportable state of the repo, and is what `ostler_ok` branches on.
    """
    try:
        _ = Ostler(root).graph
    except (OSError, ValueError, RuntimeError) as exc:
        return False, f"ostler cannot load a graph at {root}: {exc}"
    return True, ""


#: What the installed ostler-documentation skill must carry for the build's prompts to
#: point anywhere real: the per-type reference pages plus the two grammar sheets.
_REFERENCES = ("references/node-types", "references/bullet-grammar.md",
               "references/check-vocabulary.md")


def _references_ok(root: Path) -> tuple[bool, str]:
    """Whether an installed ostler-documentation skill carries the references corpus.

    The prompts hand agents the path `<skill_dir>/ostler-documentation/references/…` as
    the per-type authority. On a repo whose skills predate the corpus, that path does not
    exist, and a real run showed what happens next: every turn greps for it, finds
    nothing, and improvises the contract from memory — the exact drift the corpus exists
    to stop. A skill that is installed but incomplete is therefore a blocked run, not a
    degraded one, and the fix is a farrier refresh, not agent persistence.
    """
    installs = [
        root / d / "ostler-documentation"
        for d in BACKEND_SKILL_DIR.values()
        if (root / d / "ostler-documentation").is_dir()
    ]
    if not installs:
        return False, (
            f"no installed ostler-documentation skill under {root} — run a farrier "
            "refresh so the build's prompts have their per-type references"
        )
    for skill in installs:
        missing = [ref for ref in _REFERENCES if not (skill / ref).exists()]
        if missing:
            return False, (
                f"the installed skill at {skill} is missing {', '.join(missing)} — "
                "it predates the references corpus; run a farrier refresh before "
                "building against it"
            )
    return True, ""


@blueprint.node(stub=stubs.prepared)
def prepare(
    logger: logging.Logger,
    docs_path: str = "",
    service: str = "",
    source_path: str = "",
    source_excludes: str = "",
    repo_dir: str = "",
) -> Prepared:
    """Resolve paths and initialize (or adopt) the build worklist.

    The worklist is the crawl's memory: a list of typed items `{kind,target,context,
    status}` where an item's investigation may append deeper items (a surface spawns its
    elements, an element spawns its handler layer, a layer spawns its callees).

    Every unusable setting comes back as a `Prepared` with `ostler_ok` false and a
    `prepare_error` saying which one — `start()` is where that becomes a failed run.
    """
    root = paths.docs_root(docs_path, repo_dir)
    source_rel = source_path or service
    source = (root / source_rel).resolve() if source_rel else root.resolve()
    try:
        source.relative_to(root.resolve())
    except ValueError:
        logger.warning(
            "source path %s is outside the repo root %s — refusing to prepare", source, root
        )
        return Prepared(
            repo_root=str(root),
            service=service,
            prepare_error=f"source path {source} is outside the repo root {root}",
        )
    if not source.is_dir():
        logger.warning("source root %s is not a directory — refusing to prepare", source)
        return Prepared(
            repo_root=str(root),
            service=service,
            source_root=str(source),
            prepare_error=f"source root {source} is not a directory",
        )
    features = paths.features_root(root, service)
    paths.ensure_build_dir(root)
    wl = paths.worklist_path(root, service)
    data, reset = _load_worklist(wl, service, features)
    if reset:
        # The stamped memory was void (wrong service, unreadable, or a book that no longer
        # exists). Silently starting from zero would look like a resume that lost its work.
        logger.warning(
            "discarded a stale worklist at %s — starting fresh for service %r", wl, service
        )
    wl.write_text(json.dumps(data, indent=2), encoding="utf-8")
    # The run's budget baseline: `max_items` bounds *this* run's investigations, not the
    # worklist's lifetime total, so a resume gets its own allowance.
    baseline = sum(1 for i in data["items"] if i.get("status") == "done")
    logger.info(
        "prepared %s: book %s, source %s, worklist %s (%d items, %d done at baseline)",
        service or "(whole tree)",
        features,
        source,
        wl,
        len(data["items"]),
        baseline,
    )
    ostler_ok, why = _ostler_loads(root)
    if ostler_ok:
        ostler_ok, why = _references_ok(root)
    if not ostler_ok:
        logger.warning("the build cannot start and will branch away: %s", why)
    return Prepared(
        worklist_path=str(wl),
        features_root=str(features),
        repo_root=str(root),
        source_root=str(source),
        service=service,
        source_excludes=source_excludes,
        ostler_ok=ostler_ok,
        done_baseline=baseline,
        worklist_reset=reset,
        prepare_error=why,
    )


__all__ = ["prepare"]
