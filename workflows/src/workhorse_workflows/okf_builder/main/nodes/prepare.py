"""Resolving the run's setting: the book, the source subtree, and the drain's memory."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from uuid import uuid4

from ostler import Ostler
from workhorse.manifest import BACKEND_SKILL_DIR
from workhorse_workflows.okf_builder.shared import paths
from workhorse_workflows.okf_builder.shared import stubs
from workhorse_workflows.okf_builder.shared.blueprint import blueprint
from workhorse_workflows.okf_builder.shared.schemas import Prepared, SourceRequest
from workhorse_workflows.okf_builder.shared.worklist import book_has_docs, load_worklist


def _ostler_loads(root: Path) -> tuple[bool, str]:
    """Whether ostler can load an OKF graph at this root, and why not if it cannot."""
    try:
        _ = Ostler(root).graph
    except (OSError, ValueError, RuntimeError) as exc:
        return False, f"ostler cannot load a graph at {root}: {exc}"
    return True, ""


_REFERENCES = ("references/node-types", "references/bullet-grammar.md",
               "references/check-vocabulary.md")


def _references_ok(root: Path) -> tuple[bool, str]:
    """Whether an installed ostler-okf skill carries the references corpus."""
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
    worklist_dir: str = "",
) -> Prepared:
    """Resolve paths and initialize (or adopt) the build worklist."""
    root = paths.docs_root(docs_path, repo_dir)
    for name, value in (("since", since), ("recheck_only", recheck_only),
                        ("diff_base", diff_base), ("workspace_file", workspace_file),
                        ("sources", sources)):
        if value:
            logger.warning(
                "%s is retired and ignored — a run reconciles the book to HEAD, and the "
                "per-citation `@digest` stamp is what carries a rebase (%s=%r)",
                name, name, value,
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
    shared = paths.worklist_path(root, service)
    wl = Path(worklist_dir).resolve() / shared.name if worklist_dir else shared
    seed = wl if wl.exists() else shared
    data, reset = load_worklist(seed, service, features)
    if reset:
        logger.warning(
            "discarded a stale worklist at %s — starting fresh for service %r", wl, service
        )
    wl.parent.mkdir(parents=True, exist_ok=True)
    wl.write_text(json.dumps(data, indent=2), encoding="utf-8")
    if worklist_dir:
        alias = shared.with_name(f".{shared.name}.{uuid4().hex}")
        try:
            alias.symlink_to(wl)
            alias.replace(shared)
        finally:
            alias.unlink(missing_ok=True)
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
        book_exists=book_has_docs(features),
        done_baseline=baseline,
        worklist_reset=reset,
        prepare_error=why,
    )


__all__ = ["prepare"]
