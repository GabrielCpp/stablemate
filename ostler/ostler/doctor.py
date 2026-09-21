"""`ostler doctor` — deterministic referential-integrity checks over the organization graph."""

from __future__ import annotations

import difflib
import json
import os
import re
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from ostler import (acts, checks, dynamic_registry, freeze, inventory, links as links_mod, markdown,
                    model, registry, schemas, select)
from ostler import drivers, graph as graph_mod, locators as loc_mod, reach, routes as routes_mod
from ostler.vet import placement as placement_mod
from ostler import refs as refs_mod
from ostler.model import Graph, Epic, Story, UINode, read_doc, required_section_problems
from ostler.path import features_root as features_root_of, specs_root_in
from ostler.provenance import checkout_for
from ostler.qa import (captures as captures_mod, fixtures as fixtures_mod, references,
                       runbook as runbook_mod, sensitivity)
from ostler.qa.compile import Gap
from ostler.qa.context import RELATION_KEYS, relation_subject
from ostler.qa.outcome import QaOutcome
from ostler import stamp as stamp_mod
from ostler import values as values_mod
from ostler.source_snapshots import book_repository


@dataclass
class Finding:
    severity: str
    code: str
    message: str
    epic: str = ""
    ref: str = ""
    path: str = ""
    line: int = 0
    suggestion: str = ""
    fixable: bool = False
    node: str = ""
    related: list[str] = field(default_factory=list)


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


def scope_to_paths(report: Report, paths: list[str]) -> Report:
    """*report* keeping only the findings about *paths* (repo-relative files or folders)."""
    wanted = [p.strip("/") for p in paths]

    def inside(path: str) -> bool:
        return any(path == p or path.startswith(p + "/") for p in wanted)

    return Report(
        org=report.org,
        profile=report.profile,
        epics=report.epics,
        findings=[
            f for f in report.findings
            if inside(f.path) or any(inside(r.split("#", 1)[0]) for r in f.related)
        ],
    )


def diff_reports(indexed: Report, uncached: Report, *, context: int = 2) -> list[str]:
    """The unified diff between two runs' reports, empty when they agree."""
    left = json.dumps(indexed.as_dict(), indent=2, sort_keys=True, default=str)
    right = json.dumps(uncached.as_dict(), indent=2, sort_keys=True, default=str)
    if left == right:
        return []
    return list(
        difflib.unified_diff(
            left.splitlines(),
            right.splitlines(),
            fromfile="doctor (index)",
            tofile="doctor (--no-index)",
            lineterm="",
            n=context,
        )
    )


def _epic_matches(epic: Epic, epic_filter: str) -> bool:
    """Whether ``--epic <filter>`` names this epic — by directory or by bare slug."""
    return (epic_filter in (epic.name, epic.directory.name)
            or registry.epic_slug(epic.name) == registry.epic_slug(epic_filter))


def run(graph: Graph, epic_filter: str | None = None, check_schema: bool = True,
        checkouts: dict[str, Path] | None = None) -> Report:
    report = Report(org=graph.org_name, profile=graph.profile)
    f = report.findings

    resolver = links_mod.LinkResolver(graph)

    _check_ui(graph, f, resolver, checkouts)
    _check_book_captures(graph, f)
    _check_self_relation(graph, f, resolver)
    _check_judgment(graph, f, resolver)
    _check_same_as_symmetry(graph, f, resolver)
    _check_same_as_disagreement(graph, f, resolver)
    _check_unspecified(graph, f, resolver)
    _check_sensitivity(graph, f)
    _check_runbook(graph, f)
    ui_data = _ui_graph(graph, resolver)
    if ui_data is not None:
        _check_reachability(ui_data, f)
        _check_locators(ui_data, f)
        _check_unknown_driver(ui_data, f)
        _check_runbook_driver_surface(ui_data, f)
    if check_schema:
        _check_conformance(graph, f)
        _check_misplaced_book_pages(graph, f)
        _check_misrooted_book_pages(graph, f)
    _apply_known_defects(graph, f)
    _apply_surface_declarations(graph, f)

    _check_fixture_grammar(graph, f)
    _check_entry_properties(graph, f)
    _check_record_properties(graph, f)
    _check_undeclared_container_properties(graph, f)
    _check_prose_buried_bullets(graph, f)
    _check_bullet_value_kinds(graph, ui_data, f)

    if graph.profile != "full":
        _check_frozen(graph, report.findings)
        return report

    all_story_slugs = graph.all_story_slugs()

    _check_milestones(graph, f)
    _check_fixtures(graph, f)
    _check_story_identity(graph, f)

    for epic in graph.epics:
        if epic_filter and not _epic_matches(epic, epic_filter):
            continue
        report.epics.append(_epic_facts(epic))
        _check_epic(graph, epic, all_story_slugs, f)

    if epic_filter:
        keep = {e.name for e in graph.epics if _epic_matches(e, epic_filter)} or {epic_filter}
        report.findings = [fd for fd in report.findings if fd.epic in keep]

    _check_frozen(graph, report.findings)
    return report


def _check_story_identity(graph: Graph, findings: list[Finding]) -> None:
    """Every accepted story spelling identifies one story, and its two id copies agree."""
    owners: dict[str, list[tuple[Epic, Story]]] = {}
    for epic in graph.epics:
        for story in epic.stories:
            for alias in story.aliases:
                owners.setdefault(alias, []).append((epic, story))
            if story.eid and story.file_eid and story.eid != story.file_eid:
                path = (story.story_md.relative_to(graph.root).as_posix()
                        if story.story_md else "")
                findings.append(Finding(
                    "error", "story-id-mismatch",
                    f"story '{story.slug}' has id '{story.eid}' in epic.md but "
                    f"'{story.file_eid}' in story.md",
                    epic.name, story.slug, path=path, line=1))
    for alias, matches in owners.items():
        unique = {(epic.name, story.path) for epic, story in matches}
        if len(unique) < 2:
            continue
        paths = ", ".join(path for _, path in sorted(unique))
        findings.append(Finding(
            "error", "story-key-collision",
            f"story key '{alias}' identifies multiple stories: {paths}", ref=alias))


_KNOWN_DEFECT = re.compile(r"^`?(?P<seed>[A-Za-z0-9][\w.-]*)`?\s+`?(?P<code>[a-z][a-z0-9-]*)`?(?:\s|$)")


def parse_known_defect(value: str) -> tuple[str, str] | None:
    """``(seed_id, finding_code)`` from a ``known-defect:`` value, or None when it states neither."""
    m = _KNOWN_DEFECT.match(value.strip())
    return (m.group("seed"), m.group("code")) if m else None


OBLIGATION_CODES = frozenset({
    "undeclared-obligation", "unminted-claim", "compound-normative-bullet", "weak-check",
    "insensitive-check", "unstated-precondition", "relation-without-subject",
})


def _apply_surface_declarations(graph: Graph, findings: list[Finding]) -> None:
    """Apply ``exercised: false`` from each surface's ``index.md`` frontmatter."""
    froot = graph.doc_roots["features"]
    try:
        features_rel = froot.relative_to(graph.root).as_posix()
    except ValueError:
        return
    dropped: list[str] = []
    for surface, meta in sorted(graph.surfaces.items()):
        if "exercised" not in meta:
            continue
        rel = f"{features_rel}/{surface}/index.md"
        value = meta["exercised"]
        if not isinstance(value, bool):
            findings.append(Finding(
                "error", "malformed-declaration",
                f"{rel}: `exercised:` is `{value!r}`, not a boolean — the declaration is either "
                f"made or absent",
                ref=f"{surface}#exercised", path=rel, line=1,
                suggestion="exercised: false"))
            continue
        if value:
            continue
        prefix = f"{features_rel}/{surface}/"
        if not any(_rel_path(graph, n).startswith(prefix) for n in graph.ui_nodes):
            findings.append(Finding(
                "error", "stale-declaration",
                f"{rel}: `exercised: false` on a surface with no node — nothing is left to "
                f"declare out of scope, and the next book written here would inherit it",
                ref=f"{surface}#exercised", path=rel, line=1,
                suggestion="delete the `exercised:` key, or the index with it"))
            continue
        dropped.append(prefix)
    if dropped:
        findings[:] = [fd for fd in findings
                       if fd.code not in OBLIGATION_CODES
                       or not fd.path.startswith(tuple(dropped))]


def _apply_known_defects(graph: Graph, findings: list[Finding]) -> None:
    """Apply every ``known-defect:`` bullet, and report the ones that have gone stale."""
    seeds: dict[str, str] | None = None
    if graph.profile == "full":
        seeds = {seed.id: seed.status for epic in graph.epics for seed in epic.seeds}

    suppressed: set[int] = set()
    stale: list[Finding] = []
    for node in graph.ui_nodes:
        rel = node.path.relative_to(graph.root).as_posix()
        for index, value in enumerate(_bullet_values(node.meta.get("known-defect", "")), 1):
            parsed = parse_known_defect(value)
            if parsed is None:
                stale.append(Finding(
                    "error", "malformed-defect",
                    f"{node.id}: `known-defect: {value}` names no seed and finding code — "
                    f"the form is `<seed-id> <finding-code>`, and a bullet with neither "
                    f"excuses nothing",
                    path=rel, line=node.line, ref=refs_mod.bullet_ref(node.id, "known-defect", index),
                    suggestion="- known-defect: <seed-id> <finding-code>"))
                continue
            seed_id, code = parsed
            matched = [
                i for i, fd in enumerate(findings)
                if fd.code == code and (fd.ref == node.id or fd.ref.startswith(node.id + "#"))
            ]
            status = None if seeds is None else seeds.get(seed_id)
            if seeds is not None and (status is None or status in registry.INACTIVE_SEED_STATUS):
                why = (f"seed {seed_id} is {status}" if status
                       else f"no epic carries a seed {seed_id}")
                stale.append(Finding(
                    "error", "stale-defect",
                    f"{node.id}: `known-defect: {seed_id} {code}` points at work that is not "
                    f"open — {why}; the finding it excused is back in this report. Fix the "
                    f"code under an active seed, or drop the bullet",
                    path=rel, line=node.line, ref=refs_mod.bullet_ref(node.id, "known-defect", index),
                    suggestion="- known-defect: <an active seed-id> " + code))
                continue
            if not matched:
                stale.append(Finding(
                    "error", "stale-defect",
                    f"{node.id}: `known-defect: {seed_id} {code}` excuses a finding that no "
                    f"longer fires — the code was fixed, or the record was wrong; left in "
                    f"place it pre-excuses the next `{code}` on this node. Drop the bullet",
                    path=rel, line=node.line, ref=refs_mod.bullet_ref(node.id, "known-defect", index),
                    suggestion="delete the `known-defect:` bullet"))
                continue
            suppressed.update(matched)
    if suppressed:
        findings[:] = [fd for i, fd in enumerate(findings) if i not in suppressed]
    findings.extend(stale)


def _check_frozen(graph: Graph, f: list[Finding]) -> None:
    """Flag approved (frozen) entities that were removed or whose content changed since approval."""
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


def _check_epic(graph: Graph, epic: Epic, all_slugs: set[str], f: list[Finding]) -> None:
    seed_ids = epic.seed_ids
    covered: set[str] = set()

    for story in epic.stories:
        covered.update(story.seed_items)

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

        deps_ref = f"its `## {registry.STORY_DEPS_HEADING}` section"
        for dep in story.dependencies:
            if dep in {s.slug for s in epic.stories}:
                continue
            other = graph.epic_of_story(dep)
            if other is not None:
                f.append(Finding("error", "cross-epic-dependency",
                                  f"story '{story.slug}' is blocked by '{dep}' from epic "
                                  f"'{other.name}', not '{epic.name}' — {deps_ref}",
                                  epic.name, dep))
            else:
                f.append(Finding("error", "dangling-dependency",
                                  f"story '{story.slug}' is blocked by unknown story '{dep}' "
                                  f"in {deps_ref}", epic.name, dep))

        for stray in story.dependency_strays:
            f.append(Finding("error", "malformed-dependency-bullet",
                             f"story '{story.slug}' has a bullet under "
                             f"`## {registry.STORY_DEPS_HEADING}` that states no blocker: "
                             f"{stray!r}", epic.name, story.slug,
                             suggestion=f"write it as `- {registry.STORY_DEPS_LABEL}: <slug>`, "
                                        f"or `{registry.STORY_DEPS_NONE}` with no bullet at all"))

        if story.story_md is None:
            f.append(Finding("error", "missing-story-file",
                             f"story '{story.slug}' has no story.md (path: {story.path or '?'})",
                             epic.name, story.slug))
        else:
            if story.body_status and story.status.strip() != story.body_status.strip():
                rel = story.story_md.relative_to(graph.root).as_posix()
                f.append(Finding(
                    "error", "story-status-mismatch",
                    f"story '{story.slug}' frontmatter status '{story.status}' differs from "
                    f"its `## Implementation Status` value '{story.body_status}'",
                    epic.name, story.slug, path=rel, line=1))
            if story.conflict:
                rel = story.story_md.relative_to(graph.root).as_posix()
                f.append(Finding(
                    "error", "story-conflict",
                    f"story '{story.slug}' has acceptance criteria in conflict — "
                    f"{story.conflict}",
                    epic.name, story.slug, path=rel, line=1,
                    suggestion="rewrite the criteria so one intent holds, then "
                               f"`ostler conflict {story.slug} --clear`"))
            if story.unwritten_sections:
                rel = story.story_md.relative_to(graph.root).as_posix()
                f.append(Finding("error", "unwritten-story",
                                 f"story '{story.slug}' is still a bare scaffold — "
                                 f"{', '.join(story.unwritten_detail)}",
                                 epic.name, story.slug, path=rel, line=1))
            if story.misordered_sections:
                rel = story.story_md.relative_to(graph.root).as_posix()
                f.append(Finding("error", "story-section-order",
                                 f"story '{story.slug}' orders its required sections against "
                                 f"the contract — {'; '.join(story.misordered_sections)}",
                                 epic.name, story.slug, path=rel, line=1))
        if not story.seed_items and epic.seeds:
            f.append(Finding("warn", "story-covers-no-seed",
                             f"story '{story.slug}' lists no seedItems", epic.name, story.slug))

    for s in epic.seeds:
        if s.active and s.id not in covered:
            f.append(Finding("error", "orphan-seed",
                             f"active seed '{s.id}' ({s.status or 'no-status'}) is covered by no "
                             f"story", epic.name, s.id))
        if s.active and not s.layers:
            f.append(Finding("warn", "unclassified-seed",
                             f"seed '{s.id}' has no `layers:` — every story covering it keeps "
                             f"the mockup turn by default", epic.name, s.id,
                             suggestion=f"ostler seed add {epic.name} {s.id} --layer "
                                        f"<{'|'.join(registry.SEED_LAYERS)}>"))


