"""Build the diff-to-OKF obligation packet, and check that it holds."""
from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Literal

from git.exc import GitError
from ostler import Ostler
from ostler.qa.source_context import SourceRepository, SourceScope
from workhorse_workflows.kit import find_docs_root, open_repo
from workhorse_workflows.coder.shared.blueprint import blueprint
from workhorse_workflows.coder.shared.qa_support import notes_for, parse_source_roots
from workhorse_workflows.coder.shared.schemas.okf import OkfContextResult
from workhorse_workflows.coder.shared.schemas.dev import StorySource
from workhorse_workflows.coder.shared.worktree import digest, untouched_since

PACKET_FILES = (
    "qa-okf-context.json",
    "qa-okf-context.md",
    "qa-okf-verification-index.json",
)

STAMP_FILE = "qa-okf-context.stamp.json"


def worktree_signature(
    root: Path, base: str, head: str, ignore: tuple[str, ...] = ()
) -> str | None:
    """A digest of everything about *root* the obligation packet is a function of."""
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
    """The memo key: the worktree signature plus every argument that shapes the packet."""
    if signature is None:
        return None
    payload = json.dumps({"signature": signature, **arguments}, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def recall(spec_path: Path, key: str | None) -> OkfContextResult | None:
    """The recorded result when the packet on disk was built from exactly these inputs."""
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
    recorded = stamp.get("ostler")
    return OkfContextResult(
        status="passed" if stamp.get("status") == "passed" else "invalid",
        notes=str(stamp.get("notes", "")),
        ostler=recorded if isinstance(recorded, dict) else {},
    )


def remember(spec_path: Path, key: str | None, result: OkfContextResult) -> None:
    """Record what the packet just written was built from, so the next visit can skip it."""
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


def _source_repositories(sources: tuple[StorySource, ...]) -> tuple[SourceRepository, ...]:
    grouped: dict[str, tuple[str, str, str, list[SourceScope]]] = {}
    for source in sources:
        existing = grouped.get(source.repo)
        scope = SourceScope(surface=source.surface, root=source.root)
        if existing is None:
            grouped[source.repo] = (
                source.checkout,
                source.base,
                source.head,
                [scope],
            )
            continue
        checkout, base, head, scopes = existing
        if (source.checkout, source.base, source.head) != (checkout, base, head):
            raise ValueError(f"source repository {source.repo!r} has conflicting provenance")
        if scope not in scopes:
            scopes.append(scope)
    return tuple(
        SourceRepository(
            id=repo,
            checkout=checkout,
            base=base,
            head=head,
            scopes=tuple(scopes),
        )
        for repo, (checkout, base, head, scopes) in grouped.items()
    )


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
    story_sources: tuple[StorySource, ...] = (),
) -> OkfContextResult:
    """Map a diff onto the OKF graph and write the obligation packet into the spec dir."""
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
    repositories = _source_repositories(story_sources)
    source_signatures = {
        source.repo: worktree_signature(
            Path(source.checkout), source.base, source.head
        )
        for source in story_sources
    }
    docs_signature = worktree_signature(root, base, head, outputs)
    signature = (
        hashlib.sha256(
            json.dumps(
                {"docs": docs_signature, "sources": source_signatures}, sort_keys=True
            ).encode()
        ).hexdigest()
        if story_sources and docs_signature is not None and all(source_signatures.values())
        else docs_signature
    )
    arguments: dict[str, object] = {
        "spec": str(spec_path),
        "story_file": story_file,
        "features_root": features_root,
        "source_roots": sorted(source_roots),
        "base": base,
        "head": head,
        "exclude_paths": inherited,
    }
    if story_sources:
        arguments["story_sources"] = [
            source.model_dump(mode="json") for source in story_sources
        ]
    key = fingerprint(
        signature,
        arguments,
    )
    memo = recall(spec_path, key)
    if memo is not None:
        logger.info(
            "qa context build for spec_dir=%s: reusing the packet on disk — "
            "nothing it is a function of has moved since it was written",
            spec_dir,
        )
        return memo
    if repositories:
        outcome = Ostler(docs_root).qa_context(
            base=base,
            head=head,
            spec=spec_dir,
            features_root=features_root,
            story_file=story_file or None,
            exclude_paths=inherited,
            repositories=repositories,
        )
    else:
        outcome = Ostler(docs_root).qa_context(
            base=base,
            head=head,
            spec=spec_dir,
            source_roots=parse_source_roots(list(source_roots)),
            features_root=features_root,
            story_file=story_file or None,
            exclude_paths=inherited,
        )
    status: Literal["passed", "invalid"] = "passed" if outcome.ok else "invalid"
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
    """Re-check the packet the builder wrote, and carry the builder's verdict forward."""
    docs_root = find_docs_root(docs_path, repo_dir)
    outcome = Ostler(docs_root).qa_context_validate(spec=spec_dir)
    status: Literal["passed", "invalid"] = (
        "passed" if outcome.ok and build_status == "passed" else "invalid"
    )
    notes = notes_for(
        outcome,
        "QA OKF context is valid." if status == "passed" else "QA OKF context is invalid.",
    )
    logger.info("qa context-validate for %s returned status=%s", spec_dir, status)
    return OkfContextResult(status=status, notes=notes, ostler=outcome.data)


__all__ = ["build_okf_context", "validate_okf_context"]
