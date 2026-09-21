"""Conventional Commit subjects for everything the coder workflow writes to git."""
from __future__ import annotations

import re
from pathlib import Path

SUBJECT_LIMIT = 72

_SCOPE_STRIP = re.compile(r"[^a-z0-9._-]+")

_HEADING_LABEL = re.compile(r"^(story|epic)\s*[:–—-]\s*", re.IGNORECASE)


def scope(name: str) -> str:
    """The Conventional Commit scope for a repo/package name (`""` when nothing survives)."""
    cleaned = _SCOPE_STRIP.sub("-", name.strip().lower()).strip("-.")
    return cleaned


def describe(text: str) -> str:
    """Normalize a story heading into a Conventional Commit description."""
    stripped = " ".join(text.split()).rstrip(".")
    if not stripped:
        return ""
    head, _, tail = stripped.partition(" ")
    if head[1:].islower() or not head[1:]:
        head = head[0].lower() + head[1:]
    return f"{head} {tail}".strip()


def subject(
    kind: str,
    package: str,
    description: str,
    marker: str = "",
) -> str:
    """Build a Conventional Commit subject with a protected status suffix."""
    head = f"{kind}({package})" if package else kind
    body = describe(description) or "no description"
    suffixes = [marker] if marker else []
    tail = f" {' '.join(suffixes)}" if suffixes else ""
    budget = SUBJECT_LIMIT - len(f"{head}: {tail}")
    if len(body) > budget:
        body = body[: max(budget, 0)].rstrip(" -–—:,") or body.split(" ")[0]
    return f"{head}: {body}{tail}"


def message(
    kind: str,
    package: str,
    description: str,
    marker: str = "",
    epic: str = "",
    story: str = "",
) -> str:
    """A Conventional Commit subject plus the exact provenance trailers."""
    lines = [subject(kind, package, description, marker)]
    trailers = [f"{label}: {value}" for label, value in (("Epic", epic), ("Story", story)) if value]
    if trailers:
        lines.extend(["", *trailers])
    return "\n".join(lines)


def story_description(root: Path, story_path: str, fallback: str = "") -> str:
    """The story's `# ` heading, normalized — what its commit and its PR title both say."""
    full = root / story_path if story_path else None
    if full is not None and full.is_file():
        try:
            for line in full.read_text(encoding="utf-8").splitlines():
                stripped = line.strip()
                if stripped.startswith("# "):
                    described = describe(_HEADING_LABEL.sub("", stripped[2:].strip()))
                    if described:
                        return described
                    break
        except OSError:
            pass
    return describe(fallback)


__all__ = ["SUBJECT_LIMIT", "describe", "message", "scope", "story_description", "subject"]
