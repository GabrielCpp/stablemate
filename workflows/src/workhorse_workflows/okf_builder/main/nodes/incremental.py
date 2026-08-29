"""Deterministic convergence check for story-aware incremental builds."""
from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

from ostler import Ostler
from ostler.provenance import source_freshness
from ostler.qa.source_context import SourceRepository, SourceScope

from workhorse_workflows.okf_builder.shared import paths
from workhorse_workflows.okf_builder.shared.blueprint import blueprint
from workhorse_workflows.okf_builder.shared.schemas import (
    IncrementalCheck,
    Prepared,
    SourceRequest,
)
from workhorse_workflows.okf_builder.shared.worklist import load_worklist
from workhorse_workflows.kit.git import diff_text
from workhorse_workflows.kit.workspace import resolve_workspace


def _unit_refs(unit: dict[str, Any]) -> list[str]:
    unit_id = str(unit.get("id") or unit.get("path") or "")
    symbols = sorted(
        {
            str(symbol)
            for field in ("baseSymbols", "headSymbols")
            for symbol in unit.get(field, [])
            if symbol
        }
    )
    return [f"{unit_id}::{symbol}" for symbol in symbols] or [unit_id]


def _change_items(
    packet: dict[str, Any],
    *,
    story_id: str,
    story_path: str,
    acceptance_criteria: list[dict[str, str]],
    health_only: bool = False,
) -> list[dict[str, Any]]:
    """Turn changed units into bounded, directly-owned documentation work."""
    health = [
        finding
        for finding in packet.get("healthFindings", [])
        if finding.get("severity") == "error"
        and finding.get("kind") in {"unmapped-change", "dangling-grounding"}
    ]
    direct = packet.get("directNodes", [])
    items: list[dict[str, Any]] = []
    for unit in packet.get("changedUnits", []):
        refs = _unit_refs(unit)
        owners = [
            row["node"]
            for row in direct
            if any(reason.get("ref") in refs for reason in row.get("reasons", []))
        ]
        relevant_health = [
            finding
            for finding in health
            if finding.get("path") in refs
            or finding.get("path") == unit.get("id")
            or finding.get("ref") in refs
        ]
        if health_only and not relevant_health:
            continue
        context = {
            "status": unit.get("status", ""),
            "baseSymbols": unit.get("baseSymbols", []),
            "headSymbols": unit.get("headSymbols", []),
            "repository": unit.get("repository", ""),
            "refs": refs,
            "directNodes": owners,
            "story": {
                "id": story_id,
                "path": story_path,
                "acceptanceCriteria": acceptance_criteria,
            },
            "deleted": unit.get("status") == "deleted",
            "healthFindings": relevant_health,
        }
        items.append(
            {
                "kind": "change",
                "target": refs[0] if len(refs) == 1 else ", ".join(refs),
                "context": json.dumps(context, sort_keys=True),
                "requeue": True,
            }
        )
    if health_only:
        covered = {
            finding.get("message")
            for item in items
            for finding in json.loads(item["context"])["healthFindings"]
        }
        for finding in health:
            if finding.get("message") in covered:
                continue
            target = str(
                finding.get("ref")
                or finding.get("path")
                or finding.get("node")
                or finding["kind"]
            )
            items.append(
                {
                    "kind": "change",
                    "target": target,
                    "context": json.dumps(
                        {
                            "status": "health",
                            "baseSymbols": [],
                            "headSymbols": [],
                            "repository": "",
                            "refs": [target],
                            "directNodes": [finding.get("node")]
                            if finding.get("node")
                            else [],
                            "story": {
                                "id": story_id,
                                "path": story_path,
                                "acceptanceCriteria": acceptance_criteria,
                            },
                            "deleted": False,
                            "healthFindings": [finding],
                        },
                        sort_keys=True,
                    ),
                    "requeue": True,
                }
            )
    return items