def _check_fixtures(graph: Graph, f: list[Finding]) -> None:
    """Hold every story's ``## Fixtures`` to the repo's declarations and to its own plan."""
    spec_root = specs_root_in(graph.root)
    for message in fixtures_mod.preflight_errors(graph.root):
        f.append(Finding("error", "qa-fixture-declaration", message))

    specs, _errors = fixtures_mod.declared(graph.root)
    book_fixtures = {Path(n.id).stem for n in graph.ui_nodes_of_type("fixture")}
    known = set(specs) | book_fixtures

    _check_book_fixtures(graph, known, f)

    for name in sorted(set(specs) - book_fixtures):
        f.append(Finding(
            "warn", "unmigrated-fixture-declaration",
            f"qa fixture '{name}' is still a hand-written `qa: {{fixtures:}}` entry in "
            f"agents.yml with no book fixture node behind it — migrate it with "
            f"`ostler qa fixtures migrate`",
            ref=name))

    for epic in graph.epics:
        for story in epic.stories:
            if story.story_md is None:
                continue
            rel = story.story_md.relative_to(graph.root).as_posix()
            for stray in story.fixture_strays:
                f.append(Finding(
                    "error", "story-fixture-stray",
                    f"story '{story.slug}' has a `## {registry.STORY_FIXTURES_HEADING}` bullet "
                    f"that names no fixture: {stray!r} — write "
                    f"`- {registry.STORY_FIXTURES_LABEL}: <name>`, or "
                    f"`{registry.STORY_FIXTURES_NONE}` when the story arranges nothing",
                    epic.name, story.slug, path=rel, line=1))
            plan = spec_root / story.slug / "qa_plan.py"
            plan_rel = plan.relative_to(graph.root).as_posix()
            names = fixtures_mod.referenced(plan) if plan.is_file() else None
            stated = set(story.fixtures)

            for name in story.fixtures:
                if name not in known:
                    f.append(Finding(
                        "error", "unknown-story-fixture",
                        f"story '{story.slug}' names fixture '{name}', which this repo does not "
                        f"declare. Declared here: "
                        f"{', '.join(sorted(known)) or '(none)'}",
                        epic.name, name, path=rel, line=1,
                        suggestion=_undeclared_fixture_repair(name, names, plan_rel)))

            if names is None:
                continue
            for name in sorted(names - stated):
                f.append(Finding(
                    "error", "undeclared-story-fixture",
                    f"story '{story.slug}' arranges state with fixture '{name}' in its "
                    f"qa_plan.py but does not say so — add "
                    f"`- {registry.STORY_FIXTURES_LABEL}: {name}` under "
                    f"`## {registry.STORY_FIXTURES_HEADING}`",
                    epic.name, name, path=rel, line=1))
            for name in sorted((stated & known) - names):
                f.append(Finding(
                    "warn", "unused-story-fixture",
                    f"story '{story.slug}' names fixture '{name}' but its qa_plan.py never asks "
                    f"for it ({plan_rel})",
                    epic.name, name, path=rel, line=1))


def _undeclared_fixture_repair(name: str, referenced: set[str] | None, plan_rel: str) -> str:
    """Say what to do about a `## Fixtures` name the repo does not declare."""
    if referenced is None:
        return (f"no `{plan_rel}` yet, so nothing yet says whether '{name}' is an arrangement "
                f"nobody declared or a word that was never an arrangement. The plan decides; "
                f"write it first.")
    if name in referenced:
        return (f"`{plan_rel}` asks for '{name}', so it is an arrangement nobody declared — add "
                f"a fixture node under `docs/features/<surface>/fixtures/{name}.md`, or a "
                f"hand-written `qa: {{fixtures:}}` entry in agents.yml")
    return (f"`{plan_rel}` never asks for '{name}', so nothing arranges it and nothing wants it "
            f"— delete the bullet, or write `{registry.STORY_FIXTURES_NONE}` if the story "
            f"arranges nothing")


def _check_book_captures(graph: Graph, f: list[Finding]) -> None:
    """A `capture:` bullet is a name and a source, in the grammar a `$name` reference can spell."""
    for node in graph.ui_nodes:
        keys = registry.capture_keys(node.type)
        if not keys:
            continue
        rel = _rel_path(graph, node)
        for key, value, _bullet in node.bullet_order:
            if key not in keys:
                continue
            parsed = captures_mod.parse_bullet(value)
            if not isinstance(parsed, str):
                continue
            f.append(Finding(
                "error", "unparsed-capture",
                f"{node.id}: `{key}: {value}` is not a capture declaration — {parsed}",
                path=rel, line=node.line, ref=value,
                suggestion=f"- {key}: <name> from <json path | UI locator>"))


def _check_book_fixtures(graph: Graph, known: set[str], f: list[Finding]) -> None:
    """A `fixture:` bullet in the book names an arrangement this repo actually declares."""
    by_name = {Path(n.id).stem: n for n in graph.ui_nodes_of_type("fixture")}
    for node in graph.ui_nodes:
        arrange = registry.fixture_keys(node.type)
        if not arrange:
            continue
        rel = node.path.relative_to(graph.root).as_posix()
        for key, value, _bullet in node.bullet_order:
            if key not in arrange:
                continue
            parsed = fixtures_mod.parse_bullet(value)
            if isinstance(parsed, fixtures_mod.NoArrangement):
                continue
            if isinstance(parsed, str):
                f.append(Finding(
                    "error", "qa-fixture-bullet",
                    f"{node.id}: `{key}: {value}` is not a fixture reference — {parsed}",
                    path=rel, line=node.line, ref=value))
                continue
            if parsed.name not in known:
                f.append(Finding(
                    "error", "unknown-book-fixture",
                    f"{node.id}: `{key}:` names fixture '{parsed.name}', which this repo does "
                    f"not declare — add a fixture node under `docs/features/<surface>/fixtures/"
                    f"{parsed.name}.md`, or a hand-written `qa: {{fixtures:}}` entry in "
                    f"agents.yml. Declared here: {', '.join(sorted(known)) or '(none)'}",
                    path=rel, line=node.line, ref=parsed.name))
                continue
            _check_unbacked_precondition(node, rel, key, value, parsed,
                                         by_name.get(parsed.name), f)


def _check_unbacked_precondition(node: UINode, rel: str, key: str, value: str,
                                 parsed: fixtures_mod.FixtureRef, target: UINode | None,
                                 f: list[Finding]) -> None:
    """The state a `fixture:` bullet says it is arranged in, against what the fixture declares."""
    if not parsed.provides or target is None:
        return
    if _fixture_declared_provides(target):
        return
    f.append(Finding(
        "warn", "unbacked-precondition",
        f"{node.id}: `{key}: {value}` says fixture '{parsed.name}' leaves this state behind, "
        f"and '{target.id}' declares no `provides:` at all — the precondition is written by "
        f"the node that uses the arrangement about work the node that performs it never "
        f"claimed, and a compiled plan copies it into `preconditions=[...]` where nothing "
        f"can hold the fixture to it",
        path=rel, line=node.line, ref=parsed.name,
        suggestion=f"declare it on {target.id}: `- provides:` with a child per fact, "
                   f"`<key> — <what it means>`"))


_FIXTURE_STEP_KINDS: frozenset[str] = frozenset({"seed", "run", "verify"})


def _check_entry_properties(graph: Graph, f: list[Finding]) -> None:
    """An entry of an ``entries=True`` key may only carry the properties its key declares."""
    for node in graph.ui_nodes:
        if not node.entries:
            continue
        uitype = registry.UI_TYPES_BY_NAME.get(node.type)
        if uitype is None:
            continue
        rel = _rel_path(graph, node)
        by_key = uitype.bullet_by_key
        for key, entries in node.entries.items():
            spec = by_key.get(key)
            if spec is None or not spec.properties:
                continue
            allowed = set(spec.properties)
            for entry in entries:
                for prop in entry.properties:
                    if prop in allowed:
                        continue
                    f.append(Finding(
                        "error", "unknown-entry-property",
                        f"{node.id}: `{key}:` entry {entry.headline!r} carries `{prop}:`, which "
                        f"`{key}:` does not admit",
                        path=rel, line=node.line, ref=f"{key}:{prop}",
                        suggestion="one of: " + ", ".join(f"{name}:" for name in spec.properties)))


_BULLET_KEY_SPELLING = re.compile(r"^[a-z][a-z0-9-]{0,24}$")


def _check_undeclared_container_properties(graph: Graph, f: list[Finding]) -> None:
    """A bullet key the node type does not declare can still bury a bullet key it does — and replace it, not merely restate it, when the node states no top-level claim of its own."""
    for node in graph.ui_nodes:
        declared = registry.declared_keys(node.type)
        rel = _rel_path(graph, node)
        for key, value in node.meta.items():
            if key in declared or not _BULLET_KEY_SPELLING.match(key) or not isinstance(value, list):
                continue
            hits = []
            for item in value:
                raw = item.split(":", 1)[0].strip()
                bare = raw.strip("`")
                if bare in declared and bare not in node.meta:
                    hits.append((raw, bare))
            if not hits:
                continue
            for raw, bare in hits:
                quoted = raw if raw.startswith("`") and raw.endswith("`") else f"`{raw}`"
                f.append(Finding(
                    "error", "misnested-bullet",
                    f"{node.id}: {quoted}: nested under `{key}:` is a property spelling of "
                    f"{node.type}'s own `{bare}:` bullet, but `{key}:` is not a key {node.type} "
                    f"declares, so it is invisible rather than merely misplaced",
                    path=rel, line=node.line, ref=f"{key}:{bare}", fixable=True,
                    suggestion=f"promote `- {bare}:` to a top-level bullet of the node"))


def _prose_burial_keys() -> frozenset[str]:
    """Every key that makes a node's meta subtree normative or observational wherever it surfaces."""
    return frozenset(registry.SHARED_NORMATIVE_KEYS) | _OBSERVATION_KEYS


def _check_prose_buried_bullets(graph: Graph, f: list[Finding]) -> None:
    """A numbered list item is prose, and a bullet filed beneath one is invisible to the node."""
    burial_keys = _prose_burial_keys()
    for node in graph.ui_nodes:
        declared = registry.declared_keys(node.type)
        rel = _rel_path(graph, node)
        for key, value in node.meta.items():
            if key in declared or _BULLET_KEY_SPELLING.match(key) or not isinstance(value, list):
                continue
            children = [item.split(":", 1)[0].strip() for item in value]
            hits = sorted({child for child in children if child in burial_keys})
            if not hits:
                continue
            named = ", ".join(f"`{child}:`" for child in hits)
            verb = "is" if len(hits) == 1 else "are"
            f.append(Finding(
                "error", "prose-buried-bullet",
                f"{node.id}: the numbered list item beginning {_prose(key)[:60]!r} is prose, "
                f"not a key {node.type} declares — {named} filed beneath it {verb} invisible to "
                f"{node.type}, not merely misplaced",
                path=rel, line=node.line, ref=",".join(hits),
                suggestion=f"move {named} out of the numbered list, to a top-level bullet of "
                           f"the node"))


def _check_record_properties(graph: Graph, f: list[Finding]) -> None:
    """A property nested under a ``record=True`` key may not be a bullet key the node declares."""
    for node in graph.ui_nodes:
        if not node.records:
            continue
        uitype = registry.UI_TYPES_BY_NAME.get(node.type)
        if uitype is None:
            continue
        rel = _rel_path(graph, node)
        for key, properties in node.records.items():
            spec = uitype.bullet_by_key.get(key)
            vocabulary = spec.properties if spec is not None else ()
            for prop in properties:
                if prop in uitype.bullet_by_key:
                    f.append(Finding(
                        "error", "misnested-bullet",
                        f"{node.id}: `{prop}:` is nested under `{key}:`, so it states a property "
                        f"of `{key}:` and not this node's own `{prop}:`",
                        path=rel, line=node.line, ref=f"{key}:{prop}",
                        suggestion=f"promote it to a top-level `- {prop}:` bullet of the node"))
                    continue
                if not vocabulary or prop in vocabulary:
                    continue
                f.append(Finding(
                    "error", "unknown-record-property",
                    f"{node.id}: `{key}:` carries `{prop}:`, which `{key}:` does not admit",
                    path=rel, line=node.line, ref=f"{key}:{prop}",
                    suggestion="one of: " + ", ".join(f"{name}:" for name in vocabulary)))


def _driven_kind_parser(predicate: Callable[[str], bool], reason: str) -> Callable[[str], str]:
    """Compose a `*_grammar(driver)` pair into a `values.VALUE_KINDS`-shaped parser."""
    def parse(value: str) -> str:
        return "" if predicate(runbook_mod.bullet_text(value)) else reason
    return parse


_DRIVER_VALUE_KINDS: dict[str, Callable[[str | None], tuple[Callable[[str], bool], str]]] = {
    "route": routes_mod.route_grammar,
    "selector": placement_mod.selector_grammar,
}


def _check_bullet_value_kinds(graph: Graph, ui_data: dict | None, f: list[Finding]) -> None:
    """A bullet whose key declares a ``value_kind`` must carry a value its kind's parser accepts."""
    surface_by_id = {n["id"]: n.get("surface", "") for n in ui_data["nodes"]} if ui_data else {}
    driver_by_surface: dict[str, str | None] = {}

    def _driver_for(node: UINode) -> str | None:
        if ui_data is None:
            return None
        surface = surface_by_id.get(node.id, "")
        if not surface:
            return None
        if surface not in driver_by_surface:
            driver_by_surface[surface] = reach.surface_driver(ui_data, surface)
        return driver_by_surface[surface]

    for node in graph.ui_nodes:
        uitype = registry.UI_TYPES_BY_NAME.get(node.type)
        if uitype is None:
            continue
        rel = _rel_path(graph, node)
        for key in uitype.bullet_keys:
            if not key.value_kind:
                continue
            kind = key.value_kind
            parser: Callable[[str], str]
            selector_driver_conflict = kind == "selector"
            if kind in _DRIVER_VALUE_KINDS:
                grammar = _DRIVER_VALUE_KINDS[kind]
                predicate, driver_reason = grammar(_driver_for(node))
                parser = _driven_kind_parser(predicate, driver_reason)
            else:
                parser = values_mod.VALUE_KINDS[kind]
            for index, value in enumerate(_bullet_values(node.meta.get(key.key, "")), 1):
                if not value.strip():
                    continue
                reason = parser(value)
                if not reason:
                    continue
                ref = refs_mod.bullet_ref(node.id, key.key, index)
                if selector_driver_conflict:
                    f.append(Finding(
                        "error", "conflicting-selector-driver",
                        f"{node.id}: `{key.key}: {value}` conflicts with this node's surface "
                        f"driver — {reason}",
                        path=rel, line=node.line, ref=ref))
                else:
                    f.append(Finding(
                        "error", "unparsable-bullet-value",
                        f"{node.id}: `{key.key}: {value}` does not parse as a "
                        f"`{key.value_kind}` value — {reason}",
                        path=rel, line=node.line, ref=ref))


