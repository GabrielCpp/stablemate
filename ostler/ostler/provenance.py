"""Derived joins between Git story trailers and story-scoped OKF context packets."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from ostler import path as path_mod, refs
from ostler.model import Graph, Story, UINode

CONTEXT_FILE = "qa-okf-context.json"


def _git(checkout: Path, *args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=checkout,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout if result.returncode == 0 else None


def _trailers(message: str) -> list[str]:
    return [
        line.removeprefix("Story:").strip()
        for line in message.splitlines()
        if line.startswith("Story:") and line.removeprefix("Story:").strip()
    ]


def story_commits(checkout: Path, aliases: tuple[str, ...]) -> list[dict[str, Any]]:
    """Reachable commits carrying an exact ``Story:`` trailer, oldest first."""
    shas = _git(checkout, "log", "--reverse", "--format=%H", "HEAD")
    if shas is None:
        return []
    wanted = set(aliases)
    rows: list[dict[str, Any]] = []
    for sha in shas.splitlines():
        message = _git(checkout, "show", "-s", "--format=%B", sha)
        if message is None:
            continue
        matched = [value for value in _trailers(message) if value in wanted]
        if not matched:
            continue
        paths = _git(checkout, "show", "--format=", "--name-only", sha)
        parent = _git(checkout, "rev-parse", "--verify", f"{sha}^1")
        rows.append(
            {
                "sha": sha,
                "parent": parent.strip() if parent else None,
                "storyTrailers": matched,
                "paths": sorted({line for line in (paths or "").splitlines() if line}),
            }
        )
    return rows


def _story_row(epic_name: str, story: Story) -> dict[str, Any]:
    return {
        "id": story.eid,
        "externalKey": story.external_key,
        "slug": story.slug,
        "aliases": list(story.aliases),
        "epic": epic_name,
        "path": story.path,
    }


def _context(graph: Graph, story_ref: str) -> tuple[dict[str, Any] | None, str]:
    relative = Path(path_mod.resolve_spec(graph, story_ref)) / CONTEXT_FILE
    context_path = graph.root / relative
    try:
        payload = json.loads(context_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, relative.as_posix()
    except (OSError, ValueError):
        return {}, relative.as_posix()
    return (payload if isinstance(payload, dict) else {}), relative.as_posix()


def story_provenance(
    graph: Graph, story_ref: str, checkouts: dict[str, Path]
) -> list[dict[str, Any]]:
    found = graph.find_story(story_ref)
    if found is None:
        return []
    epic, story = found
    packet, packet_path = _context(graph, story.eid or story.slug)
    repository_ids = [
        str(repository.get("id", ""))
        for repository in (packet or {}).get("repositories", [])
        if repository.get("id")
    ]
    commits: list[dict[str, Any]] = []
    warnings: list[str] = []
    for repository in repository_ids or sorted(checkouts):
        checkout = checkouts.get(repository)
        if checkout is None:
            warnings.append(f"no checkout supplied for repository {repository!r}")
            continue
        rows = story_commits(checkout, story.aliases)
        commits.extend({"repository": repository, **row} for row in rows)
    if packet is None:
        warnings.append(f"story has no generated context packet at {packet_path}")
    elif not packet:
        warnings.append(f"story context packet at {packet_path} is unreadable")
    return [
        {
            "story": _story_row(epic.name, story),
            "contextPath": packet_path,
            "repositories": (packet or {}).get("repositories", []),
            "commits": commits,
            "changedUnits": (packet or {}).get(
                "changedUnits", (packet or {}).get("changedCode", [])
            ),
            "directNodes": (packet or {}).get("directNodes", []),
            "contracts": (packet or {}).get("contracts", []),
            "journeys": (packet or {}).get("journeys", []),
            "warnings": warnings,
        }
    ]


def commit_story(
    graph: Graph, token: str, checkouts: dict[str, Path]
) -> list[dict[str, Any]]:
    repository, separator, revision = token.partition("@")
    if not separator or not repository or not revision:
        return []
    checkout = checkouts.get(repository)
    if checkout is None:
        return [{"repository": repository, "revision": revision, "warnings": [
            f"no checkout supplied for repository {repository!r}"
        ]}]
    sha = _git(checkout, "rev-parse", "--verify", f"{revision}^{{commit}}")
    if sha is None:
        return []
    resolved_sha = sha.strip()
    message = _git(checkout, "show", "-s", "--format=%B", resolved_sha) or ""
    stories: list[dict[str, Any]] = []
    for trailer in _trailers(message):
        found = graph.find_story(trailer)
        stories.append(
            {
                "trailer": trailer,
                "resolved": bool(found),
                **(_story_row(found[0].name, found[1]) if found else {}),
            }
        )
    return [{"repository": repository, "sha": resolved_sha, "stories": stories}]


def _node_row(graph: Graph, node: UINode) -> dict[str, Any]:
    return {
        "id": node.id,
        "type": node.type,
        "title": node.title,
        "path": node.path.relative_to(graph.root).as_posix(),
        "codeRefs": refs.code_refs(node.meta.get("code")),
    }


def node_provenance(
    graph: Graph, node_ref: str, checkouts: dict[str, Path]
) -> list[dict[str, Any]]:
    node = graph.find_ui_node(node_ref)
    node_id = node.id if node is not None else node_ref
    stories: list[dict[str, Any]] = []
    specs_root = graph.doc_roots["specs"]
    for context_path in sorted(specs_root.glob(f"*/{CONTEXT_FILE}")):
        try:
            packet = json.loads(context_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(packet, dict):
            continue
        direct = [
            item for item in packet.get("directNodes", []) if item.get("node") == node_id
        ]
        roles = [
            role
            for role, values in (
                ("direct", direct),
                ("contract", packet.get("contracts", [])),
                ("journey", packet.get("journeys", [])),
            )
            if (bool(values) if role == "direct" else node_id in values)
        ]
        if not roles:
            continue
        raw_identity = packet.get("story")
        identity: dict[str, Any] = raw_identity if isinstance(raw_identity, dict) else {}
        story_ref = str(identity.get("id") or identity.get("slug") or context_path.parent.name)
        provenance = story_provenance(graph, story_ref, checkouts)
        stories.append(
            {
                "story": provenance[0]["story"] if provenance else identity,
                "roles": roles,
                "reasons": direct[0].get("reasons", []) if direct else [],
                "commits": provenance[0]["commits"] if provenance else [],
                "contextPath": context_path.relative_to(graph.root).as_posix(),
            }
        )
    return [{"node": _node_row(graph, node) if node else {"id": node_id}, "stories": stories}]


PROVENANCE_QUERIES = ("story-provenance", "commit-story", "node-provenance")
