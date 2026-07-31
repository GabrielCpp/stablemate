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

from workhorse.scriptutil import find_docs_root
from workhorse_workflows.coder import ostler_qa
from workhorse_workflows.coder.nodes._blueprint import blueprint
from workhorse_workflows.coder.schemas.okf import OkfContextResult


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
) -> OkfContextResult:
    """Map a diff onto the OKF graph and write the obligation packet into the spec dir.

    `source_roots` are `"SURFACE=PATH"` entries. They arrived as a JSON-encoded string under
    the YAML engine — a workflow var is a string — and the encoding is gone here along with
    the decoder's "was not valid JSON" warning, which had nothing left to guard.
    """
    docs_root = find_docs_root(docs_path, repo_dir)
    returncode, payload, stderr = ostler_qa.qa_context(
        spec_dir,
        base=base,
        head=head,
        features_root=features_root,
        story_file=story_file,
        source_roots=list(source_roots),
        docs_root=docs_root,
    )
    status = "passed" if returncode == 0 and payload.get("status") != "invalid" else "invalid"
    logger.info("qa context build for spec_dir=%s: status=%s", spec_dir, status)
    notes = ostler_qa.notes_for(
        payload,
        stderr,
        "QA OKF context generated." if status == "passed" else "QA OKF context generation failed.",
    )
    return OkfContextResult(status=status, notes=notes, ostler=payload)


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
    returncode, payload, stderr = ostler_qa.qa_context_validate(spec_dir, docs_root=docs_root)
    cli_status = str(payload.get("status", "invalid")).lower()
    status = (
        "passed"
        if returncode == 0 and build_status == "passed" and cli_status == "passed"
        else "invalid"
    )
    notes = ostler_qa.notes_for(
        payload,
        stderr,
        "QA OKF context is valid." if status == "passed" else "QA OKF context is invalid.",
    )
    logger.info("qa context-validate for %s returned status=%s", spec_dir, status)
    return OkfContextResult(status=status, notes=notes, ostler=payload)


__all__ = ["build_okf_context", "validate_okf_context"]