def _check_fixture_grammar(graph: Graph, f: list[Finding]) -> None:
    """The fixture-node grammar (`docs/okf-runbook.md`'s fixture tier), held to its own rules."""
    if not runbook_mod.stack_runbooks(graph):
        return

    fixtures = {n.id: n for n in graph.ui_nodes_of_type("fixture")}
    by_name = {Path(n.id).stem: n for n in fixtures.values()}

    for node in fixtures.values():
        rel = _rel_path(graph, node)
        for step in runbook_mod.steps_of(graph, node):
            kind = _bullet_value(step.meta, "kind")
            if kind and kind not in _FIXTURE_STEP_KINDS:
                f.append(Finding(
                    "error", "fixture-step-kind",
                    f"{step.id}: `kind: {kind}` is not a fixture step kind",
                    path=rel, line=step.line, ref=kind,
                    suggestion="- kind: " + "|".join(sorted(_FIXTURE_STEP_KINDS))))
            if not _bullet_value(step.meta, "run"):
                f.append(Finding(
                    "error", "fixture-step-no-run",
                    f"{step.id}: no `run:` bullet — this step would run nothing",
                    path=rel, line=step.line))
            _check_step_command_bullets(step, rel, f)

    _check_fixture_needs_cycles(graph, fixtures, f)
    _check_needs_binding_args(graph, by_name, f)
    _check_fixture_call_args(graph, by_name, f)
    _check_fixture_undeclared_provides(graph, by_name, f)
    _check_provided_facts(graph, fixtures, f)
    _check_fixture_secret_names(graph, fixtures, f)


def _check_provided_facts(graph: Graph, fixtures: dict[str, UINode], f: list[Finding]) -> None:
    """Each `provides:` entry says where its fact comes from: observed, or asserted."""
    for node in fixtures.values():
        rel = _rel_path(graph, node)
        for entry in node.entries.get("provides", []):
            head = entry.headline.partition("\u2014")[0].split()
            if not head:
                continue
            key = head[0]
            observed = bool(entry.property_text("from"))
            asserted = bool(entry.property_text("is"))
            if observed != asserted:
                continue
            both = observed and asserted
            f.append(Finding(
                "error", "undetermined-provided-fact",
                f"{node.id}: `provides:` {key} declares "
                + ("both `from:` and `is:` — a fact is observed from a step's output or "
                   "asserted by the fixture's own construction, not both"
                   if both else
                   "neither `from:` nor `is:` — the book does not say whether this fact is "
                   "observed from a step's output or asserted by the fixture's own construction"),
                path=rel, line=node.line,
                ref=refs_mod.bullet_ref(node.id, "provides"),
                suggestion=(
                    "keep one: `- from:`/`- read:` for a fact a step printed, `- is:` for one "
                    "the fixture's own construction makes true"
                    if both else
                    "  - from: [<step>](#<step>)\n  - read: <json path>   # observed\n"
                    "  - is: <value>                              # or asserted")))


_ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _check_fixture_secret_names(graph: Graph, fixtures: dict[str, UINode], f: list[Finding]) -> None:
    """Every `secrets:` child is a plausible environment-variable name, nothing else."""
    for node in fixtures.values():
        rel = _rel_path(graph, node)
        for value in _bullet_values(node.meta.get("secrets", "")):
            name = value.strip()
            if name and not _ENV_NAME.match(name):
                f.append(Finding(
                    "error", "fixture-secret-name",
                    f"{node.id}: `secrets:` child {name!r} is not a valid environment "
                    "variable name — no value or mint recipe belongs here, only the NAME "
                    "the harness resolves from its own environment at run time",
                    path=rel, line=node.line, ref=name))


def _check_fixture_needs_cycles(graph: Graph, fixtures: dict[str, UINode], f: list[Finding]) -> None:
    """A `needs:` chain that composes a fixture on top of itself is unbuildable, not deferrable."""
    edges: dict[str, list[str]] = {node_id: [] for node_id in fixtures}
    for node in fixtures.values():
        for _text, href, _line in node.links:
            target = graph.find_ui_node(graph.resolve_doc_ref(href, origin=node.path))
            if target is not None and target.id in fixtures:
                edges[node.id].append(target.id)

    visited: set[str] = set()
    stack: list[str] = []

    def visit(node_id: str) -> None:
        if node_id in stack:
            cycle = stack[stack.index(node_id):] + [node_id]
            f.append(Finding(
                "error", "fixture-needs-cycle",
                f"fixture needs-cycle: {' -> '.join(cycle)}", ref=node_id))
            return
        if node_id in visited:
            return
        visited.add(node_id)
        stack.append(node_id)
        for dep in edges.get(node_id, []):
            visit(dep)
        stack.pop()

    for node_id in edges:
        visit(node_id)


def _fixture_declared_args(node: UINode) -> set[str]:
    """The parameter names a fixture node's own `args:` bullet declares."""
    return {name for value in _bullet_values(node.meta.get("args", "")) for name in value.split()}


def _fixture_declared_provides(node: UINode) -> set[str]:
    """The fact names a fixture node's `provides:` bullet declares, one per child."""
    keys: set[str] = set()
    for value in _bullet_values(node.meta.get("provides", "")):
        head = value.partition("—")[0].split()
        if head:
            keys.add(head[0])
    return keys


def _needs_binding(graph: Graph, node: UINode, by_name: dict[str, UINode],
                    value: str) -> tuple[UINode, tuple[str, ...]] | None:
    """A `needs:` child's target fixture and the `arg=value` tokens it binds, if any."""
    links = markdown.extract_refs(value).links
    if not links:
        return None
    text, href = links[0]
    target = graph.find_ui_node(graph.resolve_doc_ref(href, origin=node.path))
    if target is None:
        return None
    rest = value.replace(f"[{text}]({href})", "", 1).strip()
    parsed = fixtures_mod.parse_bullet(f"{Path(target.id).stem} {rest}".strip())
    if not isinstance(parsed, fixtures_mod.FixtureRef):
        return None
    return by_name.get(Path(target.id).stem, target), parsed.args


def _fixture_needs_supplied_args(node: UINode, graph: Graph, by_name: dict[str, UINode]) -> set[str]:
    """Names the fixture's own `needs:` bindings supply into its env before it runs."""
    supplied: set[str] = set()
    for value in _bullet_values(node.meta.get("needs", "")):
        binding = _needs_binding(graph, node, by_name, value)
        if binding is None:
            continue
        _target, args = binding
        supplied.update(tok.partition("=")[0] for tok in args if "=" in tok)
    return supplied


def _check_needs_binding_args(graph: Graph, by_name: dict[str, UINode], f: list[Finding]) -> None:
    """A `needs:` binding's `name=value` tokens name the CONSUMER's own declared `args:`."""
    for node in graph.ui_nodes:
        if node.type != "fixture":
            continue
        rel = _rel_path(graph, node)
        declared = _fixture_declared_args(node)
        for value in _bullet_values(node.meta.get("needs", "")):
            binding = _needs_binding(graph, node, by_name, value)
            if binding is None:
                continue
            target, args = binding
            if _fixture_declared_args(target):
                f.append(Finding(
                    "error", "fixture-needs-target-args",
                    f"{node.id}: needs `{target.id}`, which declares `args:` — runtime always "
                    "runs a needs target with no args, so a needs target may not declare any",
                    path=rel, line=node.line, ref=Path(target.id).stem))
            given = {tok.partition("=")[0] for tok in args if "=" in tok}
            unknown = given - declared
            if not unknown:
                continue
            f.append(Finding(
                "error", "fixture-arg-mismatch",
                f"{node.id}: `needs: {value}` binds {', '.join(sorted(unknown))} into its own "
                f"env, which {node.id} does not declare under `args:` "
                f"({', '.join(sorted(declared)) or '(none)'})",
                path=rel, line=node.line, ref=Path(target.id).stem))


def _check_fixture_call_args(graph: Graph, by_name: dict[str, UINode], f: list[Finding]) -> None:
    """A `fixture:` bullet's `name=value` args must match the target's declared `args:`."""
    for node in graph.ui_nodes:
        arrange = registry.fixture_keys(node.type)
        rel = _rel_path(graph, node)
        for key, value, _bullet in node.bullet_order:
            if key not in arrange:
                continue
            parsed = fixtures_mod.parse_bullet(value)
            if not isinstance(parsed, fixtures_mod.FixtureRef):
                continue
            target = by_name.get(parsed.name)
            if target is None:
                continue
            declared = _fixture_declared_args(target)
            given = {tok.partition("=")[0] for tok in parsed.args if "=" in tok}
            needs_supplied = _fixture_needs_supplied_args(target, graph, by_name)
            unknown = given - declared
            missing = declared - given - needs_supplied
            overlap = given & needs_supplied
            if not unknown and not missing and not overlap:
                continue
            parts = []
            if unknown:
                parts.append(f"passes {', '.join(sorted(unknown))}, which fixture '{target.id}' "
                             f"does not declare under `args:`")
            if missing:
                parts.append(f"never passes {', '.join(sorted(missing))}, which fixture "
                             f"'{target.id}' declares under `args:` and has no default")
            if overlap:
                parts.append(f"passes {', '.join(sorted(overlap))}, which fixture '{target.id}' "
                             "already receives from its own `needs:` bindings — two sources "
                             "for the same arg")
            f.append(Finding(
                "error", "fixture-arg-mismatch",
                f"{node.id}: `{key}: {value}` " + "; ".join(parts) +
                f" ({', '.join(sorted(declared)) or '(none)'})",
                path=rel, line=node.line, ref=parsed.name))


def _check_fixture_undeclared_provides(graph: Graph, by_name: dict[str, UINode], f: list[Finding]) -> None:
    """An `@node.key` reference must name a fact the target fixture actually declares."""
    for node in graph.ui_nodes:
        rel = _rel_path(graph, node)
        for key, value, _bullet in node.bullet_order:
            for ref in references.find_references(value):
                if not isinstance(ref, references.NodeRef):
                    continue
                target = by_name.get(ref.node)
                if target is None:
                    continue
                provides = _fixture_declared_provides(target)
                if ref.key not in provides:
                    f.append(Finding(
                        "error", "fixture-undeclared-provides",
                        f"{node.id}: `{key}: {value}` references `@{ref.node}.{ref.key}`, but "
                        f"fixture '{target.id}' does not declare `{ref.key}` under `provides:` "
                        f"({', '.join(sorted(provides)) or '(none)'})",
                        path=rel, line=node.line, ref=f"{ref.node}.{ref.key}"))


def _epic_ref(epic_name: str) -> str:
    return registry.epic_slug(epic_name.strip())


def _epic_by_ref(graph: Graph, epic_name: str) -> Epic | None:
    ref = _epic_ref(epic_name)
    return next((e for e in graph.epics if e.name == epic_name or _epic_ref(e.name) == ref), None)


def _milestone_ref_by_epic(graph: Graph) -> dict[str, list[str]]:
    owners: dict[str, list[str]] = {}
    for milestone in graph.milestones:
        for epic_name in milestone.epics:
            owners.setdefault(_epic_ref(epic_name), []).append(milestone.name)
    return owners


def _milestone_done(graph: Graph, milestone_name: str) -> bool:
    milestone = graph.milestone_by_name(milestone_name)
    if milestone is None:
        return False
    for epic_name in milestone.epics:
        epic = _epic_by_ref(graph, epic_name)
        if epic is None or not epic.stories or not all(select.is_done(story.status) for story in epic.stories):
            return False
    return True


def _transitive_milestone_deps(graph: Graph, milestone_name: str) -> set[str]:
    deps: set[str] = set()
    visiting: set[str] = set()

    def visit(name: str) -> None:
        if name in visiting:
            return
        visiting.add(name)
        milestone = graph.milestone_by_name(name)
        if milestone is None:
            visiting.discard(name)
            return
        for dep in milestone.depends_on:
            if dep not in deps:
                deps.add(dep)
                visit(dep)
        visiting.discard(name)

    visit(milestone_name)
    return deps


def gap_findings(gaps: list[Gap]) -> list[Finding]:
    """`compile_plan`'s gap report, in doctor's own vocabulary."""
    findings: list[Finding] = []
    for gap in gaps:
        message = f"{gap.obligation_id}: {gap.detail}"
        if gap.kind == "unresolved-precondition":
            findings.append(Finding("error", "unresolved-precondition", message, ref=gap.obligation_id))
        elif gap.kind == "unreachable-screen":
            findings.append(Finding("error", "unreachable-screen", message, ref=gap.obligation_id))
        elif gap.kind == "screen-preconditions-undeclared":
            findings.append(Finding("error", "screen-preconditions-undeclared", message, ref=gap.obligation_id))
        elif gap.kind == "needs-snapshot":
            findings.append(Finding("error", "needs-snapshot", message, ref=gap.obligation_id))
        elif gap.kind == "needs-target-backend":
            findings.append(Finding("error", "needs-target-backend", message, ref=gap.obligation_id))
        elif gap.kind == "needs-multi-target-runtime":
            findings.append(
                Finding("error", "needs-multi-target-runtime", message, ref=gap.obligation_id)
            )
        elif gap.kind == "invalid-http-method":
            findings.append(Finding("error", "invalid-http-method", message, ref=gap.obligation_id))
        elif gap.kind == "needs-out-of-band-observation":
            findings.append(
                Finding("error", "needs-out-of-band-observation", message, ref=gap.obligation_id)
            )
        elif gap.kind == "undeclared-entry-url":
            findings.append(Finding("error", "undeclared-entry-url", message, ref=gap.obligation_id))
        elif gap.kind == "undeclared-bundle-id":
            findings.append(Finding("error", "undeclared-bundle-id", message, ref=gap.obligation_id))
        elif gap.kind == "undeclared-launch-screen":
            findings.append(
                Finding("error", "undeclared-launch-screen", message, ref=gap.obligation_id)
            )
        elif gap.kind == "unreachable-from-launch":
            findings.append(
                Finding("error", "unreachable-from-launch", message, ref=gap.obligation_id)
            )
        elif gap.kind == "unresolved-extends":
            findings.append(Finding("error", "unresolved-extends", message, ref=gap.obligation_id))
        elif gap.kind == "undeclared-check-locator":
            findings.append(
                Finding("error", "undeclared-check-locator", message, ref=gap.obligation_id)
            )
        elif gap.kind == "unstated-claim-combiner":
            findings.append(
                Finding("error", "unstated-claim-combiner", message, ref=gap.obligation_id)
            )
        elif gap.kind == "unarranged-state":
            findings.append(Finding("error", "unarranged-state", message, ref=gap.obligation_id))
        elif gap.kind == "unarranged-journey":
            findings.append(Finding("error", "unarranged-journey", message, ref=gap.obligation_id))
        elif gap.kind == "unarranged-scenario":
            findings.append(
                Finding("error", "unarranged-scenario", message, ref=gap.obligation_id)
            )
        elif gap.kind == "unarranged-request-body":
            findings.append(
                Finding("error", "unarranged-request-body", message, ref=gap.obligation_id)
            )
        elif gap.kind == "unidentifiable-screen":
            findings.append(
                Finding("error", "unidentifiable-screen", message, ref=gap.obligation_id)
            )
        elif gap.kind == "unarranged-interaction-precondition":
            findings.append(
                Finding(
                    "error", "unarranged-interaction-precondition", message, ref=gap.obligation_id
                )
            )
        elif gap.kind == "unparsed-fixture":
            findings.append(Finding("error", "qa-fixture-bullet", message, ref=gap.obligation_id))
        elif gap.kind == "undetermined-provided-fact":
            findings.append(
                Finding("error", "undetermined-provided-fact", message, ref=gap.obligation_id)
            )
        elif gap.kind == "unparsed-check-bullet":
            findings.append(Finding("error", "unparsed-check", message, ref=gap.obligation_id))
        elif gap.kind == "unparsed-capture-bullet":
            findings.append(Finding("error", "unparsed-capture", message, ref=gap.obligation_id))
        elif gap.kind == "uncaptured-declaration":
            findings.append(Finding("error", "uncompilable-claim", message, ref=gap.obligation_id))
        elif gap.kind == "no-verify-declared":
            findings.append(
                Finding("warn", "undeclared-obligation", message, ref=gap.obligation_id)
            )
        elif gap.kind == "precondition-discharged-by-arrangement":
            findings.append(
                Finding(
                    "warn", "precondition-discharged-by-arrangement", message, ref=gap.obligation_id
                )
            )
        else:
            findings.append(Finding("error", "uncompilable-claim", message, ref=gap.obligation_id))
    return findings