def _scope_id(
    story_id: str,
    story_content: str,
    packet: dict[str, Any],
    source_fingerprints: dict[str, str],
) -> str:
    payload = {
        "story": story_id,
        "content": story_content,
        "repositories": packet.get("repositories", []),
        "changedUnits": packet.get("changedUnits", []),
        "sourceFingerprints": source_fingerprints,
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()[:16]


def _doctor_errors(report: dict[str, Any]) -> tuple[str, ...]:
    return tuple(
        json.dumps(finding, sort_keys=True, separators=(",", ":"))
        for finding in report.get("findings", [])
        if finding.get("severity") == "error"
    )


def _stored_packet(spec_path: Path) -> dict[str, Any] | None:
    try:
        packet = json.loads((spec_path / "qa-okf-context.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return packet if isinstance(packet, dict) else None


def _freshness_items(
    okf: Ostler, spec_path: str | Path, checkouts: dict[str, str]
) -> list[dict[str, Any]]:
    path = Path(spec_path)
    packet = _stored_packet(path if path.is_absolute() else okf.root / path)
    if packet is None:
        return []
    freshness = source_freshness(
        okf.graph, packet, {repo: Path(path) for repo, path in checkouts.items()}
    )
    return [
        {
            "kind": "refresh:source",
            "target": str(row["repository"]),
            "context": json.dumps(row, sort_keys=True),
            "requeue": True,
        }
        for row in freshness
        if row["status"] != "fresh"
    ]


def _source_repositories(
    sources: tuple[SourceRequest, ...], checkouts: dict[str, str]
) -> tuple[SourceRepository, ...]:
    grouped: dict[str, tuple[str, str, list[SourceScope]]] = {}
    for request in sources:
        existing = grouped.get(request.repo)
        if existing is None:
            grouped[request.repo] = (
                request.base,
                request.head,
                [SourceScope(surface=request.surface, root=request.root)],
            )
            continue
        base, head, scopes = existing
        if (request.base, request.head) != (base, head):
            raise ValueError(
                f"source repository {request.repo!r} has conflicting base/head revisions"
            )
        scope = SourceScope(surface=request.surface, root=request.root)
        if scope not in scopes:
            scopes.append(scope)
    return tuple(
        SourceRepository(
            id=repo,
            checkout=checkouts[repo],
            base=base,
            head=head,
            scopes=tuple(scopes),
        )
        for repo, (base, head, scopes) in grouped.items()
    )


def prepare_incremental(
    logger: logging.Logger,
    root: Path,
    service: str,
    story_ref: str,
    workspace_file: str,
    repo_dir: str,
    sources: tuple[SourceRequest, ...],
) -> Prepared:
    """Resolve one story and build its initial multi-repository change packet."""
    try:
        okf = Ostler(root)
        found = okf.graph.find_story(story_ref)
    except (OSError, ValueError, RuntimeError) as exc:
        return Prepared(repo_root=str(root), mode="incremental", prepare_error=str(exc))
    if found is None:
        return Prepared(
            repo_root=str(root),
            mode="incremental",
            prepare_error=f"story {story_ref!r} was not found in the docs graph",
        )
    _epic, resolved_story = found
    if resolved_story.story_md is None:
        return Prepared(
            repo_root=str(root),
            mode="incremental",
            prepare_error=f"story {story_ref!r} has no story.md",
        )
    try:
        story_content = resolved_story.story_md.read_text(encoding="utf-8")
    except OSError as exc:
        return Prepared(repo_root=str(root), mode="incremental", prepare_error=str(exc))

    workspace = resolve_workspace(workspace_file, repo_dir or root)
    checkouts: dict[str, str] = {}
    for request in sources:
        row = workspace.get(request.repo)
        if row is None or not row.get("path"):
            return Prepared(
                repo_root=str(root),
                mode="incremental",
                prepare_error=f"source repository {request.repo!r} is not in the workspace",
            )
        checkout = str(Path(row["path"]).resolve())
        checkouts[request.repo] = checkout
    try:
        repositories = _source_repositories(sources, checkouts)
    except ValueError as exc:
        return Prepared(repo_root=str(root), mode="incremental", prepare_error=str(exc))
    canonical_story = resolved_story.eid or resolved_story.slug
    spec = okf.spec_path(canonical_story)
    freshness_items = _freshness_items(okf, spec, checkouts)
    outcome = okf.qa_context(
        base="HEAD",
        head="WORKTREE",
        spec=spec,
        story_file=resolved_story.story_md,
        repositories=repositories,
    )
    packet = outcome.data
    if outcome.status == "invalid" or not isinstance(packet, dict) or "changedUnits" not in packet:
        return Prepared(
            repo_root=str(root),
            mode="incremental",
            prepare_error=outcome.message or "ostler returned no incremental QA packet",
        )
    doctor = okf.doctor()
    if doctor.status == "invalid":
        return Prepared(
            repo_root=str(root),
            mode="incremental",
            prepare_error=doctor.message or "ostler could not validate the feature book",
        )
    acceptance = [dict(item) for item in packet.get("acceptanceCriteria", [])]
    story_path = str(resolved_story.story_md.resolve())
    items = _change_items(
        packet,
        story_id=canonical_story,
        story_path=story_path,
        acceptance_criteria=acceptance,
    )
    items.extend(freshness_items)
    source_fingerprints = {}
    for request in sources:
        diff_args = (
            (request.base, "--", request.root)
            if request.head == "WORKTREE"
            else (request.base, request.head, "--", request.root)
        )
        key = f"{request.repo}:{request.surface}:{request.root}"
        source_fingerprints[key] = hashlib.sha256(
            diff_text(checkouts[request.repo], *diff_args).encode()
        ).hexdigest()
    scope_id = _scope_id(
        canonical_story,
        story_content,
        packet,
        source_fingerprints,
    )
    features = paths.features_root(root, service)
    paths.ensure_build_dir(root)
    worklist = paths.worklist_path(root, service, scope_id)
    data, reset = load_worklist(
        worklist,
        service,
        features,
        scope_id=scope_id,
        mode="incremental",
    )
    worklist.write_text(json.dumps(data, indent=2), encoding="utf-8")
    baseline = sum(1 for item in data["items"] if item.get("status") == "done")
    logger.info(
        "prepared incremental story %s from %d repository source(s): %d changed unit(s)",
        canonical_story,
        len(repositories),
        len(packet.get("changedUnits", [])),
    )
    return Prepared(
        worklist_path=str(worklist),
        features_root=str(features),
        repo_root=str(root),
        source_root=next(iter(checkouts.values()), str(root)),
        service=service,
        ostler_ok=True,
        done_baseline=baseline,
        worklist_reset=reset,
        mode="incremental",
        scope_id=scope_id,
        story_id=canonical_story,
        story_path=story_path,
        story_content=story_content,
        acceptance_criteria=tuple(acceptance),
        spec_path=str(spec),
        packet=packet,
        source_requests=sources,
        source_checkouts=checkouts,
        source_roots=tuple(dict.fromkeys(checkouts.values())),
        baseline_doctor_errors=_doctor_errors(doctor.data),
        initial_items=tuple(items),
    )


@blueprint.node
def check_incremental_context(
    logger: logging.Logger,
    repo_root: str,
    spec_path: str,
    story_id: str,
    story_path: str,
    source_requests: tuple[SourceRequest, ...],
    source_checkouts: dict[str, str],
    baseline_doctor_errors: tuple[str, ...],
) -> IncrementalCheck:
    """Rebuild the packet and return only actionable incremental health failures."""
    try:
        repositories = _source_repositories(source_requests, source_checkouts)
    except ValueError as exc:
        return IncrementalCheck(error=str(exc))
    okf = Ostler(repo_root)
    freshness_items = _freshness_items(okf, Path(spec_path), source_checkouts)
    outcome = okf.qa_context(
        base="HEAD",
        head="WORKTREE",
        spec=spec_path,
        story_file=Path(story_path),
        repositories=repositories,
    )
    packet = outcome.data
    if outcome.status == "invalid" or not isinstance(packet, dict) or "changedUnits" not in packet:
        return IncrementalCheck(error=outcome.message or "ostler returned no incremental QA packet")
    acceptance = [dict(item) for item in packet.get("acceptanceCriteria", [])]
    items = _change_items(
        packet,
        story_id=story_id,
        story_path=story_path,
        acceptance_criteria=acceptance,
        health_only=True,
    )
    items.extend(freshness_items)
    affected_paths = {
        str(row.get("node", "")).partition("#")[0]
        for row in packet.get("directNodes", [])
        if row.get("node")
    }
    doctor = okf.doctor()
    if doctor.status == "invalid":
        return IncrementalCheck(error=doctor.message, packet=packet)
    baseline = set(baseline_doctor_errors)
    for finding in doctor.data.get("findings", []):
        encoded = json.dumps(finding, sort_keys=True, separators=(",", ":"))
        if finding.get("severity") != "error" or (
            finding.get("path") not in affected_paths and encoded in baseline
        ):
            continue
        items.append(
            {
                "kind": f"fix:{finding['code']}",
                "target": str(
                    finding.get("ref") or finding.get("path") or finding["code"]
                ),
                "context": json.dumps(finding, sort_keys=True),
                "requeue": True,
            }
        )
    unique = {
        (str(item.get("kind")), str(item.get("target"))): item for item in items
    }
    items = list(unique.values())
    signature = hashlib.sha256(
        json.dumps(items, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    logger.info("incremental context has %d actionable item(s)", len(items))
    return IncrementalCheck(
        clean=not items,
        packet=packet,
        items=items,
        signature=signature,
    )


__all__ = ["check_incremental_context", "prepare_incremental"]
