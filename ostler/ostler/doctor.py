"""`ostler doctor`: deterministic referential-integrity checks over the planning graph."""

from __future__ import annotations

import difflib
import functools
import json
from dataclasses import dataclass, field
from pathlib import Path

from ostler import adr as adr_mod
from ostler import dynamic_registry
from ostler import ids as ids_mod
from ostler import milestones as milestones_mod
from ostler import path as path_mod
from ostler import register as register_mod
from ostler import registry, schemas, select
from ostler.finding import Finding
from ostler.model import Epic, Graph, Story, load_config, read_doc
from ostler.pages import in_hidden_folder
from ostler.path import specs_root_in
from ostler.qa import fixtures as fixtures_mod
from ostler.qa.outcome import QaOutcome


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


def run(graph: Graph, epic_filter: str | None = None, check_schema: bool = True) -> Report:
    report = Report(org=graph.org_name, profile=graph.profile)
    f = report.findings

    _check_removed_doc_roots(graph, f)
    _check_register_records(graph, f)
    _check_decisions(graph, f)
    milestones_mod.check_milestones(graph, f)
    if check_schema:
        _check_conformance(graph, f)

    if graph.profile != "full":
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

    return report


def _check_removed_doc_roots(graph: Graph, findings: list[Finding]) -> None:
    """The `docRoots` key is gone, so a config that still carries it is flagged and not read."""
    if "docRoots" in (load_config(graph.root).model_extra or {}):
        findings.append(Finding(
            "error", "removed-doc-roots",
            "`docRoots` was removed from the organization config and is no longer read: "
            "every kind lives at its built-in path under `docs/`, and specs live in the "
            "artifacts dir, so delete the key",
            suggestion="delete the `docRoots` key from the organization config"))


def _check_register_records(graph: Graph, findings: list[Finding]) -> None:
    """A `record.md` on the Register's shelf that does not parse is left out of the listing, so it is named here."""
    for path in register_mod.records(graph).unreadable:
        findings.append(Finding(
            "error", "register-record-unreadable",
            f"{path}: not a readable record, so the listing skips it — fix its frontmatter "
            f"(id, repo, area, pattern, filed_by, summary) or delete the folder",
            path=str(path), line=1))


def _check_decisions(graph: Graph, findings: list[Finding]) -> None:
    """A decision and its evidence name each other: every evidence id resolves to a record, and that record's `decision` names the decision."""
    shelved = set(ids_mod.shelf_ids(graph))
    read = adr_mod.decisions(graph)
    bound = {r.id: r.decision for r in register_mod.records(graph).records}
    decided = {d.id for d in read.decisions}
    for decision in read.decisions:
        where = str(path_mod.adr_root(graph) / decision.id / adr_mod.ADR_FILE)
        for record_id in decision.evidence:
            if record_id not in shelved:
                findings.append(Finding(
                    "error", "decision-evidence-unresolved",
                    f"decision '{decision.id}' cites evidence '{record_id}', which resolves to no record "
                    f"on the shelf",
                    suggestion="restore the record, or remove the id from the decision's `evidence`",
                    path=where, line=1))
            elif record_id in bound and bound[record_id] != decision.id:
                findings.append(Finding(
                    "error", "decision-back-link-missing",
                    f"decision '{decision.id}' lists record '{record_id}', whose `decision` is "
                    f"'{bound[record_id] or 'empty'}'",
                    suggestion=f"set `decision: {decision.id}` on the record, or remove it from the evidence",
                    path=where, line=1))
    for record_id, named in sorted(bound.items()):
        if named and named not in decided:
            findings.append(Finding(
                "error", "decision-back-link-missing",
                f"record '{record_id}' names decision '{named}', and no decision file has that id",
                suggestion="restore the decision file, or clear the record's `decision`",
                ref=record_id))