def _check_milestone_cycles(graph: Graph, f: list[Finding]) -> None:
    visited: set[str] = set()
    stack: list[str] = []

    def visit(name: str) -> None:
        if name in stack:
            cycle = stack[stack.index(name):] + [name]
            f.append(Finding(
                "error", "milestone-cycle",
                f"milestone dependency cycle: {' -> '.join(cycle)}", ref=name))
            return
        if name in visited:
            return
        visited.add(name)
        stack.append(name)
        milestone = graph.milestone_by_name(name)
        if milestone is not None:
            for dep in milestone.depends_on:
                visit(dep)
        stack.pop()

    for milestone in graph.milestones:
        visit(milestone.name)


def _check_milestones(graph: Graph, f: list[Finding]) -> None:
    if not graph.milestones:
        return

    owners = _milestone_ref_by_epic(graph)
    source_owners: dict[str, list[str]] = {}
    for milestone in graph.milestones:
        for source_item in milestone.source_items:
            source_owners.setdefault(source_item, []).append(milestone.name)
    known_milestones = {m.name for m in graph.milestones} | {m.eid for m in graph.milestones}

    for milestone in graph.milestones:
        rel = milestone.path.relative_to(graph.root).as_posix()
        for dep in milestone.depends_on:
            if dep not in known_milestones:
                f.append(Finding(
                    "error", "dangling-milestone-dependency",
                    f"milestone '{milestone.name}' depends on unknown milestone '{dep}'",
                    ref=dep, path=rel, line=1))
        for epic_name in milestone.epics:
            if _epic_by_ref(graph, epic_name) is None:
                f.append(Finding(
                    "error", "dangling-milestone-epic",
                    f"milestone '{milestone.name}' lists unknown epic '{epic_name}'",
                    ref=epic_name, path=rel, line=1))

    for epic in graph.epics:
        refs = owners.get(_epic_ref(epic.name), [])
        if not refs:
            f.append(Finding(
                "error", "epic-without-milestone",
                f"epic '{epic.name}' is not assigned to any milestone", epic=epic.name, ref=epic.name))
        elif len(refs) > 1:
            f.append(Finding(
                "error", "epic-in-multiple-milestones",
                f"epic '{epic.name}' is assigned to multiple milestones: {', '.join(refs)}",
                epic=epic.name, ref=epic.name))

    for source_item, milestones in source_owners.items():
        if len(milestones) > 1:
            f.append(Finding(
                "error",
                "backlog-item-in-multiple-milestones",
                f"backlog item '{source_item}' is assigned to multiple milestones: "
                f"{', '.join(milestones)}",
                ref=source_item,
            ))

    _check_milestone_cycles(graph, f)


def _check_conformance(graph: Graph, f: list[Finding]) -> None:
    """OKF conformance + per-type frontmatter schema, walking every Concept on disk."""
    schema_by_base = {t.name: t.schema for t in registry.REGISTRY}
    etypes = registry.REGISTRY + dynamic_registry.as_entity_types(graph.template_kinds)
    seen: set = set()
    for etype in etypes:
        base = graph.doc_roots.get(etype.doc_root)
        if base is None or not base.is_dir():
            continue
        for path in sorted(base.glob(etype.location)):
            if not path.is_file() or path.name in registry.RESERVED_FILES or path in seen:
                continue
            seen.add(path)
            rel = path.relative_to(graph.root).as_posix()
            try:
                fm = dict(read_doc(path).frontmatter or {})
            except OSError as exc:
                f.append(Finding("error", "unreadable", f"{rel}: {exc}", path=rel))
                continue
            declared = registry.type_of(fm)
            if not declared:
                f.append(Finding("error", "okf-missing-type",
                                 f"{rel}: Concept has no non-empty `type` in frontmatter",
                                 path=rel, line=1))
                continue
            base = registry.base_type(declared)
            schema = schema_by_base.get(base) if base else None
            if schema:
                for msg in schemas.validate(fm, schema):
                    f.append(Finding("warn", "schema", f"{rel}: {msg}", path=rel))
    if graph.ids is not None:
        for msg in schemas.validate(graph.ids, "ids.schema.json"):
            f.append(Finding("warn", "schema", f"ids.json: {msg}"))


