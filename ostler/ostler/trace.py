"""`ostler trace` — walk the organization graph from any node (seed id, story slug, gap id,
surface or doc path) and print the chain of references and their statuses."""

from __future__ import annotations

from .model import Graph


def run(graph: Graph, token: str) -> tuple[list[str], bool]:
    """Return (lines, found)."""
    out: list[str] = []

    # 1) story slug
    hit = graph.find_story(token)
    if hit:
        epic, story = hit
        out.append(f"story  {story.slug}   (epic: {epic.name})")
        out.append(f"  title:  {story.title}")
        out.append(f"  status: {story.status or '—'}")
        out.append(f"  file:   {story.story_md if story.story_md else '(missing)'}")
        if story.dependencies:
            out.append(f"  depends on: {', '.join(story.dependencies)}")
        for sid in story.seed_items:
            seed = next((s for s in epic.seeds if s.id == sid), None)
            label = seed.summary if seed else "(unknown seed)"
            out.append(f"  seed  {sid}: {label}")
        owners = [(r.surface, g.id) for r in graph.knowledge for g in r.gaps if g.owner == token]
        for surface, gid in owners:
            out.append(f"  owns gap  {gid}  (in {surface})")
        return out, True

    # 2) seed id
    epic = graph.epic_of_seed(token)
    if epic:
        seed = next(s for s in epic.seeds if s.id == token)
        out.append(f"seed   {seed.id}   (epic: {epic.name}, status: {seed.status or '—'})")
        out.append(f"  {seed.summary}")
        covering = [s for s in epic.stories if token in s.seed_items]
        if covering:
            for s in covering:
                out.append(f"  covered by story  {s.slug}  ({s.status or '—'})")
        else:
            out.append("  covered by: NOTHING (orphan)" if seed.active else "  covered by: — (inactive)")
        return out, True

    # 3) gap id
    g_hit = graph.find_gap(token)
    if g_hit:
        record, gap = g_hit
        out.append(f"gap    {gap.id}   (surface: {record.surface})")
        out.append(f"  disposition: {gap.disposition or '—'}")
        if gap.owner:
            owner = graph.find_story(gap.owner)
            where = f" (epic: {owner[0].name})" if owner else " (UNKNOWN story)"
            out.append(f"  owner: {gap.owner}{where}")
        else:
            out.append("  owner: (none)")
        taggers = [s.slug for e in graph.epics for s in e.stories if token in s.gap_tags]
        for slug in taggers:
            out.append(f"  tagged by story  {slug}")
        return out, True

    # 4) surface
    rec = next((r for r in graph.knowledge if r.surface == token), None)
    if rec:
        out.append(f"surface {rec.surface}   ({rec.fmt}: {rec.path})")
        for gap in rec.gaps:
            out.append(f"  gap  {gap.id}  owner={gap.owner or '—'}  disposition={gap.disposition or '—'}")
        return out, True

    # 5) path
    referrers = [s.slug for e in graph.epics for s in e.stories if token in s.knowledge_refs]
    if referrers:
        out.append(f"path   {token}")
        for slug in referrers:
            out.append(f"  referenced by story  {slug}")
        return out, True

    return [f"no node found for '{token}'"], False
