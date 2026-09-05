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

from ostler import Ostler, source_snapshots
from workhorse.manifest import BACKEND_SKILL_DIR
from workhorse_workflows.okf_builder.shared import paths
from workhorse_workflows.okf_builder.shared import stubs
from workhorse_workflows.okf_builder.shared.blueprint import blueprint
from workhorse_workflows.okf_builder.shared.schemas import Prepared, SourceRequest
from workhorse_workflows.okf_builder.shared.worklist import book_has_docs, load_worklist


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


#: What the installed ostler-okf skill must carry for the build's prompts to
#: point anywhere real: the per-type reference pages plus the two grammar sheets.
_REFERENCES = ("references/node-types", "references/bullet-grammar.md",
               "references/check-vocabulary.md")


def _references_ok(root: Path) -> tuple[bool, str]:
    """Whether an installed ostler-okf skill carries the references corpus.

    The prompts hand agents the path `<skill_dir>/ostler-okf/references/…` as
    the per-type authority. On a repo whose skills predate the corpus, that path does not
    exist, and a real run showed what happens next: every turn greps for it, finds
    nothing, and improvises the contract from memory — the exact drift the corpus exists
    to stop. A skill that is installed but incomplete is therefore a blocked run, not a
    degraded one, and the fix is a farrier refresh, not agent persistence.
    """
    # Farrier installs the skill under the consuming repo's prefix
    # (`<repo>-ostler-okf`), so the directory name is matched by suffix.
    installs = [
        p
        for d in BACKEND_SKILL_DIR.values()
        if (root / d).is_dir()
        for p in sorted((root / d).iterdir())
        if p.is_dir() and (p.name == "ostler-okf" or p.name.endswith("-ostler-okf"))
    ]
    if not installs:
        return False, (
            f"no installed ostler-okf skill under {root} — run a farrier "
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
    since: str = "",
    recheck_only: bool = False,
    diff_base: str = "",
    story: str = "",
    workspace_file: str = "",
    sources: tuple[SourceRequest, ...] = (),
) -> Prepared:
    """Resolve paths and initialize (or adopt) the build worklist.

    The worklist is the crawl's memory: a list of typed items `{kind,target,context,
    status}` where an item's investigation may append deeper items (a surface spawns its
    elements, an element spawns its handler layer, a layer spawns its callees).

    Every unusable setting comes back as a `Prepared` with `ostler_ok` false and a
    `prepare_error` saying which one — `start()` is where that becomes a failed run.

    `recheck_only`, `diff_base`, `workspace_file` and `sources` are **retired and unread**.
    `story` remains only as commit provenance. These inputs selected between two prepare
    functions and three ways of computing what
    was stale; one reconcile against the book's own watermark answers all of them, `since`
    is the only narrowing left, and `recheck_only` falls out of the book already existing.
    They stay declared for one release because deleting a field kills every in-flight run
    on reload, so a run that passes one gets a warning, not a crash.
    """
    root = paths.docs_root(docs_path, repo_dir)
    for name, value in (("recheck_only", recheck_only), ("diff_base", diff_base),
                        ("workspace_file", workspace_file), ("sources", sources)):
        if value:
            logger.warning(
                "%s is retired and ignored — a run reconciles the book to HEAD, and "
                "`since` is the only narrowing (%s=%r)", name, name, value
            )
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
    data, reset = load_worklist(wl, service, features)
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
    scope_path = ""
    scope_count = 0
    scope_error = ""
    if since:
        changed = source_snapshots.changed_since(root, since)
        if changed is None:
            # A narrowing that was asked for but cannot be computed blocks the run — a
            # build that silently widened to a full scan would claim a measurement it
            # never took, and one that silently narrowed to nothing would claim a clean
            # book it never read.
            scope_error = (
                f"cannot compute what changed since {since!r} — git could not resolve it "
                f"in {root}"
            )
        else:
            scope_file = paths.diff_scope_path(root, service)
            scope_file.write_text(
                json.dumps({"base": since, "paths": sorted(changed)}, indent=2) + "\n",
                encoding="utf-8",
            )
            scope_path = str(scope_file)
            scope_count = len(changed)
            logger.info(
                "narrowed to what changed since %r: %d path(s) → %s",
                since, scope_count, scope_file,
            )
    ostler_ok, why = _ostler_loads(root)
    if ostler_ok:
        ostler_ok, why = _references_ok(root)
    if ostler_ok and scope_error:
        ostler_ok, why = False, scope_error
        logger.warning("refusing to widen a narrowed build to a full scan: %s", why)
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
        book_exists=book_has_docs(features),
        done_baseline=baseline,
        worklist_reset=reset,
        diff_scope_path=scope_path,
        diff_scope_count=scope_count,
        prepare_error=why,
    )


__all__ = ["prepare"]