def _check_misplaced_book_pages(graph: Graph, f: list[Finding]) -> None:
    """A typed book page that has moved (or was authored) outside every doc root is invisible."""
    try:
        result = subprocess.run(
            ["git", "ls-files", "-z", "--", "*.md"],
            cwd=graph.root, capture_output=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return
    if result.returncode != 0:
        return
    roots = [p.resolve() for p in graph.doc_roots.values()]
    for rel in result.stdout.decode("utf-8", "replace").split("\0"):
        if not rel:
            continue
        path = graph.root / rel
        if path.name in registry.RESERVED_FILES or not path.is_file():
            continue
        try:
            fm = dict(read_doc(path).frontmatter or {})
        except OSError:
            continue
        declared = registry.type_of(fm)
        if not declared:
            continue
        resolved = path.resolve()
        if any(resolved.is_relative_to(root) for root in roots):
            continue
        if model.find_root(path.parent) != graph.root:
            continue
        f.append(Finding(
            "error", "misplaced-book-page",
            f"{rel}: declares `type: {declared}`, but the file sits outside every "
            f"configured doc root (`graph.doc_roots`), so no book check ever reads it — "
            f"move it under the doc root its type belongs to, or remove `type:` if it "
            f"was never meant to be a book page",
            path=rel, line=1, ref=declared))


def _check_misrooted_book_pages(graph: Graph, f: list[Finding]) -> None:
    """A typed page can sit inside *a* doc root and still be inside the *wrong* one."""
    try:
        result = subprocess.run(
            ["git", "ls-files", "-z", "--", "*.md"],
            cwd=graph.root, capture_output=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return
    if result.returncode != 0:
        return
    roots = {key: root.resolve() for key, root in graph.doc_roots.items() if root.is_dir()}
    for rel in result.stdout.decode("utf-8", "replace").split("\0"):
        if not rel:
            continue
        path = graph.root / rel
        if path.name in registry.RESERVED_FILES or not path.is_file():
            continue
        try:
            fm = dict(read_doc(path).frontmatter or {})
        except OSError:
            continue
        declared = registry.type_of(fm)
        if not declared:
            continue
        expected_key = registry.doc_root_of(declared)
        if expected_key is None:
            continue
        resolved = path.resolve()
        actual_key = next(
            (key for key, root in roots.items() if resolved.is_relative_to(root)), None)
        if actual_key is None or actual_key == expected_key:
            continue
        if model.find_root(path.parent) != graph.root:
            continue
        f.append(Finding(
            "error", "misrooted-book-page",
            f"{rel}: declares `type: {declared}`, whose registered doc root is "
            f"`{expected_key}`, but the file sits under `{actual_key}` instead — move it "
            f"under `{expected_key}` (or delete it, if it was scratch output that should "
            f"never have landed in the book)",
            path=rel, line=1, ref=declared))


_UI_HEADING_BY_LOWER = {h.lower(): h for h in registry.UI_HEADING_TO_TYPE}
_SYMBOL_PART = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_SPACE = re.compile(r"\s")


def _known_types(graph: Graph) -> set[str]:
    return (set(registry.REGISTRY_BY_NAME) | set(registry.UI_TYPES_BY_NAME)
            | {k.name for k in graph.template_kinds})


def _check_container_siblings(doc: markdown.MarkdownDoc, rel: str, f: list[Finding]) -> None:
    """No parent heading owns the same container heading twice (`### Fields` under one concept)."""
    def check(parent: markdown.Section | None, siblings: list[markdown.Section]) -> None:
        seen: dict[str, markdown.Section] = {}
        for section in siblings:
            title = section.title.strip()
            if title in registry.UI_HEADING_TO_TYPE:
                first = seen.setdefault(title, section)
                if first is not section:
                    owner = f"`{'#' * parent.level} {parent.title.strip()}`" if parent else rel
                    f.append(Finding(
                        "error", "duplicate-container-heading",
                        f"{rel}: {owner} has two `{'#' * section.level} {title}` sections "
                        f"(line {doc.body_offset + first.line_start + 1} and this one) — the "
                        f"second block's {registry.UI_HEADING_TO_TYPE[title]} nodes belong to "
                        f"whatever heading precedes them, which is not what a reader sees",
                        path=rel, line=doc.body_offset + section.line_start + 1, ref=title))
            check(section, section.children)

    check(None, doc.sections)


def _check_ui_file(graph: Graph, path, f: list[Finding]) -> None:
    rel = path.relative_to(graph.root).as_posix()
    try:
        doc = read_doc(path)
    except OSError:
        return
    fm = doc.frontmatter or {}
    declared = registry.type_of(fm)
    if declared and registry.base_type(declared) not in _known_types(graph):
        f.append(Finding("error", "unknown-type",
                         f"{rel}: type '{declared}' is not a recognized OKF type",
                         path=rel, line=1, ref=declared))

    for section in doc.walk_sections():
        if section.level != 2 or not section.children:
            continue
        title = section.title.strip()
        canon = _UI_HEADING_BY_LOWER.get(title.lower())
        if canon and title != canon:
            f.append(Finding("error", "bad-heading-type",
                             f"{rel}: `## {title}` should be `## {canon}` — its `### id` children "
                             f"are {registry.UI_HEADING_TO_TYPE[canon]} nodes",
                             path=rel, line=doc.body_offset + section.line_start + 1,
                             suggestion=f"## {canon}", fixable=True))

    _check_container_siblings(doc, rel, f)

    ftype = registry.ui_type(declared)
    if ftype is not None and ftype.kind == "file":
        for spec, problem in required_section_problems(doc, ftype.required_sections):
            if problem == "missing":
                f.append(Finding("error", "missing-required-section",
                                 f"{rel}: {ftype.name} is missing its required "
                                 f"`## {spec.heading}` section", path=rel, line=1,
                                 suggestion=f"## {spec.heading}", fixable=True))
            else:
                f.append(Finding("error", "empty-required-section",
                                 f"{rel}: {ftype.name} leaves empty its required "
                                 f"`## {spec.heading}` section", path=rel, line=1,
                                 suggestion=f"## {spec.heading}", fixable=False))


def _declares(path: Path, symbol: str) -> bool:
    """Whether the file at *path* declares *symbol* — `inventory`'s grammar, not a second one."""
    return inventory.declares_at(path, symbol)


def _check_test_subject(node, rel: str, f: list[Finding]) -> None:
    """`code:` cites the product, never the test suite (`refs.is_test_source`)."""
    cited: dict[str, None] = {}
    for value in refs_mod.code_refs(node.meta.get("code")):
        cited[refs_mod.ref_path(value)] = None
    tests = [path for path in cited if refs_mod.is_test_source(path)]
    if not tests:
        return
    ref = f"{node.id}#code"
    if len(tests) == len(cited):
        f.append(Finding(
            "error", "test-subject",
            f"{node.id}: every `code:` citation is test source ({', '.join(tests)}) — a book "
            f"documents product behavior a user can observe, not the test suite's mocks, fakes "
            f"or fixtures", path=rel, line=node.line, ref=ref,
            suggestion="delete the node (the whole page when it is the page's own node) and "
                       "the links that point at it"))
        return
    f.append(Finding(
        "error", "code-cites-test",
        f"{node.id}: `code:` cites test source ({', '.join(tests)}) beside the product it "
        f"documents", path=rel, line=node.line, ref=ref,
        suggestion="keep only product citations in `code:`; cite a proving test under `tests:`"))


def _check_code_grounding(graph: Graph, f: list[Finding],
                           checkouts: dict[str, Path] | None = None) -> None:
    """`code:` targets name a file that exists, and a symbol that file declares."""
    checkout_map = checkouts or {}
    own_repository = book_repository(features_root_of(graph))
    for node in graph.ui_nodes:
        rel = node.path.relative_to(graph.root).as_posix()
        _check_test_subject(node, rel, f)
        for ref in refs_mod.code_refs(node.meta.get("code")):
            try:
                parsed = refs_mod.parse_code_ref(ref)
            except ValueError:
                parsed = refs_mod.CodeRef("", ref)
            target_path, symbol = parsed.path, parsed.symbol
            source_root = graph.root
            if parsed.repository and parsed.repository != own_repository:
                checkout = checkout_for(parsed.repository, checkout_map, default=own_repository)
                if checkout is None:
                    f.append(Finding(
                        "warn", "unreachable-citation",
                        f"{node.id}: `code:` target '{ref}' names a repository "
                        f"('{parsed.repository}') this run has no checkout for",
                        path=rel, line=node.line, ref=ref,
                        suggestion=f"pass --checkout {parsed.repository}=<path> to check this "
                                   "citation"))
                    continue
                source_root = checkout
            separator = "::" if symbol else ""
            target = source_root / target_path
            if target.is_dir():
                f.append(Finding(
                    "error", "directory-code-ref",
                    f"{node.id}: `code:` target '{ref}' — '{target_path}' is a directory, "
                    "not a file",
                    path=rel, line=node.line, ref=ref,
                    suggestion="a path to the specific file that declares this, as "
                               "`path::symbol`"))
                continue
            if not target.is_file():
                f.append(Finding(
                    "error", "dangling-code-ref",
                    f"{node.id}: `code:` target '{ref}' — no such file '{target_path}'"
                    + (f" in checkout '{parsed.repository}'" if parsed.repository else ""),
                    path=rel, line=node.line, ref=ref,
                    suggestion="a path relative to the repo root, as `path::symbol`"))
                continue
            if parsed.digest is None:
                f.append(Finding(
                    "warn", "unstamped-citation",
                    f"{node.id}: `code:` target '{ref}' carries no `@digest` stamp",
                    path=rel, line=node.line, ref=ref, node=node.id,
                    suggestion="stamped when a turn that edits this node commits, or by the "
                               "catalog migration"))
            else:
                try:
                    source_bytes = target.read_bytes()
                except OSError:
                    pass
                else:
                    if stamp_mod.digest_file(source_bytes) != parsed.digest:
                        f.append(Finding(
                            "error", "stale-citation",
                            f"{node.id}: `code:` target '{ref}' — '{target_path}' has changed "
                            f"since this citation was stamped",
                            path=rel, line=node.line, ref=ref, node=node.id,
                            suggestion=f"re-read '{target_path}' and correct this node's claims "
                                       "if they no longer hold; the citation is restamped when "
                                       "the turn commits"))
            if not (separator and symbol):
                uitype = registry.UI_TYPES_BY_NAME.get(node.type)
                if uitype is None or uitype.kind == "file":
                    continue
                if target.suffix not in inventory.SOURCE_SUFFIXES:
                    continue
                f.append(Finding(
                    "error", "whole-file-code-ref",
                    f"{node.id}: `code:` target '{ref}' cites the whole of {target_path} — a "
                    f"`{node.type}` documents a part, and naming the file that contains it says "
                    f"only where to start looking, not where this node is grounded",
                    path=rel, line=node.line, ref=ref,
                    suggestion="cite the specific `path::symbol` this node is grounded in"))
                continue
            if _SPACE.search(symbol):
                continue
            try:
                grounded = _declares(target, symbol)
            except OSError:
                continue
            except UnicodeDecodeError:
                f.append(Finding(
                    "error", "undecodable-code-symbol",
                    f"{node.id}: `code:` target '{ref}' — '{target_path}' is not valid UTF-8, "
                    f"so '{symbol}' cannot be checked against it",
                    path=rel, line=node.line, ref=ref,
                    suggestion="cite a source file the symbol grounding pass can decode, or a "
                               "whole-file unit with no `::symbol`"))
                continue
            if not grounded:
                f.append(Finding(
                    "error", "missing-code-symbol",
                    f"{node.id}: `code:` target '{ref}' — '{target_path}' does not declare "
                    f"'{symbol}'", path=rel, line=node.line, ref=ref))


def _resolved_targets(node, key: str, resolver: links_mod.LinkResolver) -> set[str]:
    """The node ids *node*'s `key:` links resolve to — dangling links contribute nothing (they are `unresolved-relation`'s finding, not this caller's)."""
    out: set[str] = set()
    for value in _bullet_values(node.meta.get(key, "")):
        for _text, href in markdown.extract_refs(value).links:
            target = resolver.resolve(node.path, href)
            if target is not None and target.resolved:
                out.add(target.node_id)
    return out


def _arranges_anything(node) -> bool:
    """Whether *node* declares an arrangement at all, by value rather than by key."""
    return any(_bullet_values(node.meta.get(key, ""))
               for key in registry.arrange_keys(node.type))


def _alternation_conflict(a: checks.CheckCall, b: checks.CheckCall) -> bool:
    """Whether *a* and *b* are the same check, on the same subject, claiming two different expected values — `unspelled-alternation`'s predicate."""
    if a.name != b.name or len(a.args) < 2 or a.args.keys() != b.args.keys():
        return False
    diffs = [key for key in a.args if a.args[key] != b.args[key]]
    if len(diffs) != 1:
        return False
    spec = checks.CHECK_BY_NAME[a.name]
    return not any(param.name == diffs[0] and param.identifies for param in spec.params)


def _check_self_relation(graph: Graph, f: list[Finding],
                         resolver: links_mod.LinkResolver) -> None:
    """`self-relation` — a relation bullet whose target resolves to the node it is written on."""
    for node in graph.ui_nodes:
        for key in registry.RELATION_KEYS:
            for index, value in enumerate(_bullet_values(node.meta.get(key, "")), start=1):
                for _text, href in markdown.extract_refs(value).links:
                    target = resolver.resolve(node.path, href)
                    if target is None or not target.resolved:
                        continue
                    if target.node_id != node.id:
                        continue
                    rel = node.path.relative_to(graph.root).as_posix()
                    f.append(Finding(
                        "error", "self-relation",
                        f"{node.id}: `{key}: {href}` resolves to this same node — a relation "
                        f"is between two things, so a node cannot be its own `{key}:` target",
                        path=rel, line=node.line,
                        ref=refs_mod.bullet_ref(node.id, key, index),
                        suggestion=f"point `{key}:` at the other node, or delete the bullet"))


def _check_judgment(graph: Graph, f: list[Finding],
                    resolver: links_mod.LinkResolver) -> None:
    """The judgment gap: a succession the book records without adjudicating."""
    for node in graph.ui_nodes:
        if node.type != "concept" or not _resolved_targets(node, "deprecates", resolver):
            continue
        if node.meta.get("prefers") or node.meta.get("rule"):
            continue
        rel = node.path.relative_to(graph.root).as_posix()
        f.append(Finding(
            "warn", "deprecation-without-successor",
            f"{node.id}: `deprecates:` names a node but no `prefers:` or `rule:` says "
            f"what replaces it — a deprecation with no successor reads as \"delete "
            f"this\", which is usually wrong",
            path=rel, line=node.line, ref=refs_mod.bullet_ref(node.id, "deprecates"),
            suggestion="- prefers: [<winning node>](<path>)   # or a `rule:` stating "
                       "when the deprecated one is still the right call"))


def _check_same_as_symmetry(graph: Graph, f: list[Finding],
                            resolver: links_mod.LinkResolver) -> None:
    """`one-way-same-as` — a `same-as:` claim declared on one side only."""
    by_id = {node.id: node for node in graph.ui_nodes}
    for node in graph.ui_nodes:
        if not node.meta.get("same-as"):
            continue
        for value in _bullet_values(node.meta.get("same-as")):
            for _text, href in markdown.extract_refs(value).links:
                target = resolver.resolve(node.path, href)
                if target is None or not target.resolved:
                    continue
                target_node = by_id.get(target.node_id)
                if target_node is None:
                    continue
                back = _resolved_targets(target_node, "same-as", resolver)
                if node.id in back:
                    continue
                rel = node.path.relative_to(graph.root).as_posix()
                target_rel = target_node.path.relative_to(graph.root).as_posix()
                back_href = os.path.relpath(node.path, start=target_node.path.parent)
                f.append(Finding(
                    "error", "one-way-same-as",
                    f"{node.id}: `same-as:` claims '{href}' ({target.node_id}) is the same "
                    f"documented thing, but {target_rel!r} declares no `same-as:` back — "
                    f"sameness is symmetric, so the claim must be written on both "
                    f"occurrences",
                    path=rel, line=node.line, ref=href,
                    suggestion=f"on {target_rel}: "
                               f"- same-as: [{node.title or node.id}]({back_href})"))


def _check_same_as_disagreement(graph: Graph, f: list[Finding],
                                resolver: links_mod.LinkResolver) -> None:
    """`same-as-disagreement` — a `same-as:` family states two different values for one normative key."""
    by_id = {node.id: node for node in graph.ui_nodes}
    adjacency: dict[str, set[str]] = {}
    for node in graph.ui_nodes:
        if not node.meta.get("same-as"):
            continue
        for target_id in _resolved_targets(node, "same-as", resolver):
            if target_id not in by_id:
                continue
            adjacency.setdefault(node.id, set()).add(target_id)
            adjacency.setdefault(target_id, set()).add(node.id)

    seen: set[str] = set()
    for node in graph.ui_nodes:
        if node.id in seen or node.id not in adjacency:
            continue
        component: set[str] = {node.id}
        frontier = [node.id]
        while frontier:
            current = frontier.pop()
            for neighbor in adjacency.get(current, ()):
                if neighbor not in component:
                    component.add(neighbor)
                    frontier.append(neighbor)
        seen.update(component)
        members = [by_id[i] for i in component]
        if len(members) < 2:
            continue

        keys: set[str] = set()
        for member in members:
            keys.update(registry.normative_keys(member.type))

        root = by_id[min(component)]
        rel = root.path.relative_to(graph.root).as_posix()

        for key in sorted(keys):
            declared: list[tuple[UINode, tuple[str, ...]]] = []
            for member in members:
                values = tuple(sorted(
                    v.strip() for v in _bullet_values(member.meta.get(key, "")) if v.strip()))
                if values:
                    declared.append((member, values))
            if len({values for _, values in declared}) < 2:
                continue
            declared.sort(key=lambda pair: pair[0].id)
            stated = "; ".join(
                f"{member.id} states {list(values)}" for member, values in declared)
            f.append(Finding(
                "error", "same-as-disagreement",
                f"{root.id}: `same-as:` family disagrees about `{key}:` — {stated} — "
                f"but `same-as:` claims these occurrences are one documented thing, which "
                f"means one true value; either the claim or one of the occurrences is wrong",
                path=rel, line=root.line, ref=f"{root.id}:{key}",
                related=sorted(component)))


def _check_unspecified(graph: Graph, f: list[Finding],
                       resolver: links_mod.LinkResolver) -> None:
    """`ungrounded-unspecified` — a resolved-by-design claim with nothing that resolved it."""
    for node in graph.ui_nodes:
        for index, value in enumerate(_bullet_values(node.meta.get("unspecified", "")), 1):
            links = markdown.extract_refs(value).links
            grounded = any(
                (target := resolver.resolve(node.path, href)) is not None and target.resolved
                for _text, href in links
            )
            if grounded:
                continue
            rel = node.path.relative_to(graph.root).as_posix()
            what = ("its citation does not resolve" if links
                    else "it cites no record at all")
            f.append(Finding(
                "error", "ungrounded-unspecified",
                f"{node.id}: `unspecified:{index}` ({_prose(value).strip()}) claims the "
                f"behaviour is resolved by design, but {what} — nothing distinguishes it "
                f"from a gap someone decorated",
                path=rel, line=node.line,
                ref=refs_mod.bullet_ref(node.id, "unspecified", index),
                suggestion="link the record that settled it — a decision doc, an "
                           "acceptance criterion, a stated convention; with nothing to "
                           "cite, delete the bullet"))


MAX_NORMATIVE_PROSE = 700

_OBSERVATION_KEYS: frozenset[str] = frozenset(
    b.key for t in registry.UI_TYPES for b in t.bullet_keys if b.check)
_STATUS_CODE = re.compile(r"[1-5]\d{2}")
_STATUS_LIKE_CHECKS = frozenset({"http_status", "exit_status"})
_STATUS_DONOR_KEY = {"command": "exits", "endpoint": "status", "invocation": "status"}
_ERROR_NAME = re.compile(r"\b[A-Z][A-Za-z0-9]*(?:Error|Exception|Conflict|Failure|Denied)\b")
_SEMICOLON_CLAUSE = re.compile(r";\s+(?:\S+\s+){2}\S")
_CLAUSE_AND = re.compile(r"[,;]\s+and\b")
_ANY_AND = re.compile(r"\band\b")


def _code_in_text(code: int, text: str) -> bool:
    """True when *code* appears in *text* as its own number, not as a run inside a longer one."""
    return re.search(rf"(?<!\d){code}(?!\d)", text) is not None


def _status_codes(value: str) -> list[str]:
    """The HTTP statuses this bullet names, in order — read out of its code spans only."""
    return [span for span in markdown.all_code_spans(value) if _STATUS_CODE.fullmatch(span)]


def _error_names(value: str) -> list[str]:
    """The failures this bullet names, in order — out of its code spans, like `_status_codes`."""
    return [name for span in markdown.all_code_spans(value)
            for name in _ERROR_NAME.findall(span)]


def _outside_parentheses(value: str) -> str:
    """*value* with every parenthesised span removed, nesting included."""
    out: list[str] = []
    depth = 0
    for char in value:
        if char == "(":
            depth += 1
        elif char == ")" and depth:
            depth -= 1
            continue
        if not depth:
            out.append(char)
    return "".join(out)


def _split_signals(value: str) -> list[str]:
    """Why this bullet looks like several observations, one sentence per reason (or none)."""
    reasons: list[str] = []
    statuses = sorted(set(_status_codes(value)))
    if len(statuses) > 1:
        reasons.append(f"it names {len(statuses)} status codes ({', '.join(statuses)})")
    names = sorted(set(_error_names(value)))
    if len(names) > 1:
        reasons.append(f"it names {len(names)} distinct failures ({', '.join(names)})")
    if _SEMICOLON_CLAUSE.search(_outside_parentheses(_prose(value))):
        reasons.append("a semicolon joins two independent clauses (when the second only "
                       "explains the first, keep it as an aside in parentheses instead)")
    if _CLAUSE_AND.search(value) and len(_ANY_AND.findall(value)) > 1:
        reasons.append("`and` joins clauses more than once")
    return reasons


def _prose(value: str) -> str:
    """A bullet's prose: link text without its href, no code spans, parentheticals kept."""
    return markdown.prose_text(value)


def _bullet_values(value) -> list[str]:
    """A bullet's raw values — a repeated key parses to a list, a single one to a string."""
    if isinstance(value, list):
        return [str(item) for item in value]
    return [str(value)] if value else []


LIFECYCLE_VERBS = frozenset({
    "creates", "creating", "adds", "adding", "registers", "registering",
    "inserts", "inserting", "provisions", "provisioning",
    "deletes", "deleting", "removes", "removing", "revokes", "revoking",
    "archives", "archiving", "purges", "purging",
})

LIFECYCLE_CHECKS = frozenset({"created", "removed"})

NON_ACTION_KEYS = frozenset({"semantics", "required", "default", "consumes"})

_WORD = re.compile(r"[a-zA-Z']+")

_NEGATORS = frozenset({"no", "not", "never", "without", "instead", "rather", "than", "nor",
                       "neither", "avoids", "avoid", "skips", "skip"})

_NEGATIVE_DETERMINERS = frozenset({"no", "none", "nothing", "neither"})

_ALTERNATIVE_MARKERS = frozenset({"or", "otherwise"})
_ALTERNATIVE_MUTATIONS = frozenset({
    "strip", "strips", "stripping", "update", "updates", "updating",
    "replace", "replaces", "replacing", "reuse", "reuses", "reusing",
    "restore", "restores", "restoring", "unset", "unsets", "unsetting",
}) | LIFECYCLE_VERBS
_PRIOR_STATE_CUES = frozenset({
    "already", "existing", "exists", "present", "absent", "missing",
})


def _is_one_arm_of_a_verb_alternation(words: list[str], lifecycle_index: int) -> bool:
    """Whether the verb is coordinated directly against another mutation: `restores or removes`."""
    pairs = zip(words, words[1:])
    return any(
        (first in _ALTERNATIVE_MUTATIONS and second in _ALTERNATIVE_MARKERS)
        or (first in _ALTERNATIVE_MARKERS and second in _ALTERNATIVE_MUTATIONS)
        for index, (first, second) in enumerate(pairs)
        if index != lifecycle_index and index + 1 != lifecycle_index
    )


def _has_state_dependent_alternative(words: list[str], lifecycle_index: int) -> bool:
    """Whether a lifecycle verb is one branch of a toggle or idempotent upsert."""
    if _is_one_arm_of_a_verb_alternation(words, lifecycle_index):
        return True
    rest = words[lifecycle_index + 1:]
    if not any(word in _PRIOR_STATE_CUES for word in rest):
        return False
    return any(
        any(word in _ALTERNATIVE_MUTATIONS for word in rest[index + 1:])
        for index, marker in enumerate(rest)
        if marker in _ALTERNATIVE_MARKERS
    )


def _states_a_lifecycle_claim(value: str) -> str:
    """The lifecycle verb this bullet uses, or "" — the word a finding has to quote."""
    words = [word.lower() for word in _WORD.findall(_prose(value))]
    for n, word in enumerate(words):
        if word not in LIFECYCLE_VERBS:
            continue
        if any(before in _NEGATORS for before in words[max(0, n - 2):n]):
            continue
        if words[n + 1:n + 2] and words[n + 1] in _NEGATIVE_DETERMINERS:
            continue
        if _has_state_dependent_alternative(words, n):
            continue
        return word
    return ""


_MODAL = re.compile(r"\b(must|shall|never|always|rejects?|returns?|exits? with)\b", re.I)


def _sounds_normative(value: str) -> str:
    """Why this bullet reads like a claim — one short phrase naming the signal — or ""."""
    statuses = _status_codes(value)
    if statuses:
        return f"names status {statuses[0]}"
    names = _error_names(value)
    if names:
        return f"names `{names[0]}`"
    verb = _states_a_lifecycle_claim(value)
    if verb:
        return f"states a lifecycle change, `{verb}`"
    modal = _MODAL.search(_prose(value))
    if modal:
        return f"says `{modal.group(0)}`"
    return ""


_REPR_LITERAL = re.compile(r"\b(?:None|True|False)\b")


def _matches_repr_spelled(pattern: str) -> bool:
    """Whether *pattern*, a `json_path(matches=...)` value, is spelled against Python `repr`."""
    return bool(_REPR_LITERAL.search(pattern))


def _rubber_stamp(call: checks.CheckCall) -> str:
    """Why this call would stay green against the defect its bullet describes, or ""."""
    if call.name == "json_path":
        matches = call.args.get("matches")
        admits_other = matches is not None and sensitivity.matches_admits_other(str(matches))
        if not admits_other and ({"equals", "matches"} & set(call.args) or call.args.get("absent") is True):
            return ""
        return (f"`{call.text()}` asserts the field is present without saying what it "
                f"holds, which admits {checks.CHECK_BY_NAME[call.name].excludes}")
    if call.name != "http_status":
        return ""
    code = call.args.get("code")
    if not isinstance(code, int) or not (200 <= code < 300):
        return ""
    if {"title", "path"} & set(call.args):
        return ""
    return (f"`{call.text()}` says the request succeeded and nothing about which request "
            f"or what it answered, which admits {checks.CHECK_BY_NAME[call.name].excludes}")


def _ui_graph(graph: Graph, resolver: links_mod.LinkResolver) -> dict | None:
    """The resolved node/edge dump, or None when it will not build."""
    try:
        return graph_mod.build(graph, resolver=resolver)
    except (OSError, ValueError, RuntimeError, KeyError):
        return None


def _check_reachability(data: dict, f: list[Finding]) -> None:
    """Every screen must be reachable by clicking from the surface's root."""
    surfaces = {n["surface"] for n in data["nodes"] if n["type"] == "screen"}
    for surface in sorted(s for s in surfaces if s):
        driver = reach.surface_driver(data, surface)
        scoped = graph_mod.subset(data, surface)
        screens = reach.screens_of(scoped)
        if not screens:
            continue
        unreachable, root, _seeds, reason = reach.unreachable_screens(
            scoped, driver, surface=surface)
        if root is None:
            driver_note = f" ({driver} driver)" if driver else ""
            if reason == reach.NO_PATH_ROOT:
                path, server = reach.root_path(scoped, driver)
                source = (f"the path of {server}'s `entry-url:`" if server
                          else "the app root, no server contract states another")
                f.append(Finding("warn", "no-root-screen",
                                 f"{surface}{driver_note}: no screen's `route:` is `{path}` "
                                 f"({source}) — reachability cannot be checked for this surface",
                                 ref=surface, suggestion=f"- route: `{path}`"))
            else:
                if reason == reach.LAUNCH_SCREEN_NOT_SCREEN:
                    reason_note = (
                        "states a `launch-screen:` on its runbook that is not a screen on it")
                elif reason == reach.NO_LAUNCH_SCREEN:
                    reason_note = "states no `launch-screen:` on its runbook"
                else:
                    raise AssertionError(
                        f"surface {surface!r} passes a surface to unreachable_screens, so "
                        f"surface_root cannot return {reason!r}"
                    )
                f.append(Finding("warn", "no-root-screen",
                                 f"{surface}{driver_note}: {reason_note} — reachability cannot "
                                 f"be checked for this surface",
                                 ref=surface, suggestion="- launch-screen: [<screen>](<path>)"))
            continue
        for screen in unreachable:
            node = next((n for n in scoped["nodes"] if n["id"] == screen), None)
            prose = reach.prose_entry(node) if node else ""
            if prose:
                why = (f"`entry: {prose}` is not a route a walk can open — state the path "
                       f"(`entry: /…`) or add a `leads-to:` on the component that navigates here")
            else:
                why = ("add a `leads-to:` on the component that navigates here, or `entry: /…` "
                       "with the route if it is entered from outside the app")
            f.append(Finding("error", "unreachable-screen",
                             f"{screen}: no documented path reaches this screen from {root} — {why}",
                             path=screen, line=node["line"] if node else 0, ref=screen,
                             suggestion="- leads-to: [<this screen>](<path>)"))


def _check_unknown_driver(data: dict, f: list[Finding]) -> None:
    """A runbook's `driver:` must be one of the seven values `drivers.DRIVERS` declares."""
    for node in data["nodes"]:
        if node["type"] != reach.RUNBOOK_TYPE or node["kind"] != "file":
            continue
        driver = runbook_mod.bullet_value(node["bullets"], reach.DRIVER_BULLET).strip().lower()
        if not driver:
            continue
        if driver in drivers.DRIVERS:
            continue
        legal = ", ".join(drivers.DRIVERS)
        f.append(Finding("error", "unknown-driver",
                         f"{node['path']}: `driver: {driver}` is not one of the driver "
                         f"vocabulary's values ({legal})",
                         path=node["path"], line=node["line"], ref=node["id"],
                         suggestion=f"- driver: <one of {legal}>"))


def _check_runbook_driver_surface(data: dict, f: list[Finding]) -> None:
    """A runbook's `driver:` must be able to perform against at least one of its `surfaces:`."""
    by_id = {n["id"]: n for n in data["nodes"]}
    for node in data["nodes"]:
        if node["type"] != reach.RUNBOOK_TYPE or node["kind"] != "file":
            continue
        driver = runbook_mod.bullet_value(node["bullets"], reach.DRIVER_BULLET).strip().lower()
        if not driver:
            continue
        performable = routes_mod.performable_surface_types(driver)
        if not performable:
            continue
        surfaces = [by_id[edge["to"]] for edge in node["edges"]
                   if edge["via"] == reach.SURFACES_BULLET and edge["to"] in by_id]
        surface_types = {s["type"] for s in surfaces}
        if surface_types & performable:
            continue
        performed = ", ".join(sorted(performable))
        seen = ", ".join(sorted(surface_types)) if surface_types else "none declared"
        f.append(Finding("warn", "no-drivable-surface",
                         f"{node['path']}: `driver: {driver}` performs against "
                         f"{performed} surfaces, but its `surfaces:` resolve to {seen} — "
                         f"point `surfaces:` at a node of the right type, or fix `driver:`",
                         path=node["path"], line=node["line"], ref=node["id"],
                         suggestion=f"- surfaces: [<name>](<path/to/{sorted(performable)[0]}.md>)"))


def _check_runbook(graph: Graph, f: list[Finding]) -> None:
    """The book must say how this system comes up, and say it in a shape QA can run."""
    runbooks = graph.ui_nodes_of_type("runbook")
    stacks = {n.id for n in runbook_mod.stack_runbooks(graph)}
    if (
        not stacks
        and runbook_mod.has_served_surface(graph)
        and runbook_mod.select_server(graph) is None
    ):
        f.append(Finding("error", "runbook-missing",
                         "no `runbook` node brings a system up: the book describes a surface "
                         "that has to be served and never says how it starts, so QA has no "
                         "stack to run against",
                         suggestion="ostler scaffold runbook qa-stack --service <service>"))

    for node in runbooks:
        rel = _rel_path(graph, node)
        meta = node.meta
        reuse = _bullet_value(meta, "reuse")
        if reuse and reuse not in runbook_mod.REUSE_POLICIES:
            f.append(Finding("error", "runbook-bad-reuse",
                             f"{rel}: `reuse: {reuse}` is not an adoption policy",
                             path=rel, line=node.line, ref=reuse,
                             suggestion="- reuse: " + " | ".join(sorted(runbook_mod.REUSE_POLICIES))))

        steps = runbook_mod.steps_of(graph, node)
        services = []
        for step in steps:
            kind = _bullet_value(step.meta, "kind")
            if kind and kind not in runbook_mod.STEP_KINDS:
                f.append(Finding("error", "runbook-bad-kind",
                                 f"{step.id}: `kind: {kind}` is not a boot-step kind",
                                 path=rel, line=step.line, ref=kind,
                                 suggestion="- kind: " + "|".join(sorted(runbook_mod.STEP_KINDS))))
            if kind == "service":
                services.append(step)
            _check_step_command_bullets(step, rel, f)
            _check_step_not_scenario_frame(step, rel, f)

        if node.id not in stacks:
            _check_runbook_environment(graph, node, rel, f)
            continue

        if not services:
            f.append(Finding("error", "runbook-incomplete",
                             f"{rel}: declares a launch but has no `kind: service` step — "
                             f"nothing here starts the system",
                             path=rel, line=node.line, ref=node.id,
                             suggestion="### start\n- kind: service\n- run: <bring-up command>"))
        elif len(services) > 1:
            f.append(Finding("error", "runbook-multi-service",
                             f"{rel}: {len(services)} `kind: service` steps — a runbook brings "
                             f"up one stack, so the rest belong in `kind: prepare`",
                             path=rel, line=services[1].line, ref=node.id,
                             suggestion="- kind: prepare"))
        elif not _bullet_value(meta, "entry-url") and not _bullet_value(services[0].meta, "health"):
            f.append(Finding("error", "runbook-incomplete",
                             f"{rel}: nothing proves the stack is up — give the runbook an "
                             f"`entry-url:` or the service step a `health:` gate",
                             path=rel, line=node.line, ref=node.id,
                             suggestion="- entry-url: http://localhost:<port>"))

        _check_runbook_environment(graph, node, rel, f)


def _check_runbook_environment(graph: Graph, node, rel: str, f: list[Finding]) -> None:
    """A `local-only: true` environment must name only local services."""
    for _text, href, _line in node.links:
        target = graph.find_ui_node(graph.resolve_doc_ref(href, origin=node.path))
        if target is None or target.type != "environment":
            continue
        if _bullet_value(target.meta, "local-only") not in ("true", "yes"):
            continue
        for service in _remote_services(target.meta):
            f.append(Finding("error", "runbook-local-only",
                             f"{rel}: boots `{target.id}`, which is `local-only: true`, but "
                             f"that environment points at {service}",
                             path=rel, line=node.line, ref=target.id,
                             suggestion="point it at localhost, or drop `local-only: true`"))


_STEP_COMMAND_KEYS: tuple[str, ...] = ("run", "health")


def _check_step_command_bullets(step: UINode, rel: str, f: list[Finding]) -> None:
    """A `run:`/`health:` bullet is shelled, never parsed — a check expression there is wrong."""
    for key in _STEP_COMMAND_KEYS:
        value = runbook_mod.bullet_value(step.meta, key)
        if not value or not checks.is_check_expression(value):
            continue
        f.append(Finding(
            "error", "check-expression-as-command",
            f"{step.id}: `{key}:` ({value}) is a check expression, not a shell command — "
            f"`{key}:` is shelled at bring-up time, so this would fail with a bash syntax "
            f"error instead of running; write a shell command that exits non-zero on "
            f"failure (e.g. `curl -fsS <url>`), or move this check onto the `verify:` of "
            f"the claim it actually observes",
            path=rel, line=step.line, ref=refs_mod.bullet_ref(step.id, key),
            suggestion=f"- {key}: curl -fsS <url>"))


def _check_step_not_scenario_frame(step: UINode, rel: str, f: list[Finding]) -> None:
    """A runbook step's `working-directory: scenario:` names a frame that does not exist yet."""
    value = runbook_mod.bullet_value(step.meta, "working-directory")
    if not runbook_mod.is_scenario_frame(value):
        return
    f.append(Finding(
        "error", "runbook-scenario-frame",
        f"{step.id}: `working-directory: {runbook_mod.SCENARIO_FRAME_TOKEN}` names a "
        f"scenario's own directory, but this step runs at bring-up, before any scenario "
        f"exists to name — state a path, or drop the bullet to run at the checkout root",
        path=rel, line=step.line, ref=refs_mod.bullet_ref(step.id, "working-directory"),
        suggestion="- working-directory: <path>"))


_LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "0.0.0.0", "::1", "[::1]", "host.docker.internal"})


