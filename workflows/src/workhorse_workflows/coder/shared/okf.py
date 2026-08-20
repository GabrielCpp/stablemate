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

import hashlib
import json
import logging
from pathlib import Path

from git.exc import GitError
from ostler import Ostler
from workhorse_workflows.kit import find_docs_root, open_repo
from workhorse_workflows.coder.shared.blueprint import blueprint
from workhorse_workflows.coder.shared.qa_support import notes_for, parse_source_roots
from workhorse_workflows.coder.shared.schemas.okf import OkfContextResult
from workhorse_workflows.coder.shared.worktree import digest, untouched_since

#: What `ostler qa context` writes. All three have to be on disk for a memo hit to mean
#: anything — the packet is what the next gate and the planning agent actually read, so a
#: memo that skips the build while one of them is missing is worse than no memo at all.
PACKET_FILES = (
    "qa-okf-context.json",
    "qa-okf-context.md",
    "qa-okf-verification-index.json",
)

#: Where the memo records what the packet beside it was built from. On disk rather than in
#: memory because the visits that repeat are *separate node calls* — a story's QA lane
#: builds this packet on the way in, again after every repair, and again for the docs
#: gate, and nothing about the process survives between them.
STAMP_FILE = "qa-okf-context.stamp.json"


def worktree_signature(
    root: Path, base: str, head: str, ignore: tuple[str, ...] = ()
) -> str | None:
    """A digest of everything about *root* the obligation packet is a function of.

    `HEAD` plus the tracked diff plus every untracked file's bytes — the same three things
    the packet's own inputs are, so a book edit, a commit, a code change and a brand-new
    file each move it. `None` when git cannot answer, and a `None` never matches a
    recorded signature: the memo can only ever fail towards rebuilding.

    *ignore* holds repo-relative paths the signature must not see: the packet this build is
    about to write, and the memo beside it. They land inside the docs repo and are normally
    untracked, so a signature that counted them would be moved by the very build it is
    supposed to describe — every visit a miss, and the memo dead on arrival.
    """
    excluded = set(ignore)
    try:
        repo = open_repo(root)
        parts = [repo.git.rev_parse(base), repo.git.rev_parse("HEAD")]
        if head == "WORKTREE":
            pathspec = ["--", ".", *(f":(exclude){rel}" for rel in sorted(excluded))]
            parts.append(repo.git.diff(base, *pathspec))
            parts.extend(
                f"{rel}\0{digest(root, rel)}"
                for rel in sorted(set(repo.untracked_files) - excluded)
            )
        else:
            parts.append(repo.git.rev_parse(head))
    except (GitError, ValueError):
        return None
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


def fingerprint(signature: str | None, arguments: dict[str, object]) -> str | None:
    """The memo key: the worktree signature plus every argument that shapes the packet.

    Arguments as well as repo state, because two nodes build this packet for the same repo
    at the same commit with different spec dirs and different excludes, and their packets
    are not interchangeable.
    """
    if signature is None:
        return None
    payload = json.dumps({"signature": signature, **arguments}, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def recall(spec_path: Path, key: str | None) -> OkfContextResult | None:
    """The recorded result when the packet on disk was built from exactly these inputs.

    Anything unreadable, mismatched or half-written answers `None` — the caller then does
    what it would have done anyway. This function is not allowed a failure mode that
    returns the *wrong* packet, only one that returns no packet.
    """
    if key is None:
        return None
    if not all((spec_path / name).is_file() for name in PACKET_FILES):
        return None
    try:
        stamp = json.loads((spec_path / STAMP_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(stamp, dict) or stamp.get("fingerprint") != key:
        return None
    return OkfContextResult(
        status=str(stamp.get("status", "invalid")),
        notes=str(stamp.get("notes", "")),
        ostler=stamp.get("ostler") if isinstance(stamp.get("ostler"), dict) else {},
    )


def remember(spec_path: Path, key: str | None, result: OkfContextResult) -> None:
    """Record what the packet just written was built from, so the next visit can skip it.

    Only a passing build is recorded. A failed one is what the repair lap exists to fix,
    and the repair edits the book — which moves the signature anyway, so memoizing the
    failure would buy nothing and would put a stale `invalid` where a reader might trust it.
    """
    if key is None or result.status != "passed":
        return
    try:
        (spec_path / STAMP_FILE).write_text(
            json.dumps(
                {
                    "fingerprint": key,
                    "status": result.status,
                    "notes": result.notes,
                    "ostler": result.ostler,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    except OSError:
        return


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

    The build is memoized against the packet already on disk. A story's lane visits this
    node many times over — on the way in, after every repair lap, and again for the docs
    gate — and each visit paid a full `Ostler(docs_root)` construction to re-derive a
    packet that is a pure function of the book, the diff and these arguments. When none of
    those have moved, the packet beside the memo *is* the answer, so it is returned rather
    than rebuilt.
    """
    docs_root = find_docs_root(docs_path, repo_dir)
    inherited = sorted(untouched_since(Path(docs_root).resolve(), tuple(preexisting)))
    if inherited:
        logger.info(
            "excluding %d path(s) that were already dirty when the story started: %s",
            len(inherited),
            ", ".join(inherited),
        )
    root = Path(docs_root).resolve()
    spec = Path(spec_dir)
    spec_path = spec if spec.is_absolute() else root / spec
    outputs = tuple(
        (spec_path / name).relative_to(root).as_posix()
        for name in (*PACKET_FILES, STAMP_FILE)
        if spec_path.is_relative_to(root)
    )
    key = fingerprint(
        worktree_signature(root, base, head, outputs),
        {
            "spec": str(spec_path),
            "story_file": story_file,
            "features_root": features_root,
            "source_roots": sorted(source_roots),
            "base": base,
            "head": head,
            "exclude_paths": inherited,
        },
    )
    memo = recall(spec_path, key)
    if memo is not None:
        logger.info(
            "qa context build for spec_dir=%s: reusing the packet on disk — "
            "nothing it is a function of has moved since it was written",
            spec_dir,
        )
        return memo
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
    result = OkfContextResult(status=status, notes=notes, ostler=outcome.data)
    remember(spec_path, key, result)
    return result


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
