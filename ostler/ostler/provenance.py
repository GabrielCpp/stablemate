"""Derived joins between Git story trailers and story-scoped OKF context packets."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from ostler import path as path_mod, refs
from ostler.model import Graph, Story, UINode
from ostler.qa.source_context import SourceRepository, SourceScope
from ostler.source_snapshots import load_catalog, resolved_sha, source_fingerprint

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


def source_freshness(
    graph: Graph, packet: dict[str, Any], checkouts: dict[str, Path]
) -> list[dict[str, Any]]:
    """Compare stored packet/catalog fingerprints with explicitly supplied checkouts."""
    catalog = load_catalog(graph.root)
    rows: list[dict[str, Any]] = []
    for stored in packet.get("repositories", []):
        identifier = str(stored.get("id", ""))
        reasons: list[str] = []
        checkout = checkouts.get(identifier)
        snapshot = catalog.repository(identifier) if catalog else None
        packet_fingerprint = str(stored.get("sourceFingerprint", ""))
        if checkout is None:
            rows.append(
                {
                    "repository": identifier,
                    "status": "unknown",
                    "reasons": [f"no checkout supplied for repository {identifier!r}"],
                }
            )
            continue
        if not packet_fingerprint:
            reasons.append("context packet predates source fingerprints")
        if snapshot is None or not snapshot.source_fingerprint:
            reasons.append("source catalog predates source fingerprints")
        elif packet_fingerprint and snapshot.source_fingerprint != packet_fingerprint:
            reasons.append("source catalog and context packet fingerprints disagree")
        try:
            repository = SourceRepository(
                id=identifier,
                checkout=str(checkout),
                base=str(stored.get("base") or stored.get("baseSha") or ""),
                head=str(stored.get("head") or "WORKTREE"),
                scopes=tuple(
                    SourceScope.model_validate(scope) for scope in stored.get("scopes", [])
                ),
            )
        except ValueError as exc:
            rows.append(
                {
                    "repository": identifier,
                    "status": "unknown",
                    "reasons": [f"stored source provenance is invalid: {exc}"],
                }
            )
            continue
        base_sha = resolved_sha(repository, repository.base)
        if stored.get("baseSha") and base_sha != stored.get("baseSha"):
            reasons.append("base revision no longer resolves to the recorded commit")
        if repository.head != "WORKTREE":
            head_sha = resolved_sha(repository, repository.head)
            if stored.get("headSha") and head_sha != stored.get("headSha"):
                reasons.append("head revision no longer resolves to the recorded commit")
        current_fingerprint = source_fingerprint(repository)
        if packet_fingerprint and current_fingerprint != packet_fingerprint:
            reasons.append("scoped source content differs from the recorded fingerprint")
        unknown = any("predates source fingerprints" in reason for reason in reasons)
        rows.append(
            {
                "repository": identifier,
                "status": "unknown" if unknown else "stale" if reasons else "fresh",
                "sourceFingerprint": current_fingerprint,
                "reasons": reasons,
            }
        )
    return rows


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
            "freshness": source_freshness(graph, packet or {}, checkouts),
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


def _checkout_for(repository: str, checkouts: dict[str, Path]) -> Path | None:
    """The checkout a ``code:`` target lives in.

    A qualified ref (``repo://api-service/...``) names its repository. A bare one predates
    qualification and can only mean "the" checkout — honoured when exactly one was supplied,
    because guessing among several would join a node to another repository's history.
    """
    if repository:
        return checkouts.get(repository)
    if len(checkouts) == 1:
        return next(iter(checkouts.values()))
    return None


def story_for_node(
    graph: Graph, node_ref: str, checkouts: dict[str, Path]
) -> list[dict[str, Any]]:
    """The story whose intent the code under a node answers to: the ``Story:`` trailer on
    the most recent commit touching any of the node's ``code:`` targets.

    The link between code and story is the trailer and nothing else — not a packet, not a
    citation in the story's prose. Several stories over one symbol: the latest commit wins,
    because it is the intent the code was last written to. ``story`` is ``None`` when no
    reachable commit over those files carries a trailer, which a caller reads as "the code
    is the intent" — there is no story to judge it against. A trailer no story in the book
    resolves is reported as such (``resolved: false``) rather than dropped, so a stale
    footer stays visible instead of reading as "no story".
    """
    node = graph.find_ui_node(node_ref)
    if node is None:
        return []
    row = _node_row(graph, node)
    warnings: list[str] = []
    by_checkout: dict[Path, dict[str, list[str]]] = {}
    for ref in row["codeRefs"]:
        try:
            parsed = refs.parse_code_ref(ref)
        except ValueError:
            warnings.append(f"malformed code ref {ref!r}")
            continue
        checkout = _checkout_for(parsed.repository, checkouts)
        if checkout is None:
            warnings.append(
                f"no checkout supplied for repository {parsed.repository or '(unqualified)'!r}"
            )
            continue
        slot = by_checkout.setdefault(checkout, {"repository": [parsed.repository], "paths": []})
        if parsed.path not in slot["paths"]:
            slot["paths"].append(parsed.path)

    latest: tuple[int, str, str, str] | None = None  # (time, repository, sha, trailer)
    for checkout, slot in by_checkout.items():
        listing = _git(checkout, "log", "--format=%H %ct", "--", *slot["paths"])
        if listing is None:
            warnings.append(f"git log failed in {checkout}")
            continue
        for line in listing.splitlines():
            sha, _, stamp = line.partition(" ")
            if not sha:
                continue
            message = _git(checkout, "show", "-s", "--format=%B", sha)
            trailers = _trailers(message or "")
            if not trailers:
                continue
            when = int(stamp) if stamp.isdigit() else 0
            repository = slot["repository"][0] or next(
                (name for name, path in checkouts.items() if path == checkout), "")
            # The last trailer on a commit is the one an amend appended; one commit
            # answering two stories is the operator's ambiguity to keep, so report the last.
            candidate = (when, repository, sha, trailers[-1])
            if latest is None or candidate[0] > latest[0]:
                latest = candidate
            break  # newest-first: the first commit with a trailer is this checkout's answer

    if latest is None:
        return [{"node": row, "commit": None, "story": None, "resolved": False,
                 "warnings": warnings}]
    _when, repository, sha, trailer = latest
    found = graph.find_story(trailer)
    return [{
        "node": row,
        "commit": {"repository": repository, "sha": sha, "trailer": trailer},
        "story": _story_row(found[0].name, found[1]) if found else None,
        "resolved": bool(found),
        "warnings": warnings,
    }]


PROVENANCE_QUERIES = ("story-provenance", "commit-story", "node-provenance", "story-for-node")