def _remote_services(meta: dict) -> list[str]:
    """The `services:` children of an environment whose host is not this machine."""
    children = meta.get("services") or []
    if isinstance(children, str):
        children = [children]
    remote = []
    for child in children:
        text = str(child)
        idx = markdown.label_colon_index(text)
        url = text[idx + 1:].strip().strip("`").strip() if idx != -1 else ""
        host = urlparse(url).hostname if "://" in url else ""
        if not host:
            continue
        if host in _LOCAL_HOSTS or host.endswith((".localhost", ".local")):
            continue
        remote.append(host)
    return remote


_UNAVAILABLE_WORDS = frozenset({
    "disabled", "greyed", "grayed", "readonly", "read-only", "inactive", "unclickable",
})

_AVAILABILITY_CHECKS = frozenset({"actionable", "inert"})


def _availability_observed(graph: Graph) -> set[str]:
    """Every node id some `actionable(...)`/`inert(...)` call in this book points at."""
    observed: set[str] = set()
    for node in graph.ui_nodes:
        for key in registry.check_keys(node.type):
            for value in _bullet_values(node.meta.get(key, "")):
                parsed = checks.parse_check(value)
                if (not isinstance(parsed, checks.CheckCall)
                        or parsed.name not in _AVAILABILITY_CHECKS):
                    continue
                target = loc_mod.located_node(graph, str(parsed.args.get("locator", "")),
                                              node.path)
                if target is not None:
                    observed.add(target.id)
    return observed


def _check_availability_states(graph: Graph, f: list[Finding]) -> None:
    """A `states:` bullet saying the control cannot be used, with nothing observing it."""
    observed = _availability_observed(graph)
    for node in graph.ui_nodes:
        if node.id in observed:
            continue
        rel = node.path.relative_to(graph.root).as_posix()
        for index, value in enumerate(_bullet_values(node.meta.get("states", "")), 1):
            words = set(re.split(r"[^a-z-]+", value.lower()))
            if not words & _UNAVAILABLE_WORDS:
                continue
            f.append(Finding(
                "warn", "unchecked-availability-state",
                f"{node.id}: `states:{index}` ({value}) says the user cannot act on this "
                f"control, and no `actionable(...)`/`inert(...)` call in this book names it "
                f"— the claim is about what the user can do, which one of those two "
                f"observes, and `visible(...)` does not",
                path=rel, line=node.line,
                ref=refs_mod.bullet_ref(node.id, "states", index),
                suggestion=f'- verify: inert(locator="#{node.id.rpartition("#")[2]}")'))
            break


def _bullet_value(meta: dict, key: str) -> str:
    """One bullet, read exactly as the runbook reader reads it, folded for comparison."""
    return runbook_mod.bullet_value(meta, key).lower()


def _rel_path(graph: Graph, node) -> str:
    try:
        return node.path.resolve().relative_to(graph.root.resolve()).as_posix()
    except (ValueError, OSError):
        return node.path.as_posix()


