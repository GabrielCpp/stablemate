"""Build the diff-to-OKF obligation packet, and check that it holds.

Ports `build-qa-okf-context.py` and `validate-qa-okf-context.py`. One pair of nodes rather
than two, because the YAML's two call sites differed only in their `output_key` argument —
which named the run-context key the emitted JSON landed under. The driver keys a node's
output by node name within the calling flow's own subscope, so `docs` and `qa` each get
their own recorded output from the same node and the argument has no job left.

The two scripts *looked* like they disagreed about how to resolve the docs root — the builder
took `Path(argv).resolve()` or `None`, letting `Ostler` discover its own root when the
argument was blank, where the validator ran it through `find_docs_root`. They did not
actually disagree: the YAML gave both nodes `cwd: docs_repo_path`, so "discover your own
root" and "resolve the docs root" were the same answer.

A node has no per-node cwd. Left as written, a blank `docs_path` made the builder discover
the *orchestrating* repo's graph and diff the story against it — which is what the docs
flow's local-mode test caught, as `'…/docs/features' is outside repository at '…/stablemate'`.
So both resolve through `find_docs_root` here. That is the port rule this package already
follows everywhere else: the repo a node works on is a parameter, never the process's cwd.
"""
from __future__ import annotations

import logging
from pathlib import Path

from ostler import Ostler
from workhorse_workflows.kit import find_docs_root
from workhorse_workflows.coder.shared.blueprint import blueprint
from workhorse_workflows.coder.shared.qa_support import notes_for, parse_source_roots
from workhorse_workflows.coder.shared.schemas.okf import OkfContextResult
from workhorse_workflows.coder.shared.worktree import untouched_since


@blueprint.node
def build_okf_context(
    logger: logging.Logger,
    spec_dir: str = "",
    story_file: str = "",
    features_root: str = "",
    source_roots: tuple[str, ...] = (),
    base: str = "HEAD",
    head: str = "WORKTREE",
    docs_path: str = "",
    repo_dir: str = "",
    preexisting: tuple[str, ...] = (),
) -> OkfContextResult:
    """Map a diff onto the OKF graph and write the obligation packet into the spec dir.

    `source_roots` are `"SURFACE=PATH"` entries. They arrived as a JSON-encoded string under
    the YAML engine — a workflow var is a string — and the encoding is gone here along with
    the decoder's "was not valid JSON" warning, which had nothing left to guard.

    `preexisting` is `snapshot_worktree_state`'s reading from before this story's first dev
    turn. The default `HEAD..WORKTREE` diff cannot tell this story's uncommitted work from
    an abandoned story's, so the paths in it that still hold the same bytes are dropped from
    the diff before it is mapped. Both consumers of this packet were wrong without it: the
    docs gate demanded grounding for the other story's symbols, and the QA planner wrote
    scenarios for them. Excluding here rather than in either consumer is what keeps
    `qa-okf-context.json` and the rendered `.md` beside it saying the same thing.
    """
    docs_root = find_docs_root(docs_path, repo_dir)
    inherited = sorted(untouched_since(Path(docs_root).resolve(), tuple(preexisting)))
    if inherited:
        logger.info(
            "excluding %d path(s) that were already dirty when the story started: %s",
            len(inherited),
            ", ".join(inherited),
        )
    outcome = Ostler(docs_root).qa_context(
        base=base,
        head=head,
        spec=spec_dir,
        source_roots=parse_source_roots(list(source_roots)),
        features_root=features_root,
        story_file=story_file or None,
        exclude_paths=inherited,
    )
    status = "passed" if outcome.ok else "invalid"
    logger.info("qa context build for spec_dir=%s: status=%s", spec_dir, status)
    notes = notes_for(
        outcome,
        "QA OKF context generated." if status == "passed" else "QA OKF context generation failed.",
    )
    return OkfContextResult(status=status, notes=notes, ostler=outcome.data)


@blueprint.node
def validate_okf_context(
    logger: logging.Logger,
    spec_dir: str = "",
    build_status: str = "invalid",
    docs_path: str = "",
    repo_dir: str = "",
) -> OkfContextResult:
    """Re-check the packet the builder wrote, and carry the builder's verdict forward.

    Three things have to be true for `passed`: ostler validated it, ostler reported it valid,
    and the build that produced it passed. The last is why `build_status` is a parameter — a
    packet can validate cleanly and still have been generated from a failed run.
    """
    docs_root = find_docs_root(docs_path, repo_dir)
    outcome = Ostler(docs_root).qa_context_validate(spec=spec_dir)
    status = "passed" if outcome.ok and build_status == "passed" else "invalid"
    notes = notes_for(
        outcome,
        "QA OKF context is valid." if status == "passed" else "QA OKF context is invalid.",
    )
    logger.info("qa context-validate for %s returned status=%s", spec_dir, status)
    return OkfContextResult(status=status, notes=notes, ostler=outcome.data)


__all__ = ["build_okf_context", "validate_okf_context"]
