"""Resolving the run's setting: the book, the source subtree, and the drain's memory.

Ported from `base-library/workflows/okf-builder/scripts/prepare.py`. The four positional
`sys.argv` entries become typed parameters and the JSON envelope becomes a `Prepared`,
which the workflow's `setup()` returns — so this is the one node whose result every
state can read.
"""
from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path

from ostler import Ostler
from workhorse.manifest import BACKEND_SKILL_DIR
from workhorse_workflows.okf_builder.main.nodes.incremental import prepare_incremental
from workhorse_workflows.okf_builder.shared import paths
from workhorse_workflows.okf_builder.shared import stubs
from workhorse_workflows.okf_builder.shared.blueprint import blueprint
from workhorse_workflows.okf_builder.shared.schemas import Prepared, SourceRequest
from workhorse_workflows.okf_builder.shared.worklist import load_worklist


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


def _git(root: Path, *args: str) -> str:
    """One git read, or `OSError` with git's own words — the caller decides what it means."""
    result = subprocess.run(
        ["git", *args], cwd=root, capture_output=True, text=True, timeout=120, check=False
    )
    if result.returncode != 0:
        raise OSError(result.stderr.strip() or f"git {' '.join(args)} failed")
    return result.stdout


def _diff_scope(root: Path, base: str) -> tuple[list[str] | None, str]:
    """The squashed-diff scope against *base*: the paths, or `None` for the whole tree.

    On a branch, the scope is the squashed diff between the branch and the base — every
    path the branch (plus the working tree, including untracked files) touched since the
    merge base. Sitting *on* the base itself, the squash of every commit is the whole
    tree, so there is no filter to apply and the answer is `None`, a full scan.

    A scope that was asked for but cannot be computed — an unknown rev, unrelated
    histories, not a checkout — comes back as an error, never as a silent full scan: a
    run that claims to have measured a diff must actually have had one.
    """
    try:
        _git(root, "rev-parse", "--verify", f"{base}^{{commit}}")
        # Judged by name, not by commit equality: a fresh branch sitting at the base's
        # tip is still a branch, and its scope is its (possibly empty) working-tree diff.
        if _git(root, "branch", "--show-current").strip() == base:
            return None, ""
        merge_base = _git(root, "merge-base", base, "HEAD").strip()
        changed = set(_git(root, "diff", "--name-only", merge_base).splitlines())
        changed.update(_git(root, "ls-files", "--others", "--exclude-standard").splitlines())
    except (OSError, subprocess.SubprocessError) as exc:
        return None, f"cannot compute the diff scope against {base!r}: {exc}"
    return sorted(path for path in changed if path), ""


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
    """
    root = paths.docs_root(docs_path, repo_dir)
    incremental = bool(story or sources)
    if bool(story) != bool(sources):
        return Prepared(
            repo_root=str(root),
            service=service,
            mode="incremental",
            prepare_error="story-aware incremental mode requires both story and sources",
        )
    if incremental:
        return prepare_incremental(
            logger,
            root,
            service,
            story,
            workspace_file,
            repo_dir,
            sources,
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
    if diff_base:
        scope, scope_error = _diff_scope(root, diff_base)
        if scope is None and not scope_error:
            logger.info(
                "diff scope: on %r itself, the squash of every commit is the whole "
                "tree — running a full scan",
                diff_base,
            )
        elif scope is not None:
            scope_file = paths.diff_scope_path(root, service)
            scope_file.write_text(
                json.dumps({"base": diff_base, "paths": scope}, indent=2) + "\n",
                encoding="utf-8",
            )
            scope_path = str(scope_file)
            scope_count = len(scope)
            logger.info(
                "diff scope against %r: %d changed path(s) → %s",
                diff_base,
                scope_count,
                scope_file,
            )
    ostler_ok, why = _ostler_loads(root)
    if ostler_ok:
        ostler_ok, why = _references_ok(root)
    if ostler_ok and scope_error:
        # A scope that was asked for but could not be computed blocks the run — a build
        # that silently widened to a full scan would claim a measurement it never took.
        ostler_ok, why = False, scope_error
        logger.warning("refusing to widen a diff-scoped build to a full scan: %s", why)
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
        diff_scope_path=scope_path,
        diff_scope_count=scope_count,
        prepare_error=why,
    )
__all__ = ["prepare"]