def _check_locators(data: dict, f: list[Finding]) -> None:
    """Every documented control must map to exactly one Playwright locator."""
    by_id = {n["id"]: n for n in data["nodes"]}

    def _at(node_id: str) -> dict:
        node = by_id.get(node_id, {})
        return {"path": node_id.split("#")[0], "line": node.get("line", 0)}

    for collision in loc_mod.collisions(data):
        named = f" name={collision['name']!r}" if collision["name"] else " with no name"
        for node_id in collision["nodes"]:
            f.append(Finding(
                "error", "ambiguous-locator",
                f"{node_id}: role={collision['role']}{named} also matches "
                + ", ".join(o.split("#")[-1] for o in collision["nodes"] if o != node_id)
                + " on the same screen — `getByRole` cannot tell them apart",
                ref=refs_mod.collision_ref(node_id, collision),
                suggestion="give each control a distinct accessible `name:`",
                **_at(node_id)))

    for bad in loc_mod.invalid_roles(data):
        f.append(Finding(
            "error", "invalid-role",
            f"{bad['node']}: `role: {bad['role']}` is not an ARIA role — `getByRole` would match "
            f"nothing; state the bare computed role, and put any caveat in prose",
            ref=bad["node"], suggestion="- role: <one bare ARIA role, or `none`>",
            **_at(bad["node"])))

    for unnamed in loc_mod.unnamed_interactives(data):
        f.append(Finding(
            "error", "unnamed-interactive",
            f"{unnamed['node']}: role={unnamed['role']} is operable but has no accessible "
            f"`name:` — unannounceable to assistive tech and unaddressable by `getByRole`",
            ref=unnamed["node"],
            suggestion="- name: <the control's visible label or aria-label>",
            **_at(unnamed["node"])))

    for item in loc_mod.static_templates(data):
        var = item["iterates"]
        f.append(Finding(
            "error", "static-template",
            f"{item['node']}: repeats one-per `{var}` but `name:` {item['template']!r} carries no "
            f"bindable hole of `{var}` — every instance shares one accessible name, and no "
            f"consumer can discriminate them",
            ref=item["node"],
            suggestion=f"interpolate a per-instance datum (e.g. `{{{var}.name}}`) or give the "
                       f"control an instance-specific aria-label in the app",
            **_at(item["node"])))

    for item in loc_mod.unproven_unique_names(data):
        f.append(Finding(
            "warn", "unproven-unique-name",
            f"{item['node']}: instances are told apart only by display value(s) "
            f"({', '.join(item['binds'])}), which nothing guarantees distinct — two instances "
            f"sharing one are ambiguous at runtime with no warning anywhere",
            ref=item["node"],
            suggestion="state the distinct key as `- unique-by: `<var>.<key>``, or interpolate a "
                       "guaranteed-distinct datum into the name",
            **_at(item["node"])))

    for item in loc_mod.malformed_templates(data):
        f.append(Finding(
            "error", "malformed-template",
            f"{item['node']}: `name:` {item['template']!r} has an unbalanced brace — the one "
            f"template error classification cannot absorb",
            ref=item["node"],
            suggestion="balance the `{…}` holes; anything the path grammar rejects is kept "
                       "verbatim as opaque, so no hole needs rewording",
            **_at(item["node"])))

    for item in loc_mod.invalid_variants(data):
        f.append(Finding(
            "warn", "malformed-variants",
            f"{item['node']}: `variants: {item['value']}` does not parse as "
            f"`<var>.<path> = tok | tok | …` — the axis would be silently dropped and QA would "
            f"stop owing one instance per variant",
            ref=item["node"],
            suggestion="- variants: `<var>.<path> = <literal> | <literal>` — all inside one "
                       "backtick span",
            **_at(item["node"])))

    for item in loc_mod.templates_outside_repeat(data):
        f.append(Finding(
            "warn", "template-outside-repeat",
            f"{item['node']}: `name:` {item['template']!r} carries `{{…}}` holes but the node "
            f"repeats over nothing — every hole is opaque, so every consumer matches the name "
            f"as a wildcard instead of the value it was written to pin",
            ref=item["node"],
            suggestion="declare the repeat (`- one-per: `<var>``, plus `unique-by:` for the "
                       "distinct key) if the control renders per member of a collection; "
                       "otherwise write the literal rendered name",
            **_at(item["node"])))


def _check_placement(node, rel: str, f: list[Finding]) -> None:
    """A structural component says where it sits, and says it in a form QA can check."""
    values = _bullet_values(node.meta.get("placement", ""))
    role = str(node.meta.get("role", "")).strip()
    if not values:
        if role in placement_mod.PLACED_ROLES:
            f.append(Finding(
                "error", "missing-placement",
                f"{node.id}: role={role} carries the page but no `placement:` says where it "
                f"sits — a role+name assertion passes on a component crushed into a sliver",
                path=rel, line=node.line, ref=refs_mod.bullet_ref(node.id, "placement"),
                suggestion="- placement: width 60-100%, x 0-20%   (read off the running UI)"))
        return
    for index, value in enumerate(values, 1):
        parsed = placement_mod.parse_placement(value)
        if isinstance(parsed, str):
            f.append(Finding(
                "error", "malformed-placement",
                f"{node.id}: `placement:{index}` ({value}) is not a placement — {parsed}",
                path=rel, line=node.line,
                ref=refs_mod.bullet_ref(node.id, "placement", index),
                suggestion="- placement: width 60-100%, x 0-20%"))


def _check_unaddressable_selector(node, rel: str, f: list[Finding]) -> None:
    """A component's `selector:` names a form nothing in this tree can resolve."""
    values = _bullet_values(node.meta.get("selector", ""))
    for index, raw in enumerate(values, 1):
        value = raw.strip().strip("`").strip()
        if value and not placement_mod.is_addressable(value):
            f.append(Finding(
                "error", "unaddressable-selector",
                f"{node.id}: `selector:{index}` ({value}) is a form the render scan never "
                f"mints and no recognized `scheme=value` address either — the census can "
                f"only ever read this component as missing",
                path=rel, line=node.line,
                ref=refs_mod.bullet_ref(node.id, "selector", index),
                suggestion="address by id, class, or role; on a surface with no web DOM, "
                           "by the address its own driver resolves — `testID=<value>`, the "
                           "prop the source writes; if the distinction is a piece of "
                           "state, record it on `states:` instead — a state distinguishable "
                           "by rendered text still gets `verify: visible(locator=\"#anchor\", "
                           "text=\"...\")`; one that isn't has no check in this book's "
                           "vocabulary yet and stays documented but unverified"))


def _check_arranged_acts(graph: Graph, node: UINode, rel: str, f: list[Finding]) -> None:
    """Every `arrange:` bullet is an act this repo can perform, on a control this book declares."""
    for key in registry.performed_keys(node.type):
        for index, value in enumerate(_bullet_values(node.meta.get(key, "")), 1):
            parsed = acts.parse_act(value)
            if isinstance(parsed, checks.Refusal):
                f.append(Finding(
                    "error", "unparsed-act",
                    f"{node.id}: `{key}:{index}` ({value}) {parsed.message}",
                    path=rel, line=node.line,
                    ref=refs_mod.bullet_ref(node.id, key, index),
                    suggestion=parsed.bullet(key)))
                continue
            for param in acts.ACT_BY_NAME[parsed.name].params:
                if not param.locator or param.name not in parsed.args:
                    continue
                named = parsed.args[param.name]
                target = loc_mod.locator_target(graph, named, node.path)
                if loc_mod.located_node(graph, named, node.path) is not None:
                    continue
                why = ("names no component this book declares" if target
                       else "is a raw selector, not a reference into the book")
                f.append(Finding(
                    "error", "undeclared-act-locator",
                    f"{node.id}: `{key}:{index}` performs `{parsed.name}` on `{named}`, "
                    f"which {why} — name the `component` or `interaction` that declares it, "
                    f"by its anchor, so the selector lives in one place and renaming the "
                    f"element shows up here",
                    path=rel, line=node.line,
                    ref=refs_mod.bullet_ref(node.id, key, index),
                    suggestion=f'- {key}: {parsed.name}({param.name}="#<component-anchor>")'))


