"""`ostler doctor` — deterministic referential-integrity checks over the organization graph.

Computes (never asserts) per-epic seed/story counts and flags cross-epic references, orphan seeds,
missing story files, dangling dependencies / gap-tags / knowledge paths, and stale gap owners.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from . import freeze, markdown, registry, schemas
from .model import Graph, Epic


@dataclass
class Finding:
    severity: str   # "error" | "warn"
    code: str
    message: str
    epic: str = ""
    ref: str = ""


@dataclass
class Report:
    org: str
    profile: str
    epics: list[dict] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)

    @property
    def errors(self) -> int:
        return sum(1 for f in self.findings if f.severity == "error")

    @property
    def warnings(self) -> int:
        return sum(1 for f in self.findings if f.severity == "warn")

    def as_dict(self) -> dict:
        return {
            "org": self.org,
            "profile": self.profile,
            "epics": self.epics,
            "errors": self.errors,
            "warnings": self.warnings,
            "findings": [vars(f) for f in self.findings],
        }


def run(graph: Graph, epic_filter: str | None = None, check_schema: bool = True) -> Report:
    report = Report(org=graph.org_name, profile=graph.profile)
    f = report.findings

    _check_knowledge(graph, f)
    _check_surfaces(graph, f)
    if check_schema:
        _check_conformance(graph, f)

    if graph.profile != "full":
        _check_frozen(graph, report.findings)
        return report

    all_story_slugs = graph.all_story_slugs()
    all_gap_ids = graph.all_gap_ids()

    for epic in graph.epics:
        if epic_filter and epic.name != epic_filter and epic.directory.name != epic_filter:
            continue
        report.epics.append(_epic_facts(epic))
        _check_epic(graph, epic, all_story_slugs, all_gap_ids, f)

    if epic_filter:
        keep = {e.name for e in graph.epics
                if epic_filter in (e.name, e.directory.name)} or {epic_filter}
        report.findings = [fd for fd in report.findings if fd.epic in keep]

    # Frozen-entity checks are graph-global (an approved entity is pinned regardless of which
    # epic is being filtered), so run them after any epic trim, appending to the live list.
    _check_frozen(graph, report.findings)

    return report


def _check_frozen(graph: Graph, f: list[Finding]) -> None:
    """Flag approved (frozen) entities that were removed or whose content changed since approval.
    The fingerprint + provenance live in ``.agents/ids.json`` under ``frozen`` (see freeze.py)."""
    frozen = (graph.ids or {}).get("frozen") or {}
    for ident, meta in frozen.items():
        if not isinstance(meta, dict) or "hash" not in meta:
            continue
        by = f" by {meta['approvedBy']}" if meta.get("approvedBy") else ""
        resolved = freeze.resolve_content(graph, ident)
        if resolved is None:
            f.append(Finding("error", "frozen-removed",
                             f"frozen {meta.get('kind', 'entity')} '{ident}' (approved{by}) no "
                             f"longer exists — restore it, or `ostler unfreeze {ident}` if the "
                             f"removal is intended", ref=ident))
            continue
        kind, content = resolved
        if freeze.fingerprint(content) != meta["hash"]:
            found = graph.find_story(ident)
            epic_name = found[0].name if found else ""
            f.append(Finding("error", "frozen-mutated",
                             f"frozen {kind} '{ident}' (approved{by}) changed since approval — "
                             f"revert it, or `ostler unfreeze {ident}` to intentionally let it "
                             f"evolve", epic=epic_name, ref=ident))


def _epic_facts(epic: Epic) -> dict:
    active = [s for s in epic.seeds if s.active]
    covered = {sid for st in epic.stories for sid in st.seed_items}
    return {
        "epic": epic.name,
        "dir": epic.directory.name,
        "seedCount": len(epic.seeds),
        "activeSeedCount": len(active),
        "storyCount": len(epic.stories),
        "coveredActiveSeeds": len([s for s in active if s.id in covered]),
        "orphanActiveSeeds": [s.id for s in active if s.id not in covered],
    }


def _check_epic(graph: Graph, epic: Epic, all_slugs: set[str], all_gaps: set[str],
                f: list[Finding]) -> None:
    seed_ids = epic.seed_ids
    covered: set[str] = set()

    for story in epic.stories:
        covered.update(story.seed_items)

        # seed references resolve within this epic
        for sid in story.seed_items:
            if sid in seed_ids:
                continue
            other = graph.epic_of_seed(sid)
            if other is not None:
                f.append(Finding("error", "cross-epic-seed",
                                  f"story '{story.slug}' references seed '{sid}' that belongs to "
                                  f"epic '{other.name}', not '{epic.name}'", epic.name, sid))
            else:
                f.append(Finding("error", "dangling-seed",
                                  f"story '{story.slug}' references unknown seed '{sid}'",
                                  epic.name, sid))

        # dependencies resolve to sibling stories
        for dep in story.dependencies:
            if dep in {s.slug for s in epic.stories}:
                continue
            other = graph.epic_of_story(dep)
            if other is not None:
                f.append(Finding("error", "cross-epic-dependency",
                                  f"story '{story.slug}' depends on '{dep}' from epic "
                                  f"'{other.name}', not '{epic.name}'", epic.name, dep))
            else:
                f.append(Finding("error", "dangling-dependency",
                                  f"story '{story.slug}' depends on unknown story '{dep}'",
                                  epic.name, dep))

        # story.md file present
        if story.story_md is None:
            f.append(Finding("error", "missing-story-file",
                             f"story '{story.slug}' has no story.md (path: {story.path or '?'})",
                             epic.name, story.slug))
        else:
            # gap tags referenced in prose resolve to a real gap
            for tag in story.gap_tags:
                if all_gaps and tag not in all_gaps:
                    f.append(Finding("warn", "dangling-gap-tag",
                                     f"story '{story.slug}' tags [gap:{tag}] but no knowledge "
                                     f"record defines it", epic.name, tag))
            # knowledge paths referenced in prose exist on disk
            for ref in story.knowledge_refs:
                if not (graph.root / ref).exists():
                    f.append(Finding("error", "dangling-knowledge-path",
                                     f"story '{story.slug}' links '{ref}' which does not exist",
                                     epic.name, ref))

        # only meaningful when the epic uses seeds at all (a wholly-seedless epic is a valid mode)
        if not story.seed_items and epic.seeds:
            f.append(Finding("warn", "story-covers-no-seed",
                             f"story '{story.slug}' lists no seedItems", epic.name, story.slug))

    # orphan active seeds — no story covers them
    for s in epic.seeds:
        if s.active and s.id not in covered:
            f.append(Finding("error", "orphan-seed",
                             f"active seed '{s.id}' ({s.status or 'no-status'}) is covered by no "
                             f"story", epic.name, s.id))


def _check_conformance(graph: Graph, f: list[Finding]) -> None:
    """OKF conformance + per-type frontmatter schema, walking every Concept on disk.

    Conformance is the one hard OKF rule: a non-reserved ``.md`` must carry a non-empty ``type``
    (``okf-missing-type`` otherwise). On top of that, ostler validates each Concept's frontmatter
    against its registered per-type schema (warn-level), which OKF permits for known types.
    """
    for etype in registry.REGISTRY:
        base = graph.doc_roots.get(etype.doc_root)
        if base is None or not base.is_dir():
            continue
        for path in sorted(base.glob(etype.location)):
            if not path.is_file() or path.name in registry.RESERVED_FILES:
                continue
            rel = path.relative_to(graph.root).as_posix()
            try:
                fm = (markdown.split(path.read_text(encoding="utf-8")).frontmatter) or {}
            except OSError as exc:
                f.append(Finding("error", "unreadable", f"{rel}: {exc}"))
                continue
            if not registry.type_of(fm):
                f.append(Finding("error", "okf-missing-type",
                                 f"{rel}: Concept has no non-empty `type` in frontmatter"))
                continue
            if etype.schema:
                for msg in schemas.validate(fm, etype.schema):
                    f.append(Finding("warn", "schema", f"{rel}: {msg}"))
    if graph.ids is not None:
        for msg in schemas.validate(graph.ids, "ids.schema.json"):
            f.append(Finding("warn", "schema", f"ids.json: {msg}"))


def _check_knowledge(graph: Graph, f: list[Finding]) -> None:
    all_slugs = graph.all_story_slugs()
    for record in graph.knowledge:
        for gap in record.gaps:
            if not gap.owner:
                if gap.disposition and gap.disposition not in ("dropped", "deferred"):
                    f.append(Finding("warn", "stale-owner",
                                     f"gap '{gap.id}' in {record.surface} is "
                                     f"'{gap.disposition}' but has no owner", ref=gap.id))
                continue
            if graph.profile == "full" and gap.owner not in all_slugs:
                f.append(Finding("error", "dangling-owner",
                                 f"gap '{gap.id}' in {record.surface} is owned by unknown story "
                                 f"'{gap.owner}'", ref=gap.id))


def _norm(s: object) -> str:
    """Lowercase, route-/path-insensitive token for generous surface matching."""
    return re.sub(r"[^a-z0-9]+", "-", str(s or "").strip().lower().strip("/")).strip("-")


def _inventory_keys(graph: Graph) -> set[str] | None:
    """Surface identifiers derived from the feature Concepts (``docs/features/**/*.md``), or None
    if there are no features yet (a greenfield repo before its surface registry exists → skip)."""
    if not graph.features:
        return None
    keys: set[str] = set()
    for feat in graph.features:
        for v in (feat.slug, feat.key, feat.data.get("route")):
            if v:
                keys.add(_norm(v))
    return keys


def _check_surfaces(graph: Graph, f: list[Finding]) -> None:
    """Spec ↔ surface-registry edge: every knowledge record describes a screen, so its surface
    must exist in the feature inventory that the coder builds against. A surface absent from the
    inventory means the spec graph and the implementation registry have drifted apart. (The
    registry ↔ running-code edge — does the route actually render — is framework-specific and
    lives in the coder's QA health gate, not here.) Generous substring match, warn-level."""
    keys = _inventory_keys(graph)
    if not keys:
        return  # no inventory registry → nothing to ground against
    for record in graph.knowledge:
        needles = [_norm(record.surface), _norm(record.data.get("route") or "")]
        needles = [n for n in needles if len(n) >= 3]
        if needles and not any(n in k or k in n for n in needles for k in keys):
            f.append(Finding("warn", "ungrounded-surface",
                             f"knowledge surface '{record.surface}' is not in the feature "
                             f"inventory (inventory.json) — add its feature doc or fix the "
                             f"surface so spec and implementation registry stay in sync",
                             ref=record.surface))