def _check_story_identity(graph: Graph, findings: list[Finding]) -> None:
    """Every accepted story spelling identifies one story, and its two id copies agree."""
    owners: dict[str, list[tuple[Epic, Story]]] = {}
    for epic in graph.epics:
        for story in epic.stories:
            for alias in story.aliases:
                owners.setdefault(alias, []).append((epic, story))
            if story.eid and story.file_eid and story.eid != story.file_eid:
                path = (_rel_posix(story.story_md, graph.root)
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
                rel = _rel_posix(story.story_md, graph.root)
                f.append(Finding(
                    "error", "story-status-mismatch",
                    f"story '{story.slug}' frontmatter status '{story.status}' differs from "
                    f"its `## Implementation Status` value '{story.body_status}'",
                    epic.name, story.slug, path=rel, line=1))
            if story.conflict:
                rel = _rel_posix(story.story_md, graph.root)
                f.append(Finding(
                    "error", "story-conflict",
                    f"story '{story.slug}' has acceptance criteria in conflict — "
                    f"{story.conflict}",
                    epic.name, story.slug, path=rel, line=1,
                    suggestion="rewrite the criteria so one intent holds, then "
                               f"`ostler conflict {story.eid or story.slug} --clear`"))
            if story.unwritten_sections:
                rel = _rel_posix(story.story_md, graph.root)
                f.append(Finding("error", "unwritten-story",
                                 f"story '{story.slug}' is still a bare scaffold — "
                                 f"{', '.join(story.unwritten_detail)}",
                                 epic.name, story.slug, path=rel, line=1))
            if story.misordered_sections:
                rel = _rel_posix(story.story_md, graph.root)
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
    known = set(specs)

    for epic in graph.epics:
        for story in epic.stories:
            if story.story_md is None:
                continue
            rel = _rel_posix(story.story_md, graph.root)
            for stray in story.fixture_strays:
                f.append(Finding(
                    "error", "story-fixture-stray",
                    f"story '{story.slug}' has a `## {registry.STORY_FIXTURES_HEADING}` bullet "
                    f"that names no fixture: {stray!r} — write "
                    f"`- {registry.STORY_FIXTURES_LABEL}: <name>`, or "
                    f"`{registry.STORY_FIXTURES_NONE}` when the story arranges nothing",
                    epic.name, story.slug, path=rel, line=1))
            plan = spec_root / story.eid / "qa_plan.py" if story.eid else None
            plan_rel = _rel_posix(plan, graph.root) if plan else "qa_plan.py"
            names = fixtures_mod.referenced(plan) if plan and plan.is_file() else None
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
        return (f"`{plan_rel}` asks for '{name}', so it is an arrangement nobody declared; add a "
                f"`qa: {{fixtures:}}` entry in agents.yml")
    return (f"`{plan_rel}` never asks for '{name}', so nothing arranges it and nothing wants it "
            f"— delete the bullet, or write `{registry.STORY_FIXTURES_NONE}` if the story "
            f"arranges nothing")


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
        rel = _rel_posix(milestone.path, graph.root)
        for dep in milestone.depends_on:
            if dep not in known_milestones:
                f.append(Finding(
                    "error", "dangling-milestone-dependency",
                    f"milestone '{milestone.name}' depends on unknown milestone '{dep}'",
                    ref=dep, path=rel, line=1))
        for epic_name in milestone.epics:
            listed = _epic_by_ref(graph, epic_name)
            if listed is None:
                f.append(Finding(
                    "error", "dangling-milestone-epic",
                    f"milestone '{milestone.name}' lists unknown epic '{epic_name}'",
                    ref=epic_name, path=rel, line=1))
            elif listed.followups:
                f.append(Finding(
                    "error", "followups-epic-in-milestone",
                    f"milestone '{milestone.name}' lists '{epic_name}', an epic of filed follow-ups "
                    "that no milestone owns",
                    epic=listed.name, ref=epic_name, path=rel, line=1))

    for epic in graph.epics:
        refs = owners.get(_epic_ref(epic.name), [])
        if not refs and not epic.followups:
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
    """Every document's frontmatter declares a type, and each known type meets its schema."""
    schema_by_base = {t.name: t.schema for t in registry.REGISTRY}
    etypes = registry.REGISTRY + dynamic_registry.as_entity_types(graph.template_kinds)
    seen: set = set()
    for etype in etypes:
        folder = graph.doc_roots.get(etype.doc_root)
        if folder is None or not folder.is_dir():
            continue
        for path in sorted(folder.glob(etype.location)):
            if not path.is_file() or path.name in registry.RESERVED_FILES or path in seen or in_hidden_folder(path, folder):
                continue
            seen.add(path)
            rel = _rel_posix(path, graph.root)
            try:
                fm = dict(read_doc(path).frontmatter or {})
            except OSError as exc:
                f.append(Finding("error", "unreadable", f"{rel}: {exc}", path=rel))
                continue
            declared = registry.type_of(fm)
            if not declared:
                f.append(Finding("error", "missing-type",
                                 f"{rel}: document has no non-empty `type` in frontmatter",
                                 path=rel, line=1))
                continue
            base = registry.base_type(declared)
            schema = schema_by_base.get(base) if base else None
            if schema:
                for msg in schemas.validate(fm, schema):
                    f.append(Finding("warn", "schema", f"{rel}: {msg}", path=rel))


@functools.lru_cache(maxsize=65536)
def _rel_posix(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def cmd_doctor(graph: Graph, *, epic: str | None = None,
               check_schema: bool = True) -> QaOutcome:
    """`ostler doctor` as an outcome: `ok` = no error-severity finding, `data` = the report."""
    report = run(graph, epic_filter=epic, check_schema=check_schema)
    message = f"{report.errors} error(s), {report.warnings} warning(s)"
    return QaOutcome(ok=not report.errors, message=message, data=report.as_dict())