def _check_ui(graph: Graph, f: list[Finding],
              resolver: links_mod.LinkResolver | None = None,
              checkouts: dict[str, Path] | None = None) -> None:
    """The UI-profile per-file and per-node checks."""
    _check_availability_states(graph, f)
    if resolver is None:
        resolver = links_mod.LinkResolver(graph)
    froot = graph.doc_roots.get("features")
    if froot is not None and froot.is_dir():
        for path in sorted(froot.rglob("*.md")):
            if path.is_file() and path.name not in registry.RESERVED_FILES:
                _check_ui_file(graph, path, f)
    _check_code_grounding(graph, f, checkouts)

    by_id = {n.id: n for n in graph.ui_nodes}
    for node in graph.ui_nodes:
        uitype = registry.ui_type(node.type)
        if uitype is None:
            continue
        rel = node.path.relative_to(graph.root).as_posix()
        extends_ok = False
        if node.type in ("interaction", "invocation"):
            targets = _resolved_targets(node, "extends", resolver)
            extends_ok = any(by_id[t].type == node.type for t in targets if t in by_id)
            for target_id in sorted(targets):
                target = by_id.get(target_id)
                if target is not None and target.type != node.type:
                    f.append(Finding(
                        "error", "extends-type-mismatch",
                        f"{node.id}: `extends:` names {target_id} ({target.type}), not "
                        f"another {node.type} — an arm can only extend its own node type",
                        path=rel, line=node.line, ref=refs_mod.bullet_ref(node.id, "extends"),
                        suggestion=f"- extends: [{node.type} base case](#anchor)"))
            arrange = registry.arrange_keys(node.type)
            if extends_ok and arrange and not _arranges_anything(node):
                for target_id in sorted(targets):
                    target = by_id.get(target_id)
                    if target is None or target.type != node.type:
                        continue
                    if not _arranges_anything(target):
                        continue
                    f.append(Finding(
                        "error", "unarranged-extending-arm",
                        f"{node.id}: `extends:` {target_id}, which arranges its own "
                        f"precondition, and this arm arranges nothing — arrangements are not "
                        f"inherited, because an arrangement exists to make this arm's `when:` "
                        f"true and the base's makes the base's true",
                        path=rel, line=node.line,
                        ref=refs_mod.bullet_ref(node.id, "extends"),
                        suggestion=(
                            "- arrange: an act that puts this arm's own `when:` state on the "
                            "surface, or `- fixture:` when the state lives beside it"
                            if "arrange" in arrange else
                            "- fixture: the state this arm's own `when:` describes")))
                    break

            verify_calls = [
                c for c in (checks.parse_check(v)
                            for v in _bullet_values(node.meta.get("verify", "")))
                if isinstance(c, checks.CheckCall)
            ]
            seen_conflicts: set[tuple[str, str]] = set()
            for i, a in enumerate(verify_calls):
                for b in verify_calls[i + 1:]:
                    if not _alternation_conflict(a, b):
                        continue
                    first, second = sorted((a.text(), b.text()))
                    pair = (first, second)
                    if pair in seen_conflicts:
                        continue
                    seen_conflicts.add(pair)
                    f.append(Finding(
                        "warn", "unspelled-alternation",
                        f"{node.id}: `verify: {a.text()}` and `verify: {b.text()}` are the "
                        f"same check on the same subject with two different expected values — "
                        f"one node cannot be both at once. Split into a base case and an arm "
                        f"that `extends:` it, each keeping the `verify:` that is true of it",
                        path=rel, line=node.line, ref=refs_mod.bullet_ref(node.id, "verify"),
                        suggestion="- extends: [base case](#anchor)"))
        for bk in uitype.bullet_keys:
            if bk.required and bk.key not in node.meta:
                if extends_ok and bk.key in {"on", "trigger", "role", "name", "keyboard"}:
                    continue
                f.append(Finding("error", "missing-required-bullet",
                                 f"{node.id}: {node.type} missing required `{bk.key}:`",
                                 path=rel, line=node.line, ref=bk.key,
                                 suggestion=f"- {bk.key}:", fixable=True))

        if node.type == "component":
            _check_placement(node, rel, f)
            _check_unaddressable_selector(node, rel, f)
            for key in loc_mod.malformed_identity({"bullets": node.meta}):
                f.append(Finding(
                    "error", "duplicate-bullet",
                    f"{node.id}: `{key}:` is stated {len(node.meta[key])} times — a component "
                    f"has one {key}, so the node cannot say which it is; keep the bullet the "
                    f"source supports and drop the rest",
                    path=rel, line=node.line, ref=refs_mod.bullet_ref(node.id, key),
                    suggestion=f"- {key}: <the one value the source renders>"))

        for key in registry.unknown_bullet_keys(node.type, node.meta):
            minted = ", ".join(f"`{k}:`" for k in registry.NORMATIVE_KEYS_BY_TYPE.get(
                node.type, ()))
            f.append(Finding(
                "warn", "unknown-bullet",
                f"{node.id}: `{key}:` is not a bullet {node.type} declares, so here it is "
                f"inert — nothing orders it, grades it, grounds it or binds a `verify:` "
                f"to it; move the claim under a key {node.type} mints from "
                f"({minted or 'none — this type states no claims'}) or into prose",
                path=rel, line=node.line, ref=refs_mod.bullet_ref(node.id, key)))

        normative = 0
        for key in registry.normative_keys(node.type):
            for index, value in enumerate(_bullet_values(node.meta.get(key, "")), 1):
                if not registry.states_no_claim(key, value):
                    normative += 1
                length = len(_prose(value))
                if length > MAX_NORMATIVE_PROSE:
                    f.append(Finding(
                        "error", "overlong-normative-bullet",
                        f"{node.id}: `{key}:{index}` runs {length} characters of prose — "
                        f"too much to prove as one claim; split it into one bullet per "
                        f"provable claim",
                        path=rel, line=node.line,
                        ref=refs_mod.bullet_ref(node.id, key, index)))
                    continue
                if key in RELATION_KEYS and relation_subject(value)[0] is None:
                    f.append(Finding(
                        "warn", "relation-without-subject",
                        f"{node.id}: `{key}:{index}` ({_prose(value)[:60]}) names no "
                        f"subject, so no other node can be found to share it; lead with the "
                        f"record, event or lock it is about, as one lowercase slug before a "
                        f"spaced em dash — `- {key}: payout-record — {_prose(value)[:40]}…`",
                        path=rel, line=node.line,
                        ref=refs_mod.bullet_ref(node.id, key, index)))
                reasons = _split_signals(value)
                if reasons:
                    f.append(Finding(
                        "warn", "compound-normative-bullet",
                        f"{node.id}: `{key}:{index}` ({_prose(value)[:60]}) states more "
                        f"than one observation — {'; '.join(reasons)}. One bullet is one "
                        f"obligation and is proved by one scenario, so the clauses that share "
                        f"it are covered by whichever one the planner read; split it into one "
                        f"bullet per observation",
                        path=rel, line=node.line,
                        ref=refs_mod.bullet_ref(node.id, key, index)))

        instrumented = (frozenset(registry.normative_keys(node.type))
                        | frozenset(registry.RELATION_KEYS)
                        | frozenset(registry.check_keys(node.type))
                        | frozenset(registry.arrange_keys(node.type))
                        | _OBSERVATION_KEYS)
        instrumented |= registry.declared_keys(node.type)
        minted = ", ".join(f"`{k}:`" for k in registry.normative_keys(node.type))
        for key, value, _line in node.bullet_order:
            if key in instrumented:
                continue
            signal = next((s for v in _bullet_values(value) if (s := _sounds_normative(v))), "")
            if not signal:
                continue
            f.append(Finding(
                "warn", "unminted-claim",
                f"{node.id}: `{key}:` reads like a claim ({signal}) but {node.type} mints no "
                f"obligation from it — nothing will ask a QA plan to prove it; move it under "
                f"a normative key ({minted}) or into prose",
                path=rel, line=node.line, ref=refs_mod.bullet_ref(node.id, key)))
            break

        check_keys = registry.check_keys(node.type)
        declared = 0
        for key in check_keys:
            for index, value in enumerate(_bullet_values(node.meta.get(key, "")), 1):
                declared += 1
                parsed = checks.parse_check(value)
                if isinstance(parsed, checks.Refusal):
                    node_keys = registry.declared_keys(node.type)
                    said: dict[str, Any] = dict(
                        message=f"{node.id}: `{key}:{index}` ({value}) {parsed.message}",
                        path=rel, line=node.line,
                        ref=refs_mod.bullet_ref(node.id, key, index),
                        suggestion=parsed.bullet(key, node_keys))
                    if parsed.kind == "misfiled-test-ref":
                        f.append(Finding("error", "misfiled-test-ref", **said,
                                         fixable=(key == "verify"
                                                  and "tests" in node_keys
                                                  and checks.relocatable_to_tests(value))))
                    else:
                        f.append(Finding("error", "unparsed-check", **said))
                    continue
                for param in checks.CHECK_BY_NAME[parsed.name].params:
                    if not param.locator or param.name not in parsed.args:
                        continue
                    named = str(parsed.args[param.name])
                    target = loc_mod.locator_target(graph, named, node.path)
                    if loc_mod.located_node(graph, named, node.path) is not None:
                        continue
                    why = ("names no component this book declares" if target
                           else "is a raw selector, not a reference into the book")
                    f.append(Finding(
                        "error", "undeclared-check-locator",
                        f"{node.id}: `{key}:{index}` points `{param.name}=` at "
                        f"`{named}`, which {why} — name the `component` or `interaction` "
                        f"that declares it, by its anchor, so the selector lives in one "
                        f"place and renaming the element shows up here",
                        path=rel, line=node.line,
                        ref=refs_mod.bullet_ref(node.id, key, index),
                        suggestion=f'- {key}: {parsed.name}({param.name}="#<component-anchor>")'))

        _check_arranged_acts(graph, node, rel, f)

        verify_key = check_keys[0] if check_keys else "verify"
        contract_checks, claim_checks = registry.attributed_checks(
            node.type, node.bullet_order, node.combiners)

        claim_universe = registry.normative_claims(node.type, node.bullet_order)
        overcovered = sorted(
            pos for pos, values in claim_checks.items() if len(values) >= 2)
        undercovered = sorted(
            pos for pos in claim_universe if not claim_checks.get(pos))
        if overcovered and undercovered:
            heavy_key, heavy_index = overcovered[0]
            light_key, light_index = undercovered[0]
            f.append(Finding(
                "error", "uneven-claim-coverage",
                f"{node.id}: `{heavy_key}:{heavy_index}` carries "
                f"{len(claim_checks[(heavy_key, heavy_index)])} `{verify_key}:` checks and "
                f"`{light_key}:{light_index}` on the same node carries none — a check bound to "
                f"the nearest bullet above it rather than the claim it names lands doubled on "
                f"one and missing from its sibling; rebind each check to the claim it observes",
                path=rel, line=node.line,
                ref=refs_mod.bullet_ref(node.id, heavy_key, heavy_index),
                suggestion=f"- {light_key}:{light_index} …\n- {verify_key}: …"))

        donor_key = _STATUS_DONOR_KEY.get(node.type)
        if donor_key:
            _, indexed_claim_checks = registry.attributed_check_bullets(
                node.type, node.bullet_order, node.combiners)
            by_verify_index: dict[int, list[tuple[tuple[str, int], str]]] = {}
            for claim_pos, values in indexed_claim_checks.items():
                for verify_index, value in values:
                    by_verify_index.setdefault(verify_index, []).append((claim_pos, value))
            donor_bullets = list(enumerate(_bullet_values(node.meta.get(donor_key, "")), 1))
            for verify_index in sorted(by_verify_index):
                entries = by_verify_index[verify_index]
                value = entries[0][1]
                parsed = checks.parse_check(value)
                if isinstance(parsed, checks.Refusal) or parsed.name not in _STATUS_LIKE_CHECKS:
                    continue
                code = parsed.args.get("code")
                if not isinstance(code, int) or isinstance(code, bool):
                    continue
                if any(_code_in_text(code, claim_universe.get(claim_pos, ""))
                       for claim_pos, _ in entries):
                    continue
                donor = next(
                    (db for db in donor_bullets if _code_in_text(code, db[1])), None)
                if donor is None:
                    continue
                donor_index, donor_value = donor
                claim_names = ", ".join(
                    f"{claim_key}:{claim_index}"
                    for claim_key, claim_index in sorted({cp for cp, _ in entries}))
                f.append(Finding(
                    "error", "misbound-status-check",
                    f"{node.id}: `{verify_key}:{verify_index}` ({value}) names {code}, which is "
                    f"absent from `{claim_names}` — the claim(s) document order bound "
                    f"it to — but present, verbatim, on this node's own `{donor_key}:"
                    f"{donor_index}` ({_prose(donor_value)[:60]}); the check was written after "
                    f"every claim and landed on the last one above it rather than the bullet "
                    f"naming its own code",
                    path=rel, line=node.line,
                    ref=refs_mod.bullet_ref(node.id, verify_key, verify_index),
                    fixable=True,
                    suggestion=(f"- {donor_key}:{donor_index} …\n"
                                f"- {verify_key}: {value}")))

        if node.type == "command":
            _, claim_acts = registry.attributed_acts(
                node.type, node.bullet_order, node.combiners)
            for claim_key, claim_index in sorted(claim_checks):
                if claim_acts.get((claim_key, claim_index)):
                    continue
                f.append(Finding(
                    "error", "unbound-command-claim",
                    f"{node.id}: `{claim_key}:{claim_index}` carries a `{verify_key}:` and no "
                    f"`run:` for it to bind to — `usage:`/`flags:`/`args:` are a prose "
                    f"synopsis of every way to call this command, not the one concrete "
                    f"invocation this claim was checked against, so nothing compiles this "
                    f"claim to a scenario; add a `run:` with the literal argv this claim "
                    f"checks",
                    path=rel, line=node.line,
                    ref=refs_mod.bullet_ref(node.id, claim_key, claim_index),
                    suggestion='- run: invoke(argv=["<binary>", "<arg>", …])'))

        undetermined = registry.undetermined_claims(
            node.type, node.bullet_order, node.combiners)
        for position, group in undetermined.items():
            key, index = group[0]
            f.append(Finding(
                "error", "unstated-claim-combiner",
                f"{node.id}: `{key}:` nests {len(group)} claims with a `{verify_key}:` "
                f"written under them, and does not say whether they are parts of one "
                f"effect or alternative outcomes — so nothing can tell a check that "
                f"observes all of them from one that refutes all but one",
                path=rel, line=node.bullet_lines.get(position, node.line),
                ref=refs_mod.bullet_ref(node.id, key, index),
                suggestion=f"- {key}: all   # or: branches"))
        _, fanned = registry.attributed_checks(node.type, node.bullet_order, {})
        for position, group in registry.claim_groups(node.type, node.bullet_order).items():
            if node.combiners.get(position, "") != "branches" or len(group) < 2:
                continue
            if not any(fanned.get(claim) for claim in group):
                continue
            line = node.bullet_lines.get(position, node.line)
            for claim_key, claim_index in group:
                if claim_checks.get((claim_key, claim_index)):
                    continue
                f.append(Finding(
                    "warn", "unobserved-branch",
                    f"{node.id}: `{claim_key}:{claim_index}` is one branch of a list declared "
                    f"`branches`, and nothing observes it — the `{verify_key}:` under the list "
                    f"was written for a sibling outcome and would refute this one. Split the "
                    f"branches into sibling bullets, each with the check that is true of it",
                    path=rel, line=line,
                    ref=refs_mod.bullet_ref(node.id, claim_key, claim_index),
                    suggestion=f"- {claim_key}: <this outcome>\n- {verify_key}: …"))

        def _calls(values: list[str]) -> list[checks.CheckCall]:
            return [c for c in (checks.parse_check(v) for v in values)
                    if isinstance(c, checks.CheckCall)]

        contract_calls = _calls(contract_checks)
        calls_by_claim = {ck: _calls(values) for ck, values in claim_checks.items()}

        claims = [(refs_mod.bullet_ref(node.id, "contract"), contract_calls)]
        claims += [(refs_mod.bullet_ref(node.id, key, index), calls_by_claim[(key, index)])
                   for (key, index) in claim_checks]
        for claim, calls in claims:
            stamps = [_rubber_stamp(call) for call in calls]
            if calls and all(stamps):
                f.append(Finding(
                    "error", "weak-check",
                    f"{claim}: every check declared for this claim passes on the defect it is "
                    f"meant to catch — {stamps[0]}",
                    path=rel, line=node.line, ref=claim,
                    suggestion=f'- {verify_key}: json_path(path="…", equals="…")'))
            repr_spelled = [c for c in calls if c.name == "json_path"
                             and _matches_repr_spelled(str(c.args.get("matches", "")))]
            if repr_spelled:
                call = repr_spelled[0]
                f.append(Finding(
                    "error", "matches-repr-spelling",
                    f"{claim}: `{call.text()}` spells its pattern against Python's `repr` — "
                    f"the book documents a JSON document, so `None`/`True`/`False` never "
                    f"appear in the value this pattern is matched against; write `null`/"
                    f"`true`/`false`",
                    path=rel, line=node.line, ref=claim,
                    suggestion='- ' + verify_key + ': json_path(path="…", matches="^null$")'))

        claim_values = registry.normative_claims(node.type, node.bullet_order)
        for (key, index), calls in calls_by_claim.items():
            if key in NON_ACTION_KEYS:
                continue
            if not calls or any(c.name in LIFECYCLE_CHECKS for c in calls + contract_calls):
                continue
            verb = _states_a_lifecycle_claim(claim_values.get((key, index), ""))
            if not verb:
                continue
            claim_text = claim_values.get((key, index), "")
            f.append(Finding(
                "warn", "unstated-precondition",
                f"{node.id}: `{key}:{index}` ({_prose(claim_text).strip()}) states a lifecycle "
                f"change ('{verb}'), and the checks read "
                f"only the state afterwards — which is the same state a no-op leaves when "
                f"the subject was already there. Declare the change as a change, so the "
                f"before-read is part of the observation rather than an assumption",
                path=rel, line=node.line,
                ref=refs_mod.bullet_ref(node.id, key, index),
                suggestion=f'- {verify_key}: created(subject="…")   # or: removed'))
            break

        if check_keys and normative and not declared and node.type != "field":
            f.append(Finding(
                "warn", "undeclared-obligation",
                f"{node.id}: {normative} normative bullet{'s' if normative > 1 else ''} and no "
                f"`{check_keys[0]}:` — nothing says what observing them looks like, so a QA plan "
                f"claiming them can assert anything and still pass; declare a check per "
                f"observation (`ostler checks` lists the vocabulary and its signatures)",
                path=rel, line=node.line,
                ref=refs_mod.bullet_ref(node.id, check_keys[0]),
                suggestion=f'- {check_keys[0]}: http_status(code=409, title="Conflict")'
                           f'   # or: {", ".join(s.name for s in checks.CHECKS)}'))

    relation_hrefs: dict[tuple[str, str], str] = {}
    for node in graph.ui_nodes:
        for key in registry.RELATION_KEYS:
            for value in _bullet_values(node.meta.get(key, "")):
                for _text, href in markdown.extract_refs(value).links:
                    relation_hrefs[(str(node.path), href)] = key

    if froot is not None and froot.is_dir():
        for path in sorted(froot.rglob("*.md")):
            if not path.is_file() or path.name in registry.RESERVED_FILES:
                continue
            rel = path.relative_to(graph.root).as_posix()
            try:
                links = model.read_links(path)
            except OSError:
                continue
            seen: set = set()
            for _text, href, line in links:
                if not links_mod.is_doc_link(href) or href in seen:
                    continue
                seen.add(href)
                target = resolver.resolve(path, href)
                if target is None or target.resolved:
                    continue
                ref = f"{rel}:{line}:{href}"
                rkey = relation_hrefs.get((str(path), href))
                if rkey:
                    f.append(Finding("error", "unresolved-relation",
                                     f"{rel}: `{rkey}:` target '{href}' does not resolve",
                                     path=rel, line=line, ref=ref, fixable=True))
                elif not target.file_exists:
                    f.append(Finding("error", "dangling-link",
                                     f"{rel}: link '{href}' target file does not exist",
                                     path=rel, line=line, ref=ref, fixable=True))
                else:
                    f.append(Finding("error", "missing-anchor",
                                     f"{rel}: link '{href}' — file exists but `#{target.anchor}` "
                                     f"heading not found", path=rel, line=line, ref=ref,
                                     fixable=True))


def _check_sensitivity(graph: Graph, f: list[Finding]) -> None:
    """A claim's checks must be able to go red, not just able to run."""
    for row in sensitivity.report(graph):
        if row.status == "unwitnessed":
            notes = "; ".join(f"`{t.call}` — {t.note}" for t in row.trials if not t.witnessed)
            f.append(Finding(
                "warn", "unwitnessed-check",
                f"{row.claim}: `ostler qa sensitivity` could not build a witness observation "
                f"any check on this claim accepts, so no perturbation was tried — {notes}",
                path=row.path, line=row.line, ref=row.claim,
                suggestion="leave the check as it is unless it is wrong: this reports the "
                           "reach of the sensitivity harness, not a defect in the check"))
            continue
        if row.status != "insensitive":
            continue
        reasons = "; ".join(f"`{t.call}` — survived: {', '.join(t.survived)}"
                            for t in row.trials if t.witnessed)
        f.append(Finding(
            "error", "insensitive-check",
            f"{row.claim}: every check declared for this claim stayed green through every "
            f"perturbation tried against it — {reasons}",
            path=row.path, line=row.line, ref=row.claim,
            suggestion="assert a value the defect would actually change: name the route, the "
                       "field's content, or the title the claim turns on"))


def cmd_doctor(graph: Graph, *, epic: str | None = None,
               check_schema: bool = True) -> QaOutcome:
    """`ostler doctor` as an outcome: `ok` = no error-severity finding, `data` = the report."""
    report = run(graph, epic_filter=epic, check_schema=check_schema)
    message = f"{report.errors} error(s), {report.warnings} warning(s)"
    return QaOutcome(ok=not report.errors, message=message, data=report.as_dict())
