"""`ostler doctor` — deterministic referential-integrity checks over the organization graph.

Computes (never asserts) per-epic seed/story counts and flags cross-epic references, orphan seeds,
missing story files, and dangling dependencies.
"""

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
    severity: str   # "error" | "warn"
    code: str
    message: str
    epic: str = ""
    ref: str = ""              # offending token
    path: str = ""             # repo-relative file
    line: int = 0              # 1-based, file-absolute
    suggestion: str = ""       # expected form / nearest match
    fixable: bool = False      # `ostler fmt`/`scaffold`/relink can apply the remedy
    #: The node id this finding is about, when the finding is scoped to exactly one node.
    #: Every finding already carries the id as a `f"{node.id}: ..."` message prefix by
    #: convention; this field exists so a consumer that needs to group findings by node
    #: (okf-builder's stale-citation regrounding, the RESTAMP doctor gate) does not have to
    #: parse prose to recover it. Left empty for a finding not about a single node.
    node: str = ""
    #: The *other* book locations this one finding is also about, `<path>#<node-id>` each.
    #: Empty for the ordinary finding, which is about the one place `path`/`line` name.
    #:
    #: A group finding — a `same-as:` family disagreeing about one key, a surface whose
    #: runbooks disagree about `driver:` — has a remedy that is only complete when every member
    #: is edited, and `path` can name just one of them. Carrying the membership as a field
    #: rather than only as prose in `message` is what lets a consumer address the group:
    #: okf-builder's repair item reads this to put every member in scope, and without it the
    #: only membership list was a sentence it would have had to match.
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
    """*report* keeping only the findings about *paths* (repo-relative files or folders).

    The run is not scoped, only the answer: most checks resolve links and symbols across the
    whole book, so a finding on one file is known only after every file is read. What a
    scope buys is a report the size of the question. The caller it exists for is an agent
    that has just repaired one file and must see whether its findings cleared: over a real
    book the unscoped report is megabytes, so it went unread and the turn closed on a guess
    instead — a grep for the finding's shape that missed every bullet spanning two lines.

    A group finding stays when any of its `related` locations is in scope, because editing
    one member is exactly the edit that has to see the group.
    """
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
    """The unified diff between two runs' reports, empty when they agree.

    This is the correctness half of the index's acceptance gate (Q13): the cached path and
    the uncached one are the same computation, so their reports are compared *whole*
    rather than by error count. An equal count over different findings is exactly the
    disagreement a count-only comparison cannot see.

    The reports are rendered as sorted-key JSON so the diff is stable and the line a
    reader lands on names the field that moved.
    """
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
    """Whether ``--epic <filter>`` names this epic — by directory or by bare slug.

    Epic directories are numbered, so `--epic checkout-flow` has to keep finding
    `0001-checkout-flow`; a filter nobody matches still narrows to nothing, as before.
    """
    return (epic_filter in (epic.name, epic.directory.name)
            or registry.epic_slug(epic.name) == registry.epic_slug(epic_filter))


def run(graph: Graph, epic_filter: str | None = None, check_schema: bool = True,
        checkouts: dict[str, Path] | None = None) -> Report:
    report = Report(org=graph.org_name, profile=graph.profile)
    f = report.findings

    # One resolver, shared. The UI checks and the graph build resolve the same links against the
    # same target files, and a resolver's anchor memo is per instance — two of them means every
    # link target is read and parsed twice for one run's worth of answers.
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
    # One build, shared. Each of these needs the resolved node/edge dump, and on a large book a
    # rebuild costs more than every other check in this function put together.
    ui_data = _ui_graph(graph, resolver)
    if ui_data is not None:
        _check_conflicting_surface_driver(ui_data, f)
        _check_undeclared_walkthrough_runbook(ui_data, f)
        _check_conflicting_entry_origin(ui_data, f)
        _check_reachability(ui_data, f)
        _check_locators(ui_data, f)
        _check_unknown_driver(ui_data, f)
        _check_runbook_driver_surface(ui_data, f)
    if check_schema:
        _check_conformance(graph, f)
        _check_misplaced_book_pages(graph, f)
        _check_misrooted_book_pages(graph, f)
    # Before the epic trim below: a suppression decided against a finding the trim had already
    # dropped would read as "no longer fires", and the trim keeps findings by epic, which a UI
    # finding does not carry.
    _apply_known_defects(graph, f)
    _apply_surface_declarations(graph, f)

    # Above the profile gate, because what this reads is present on both profiles. It walks
    # fixture nodes and `arrange`-key bullets, and self-gates on `stack_runbooks` — so on a book
    # with no fixtures it is already a no-op, and the profile adds nothing to that decision. It
    # was below the gate for years, and the cost was concrete: the one app the QA harness
    # actually drives a browser against is the tree's only `exploration` book, so the checker
    # that reads exactly the bullets its two authored `fixture:` defects were in never ran on it,
    # and `doctor` reported 0 errors both before and after they were repaired. `_check_fixtures`
    # below stays gated: it reads a story's `## Fixtures` section, and an exploration book has no
    # stories to read it from.
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

    # Frozen-entity checks are graph-global (an approved entity is pinned regardless of which
    # epic is being filtered), so run them after any epic trim, appending to the live list.
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
    """``(seed_id, finding_code)`` from a ``known-defect:`` value, or None when it states neither.

    The form is ``<seed-id> <finding-code>``, prose allowed after the pair. Both halves are
    required: a code with no seed is a waiver, and a seed with no code excuses everything.
    """
    m = _KNOWN_DEFECT.match(value.strip())
    return (m.group("seed"), m.group("code")) if m else None


#: The findings that say "this claim is not provable yet": a bullet with no check, a check that
#: cannot fail, a claim under the wrong key. Each is an obligation on QA, which is why a surface
#: nothing exercises can declare them out of scope — no plan will ever be asked to prove them.
#:
#: `unwitnessed-check` is deliberately absent, and is not an oversight the way `insensitive-check`
#: was: it states that the sensitivity harness could not build a witness, which is a fact about
#: the harness and not an obligation anyone owes a proof of. Dropping it under `exercised: false`
#: would suppress it for the one reason it is never claiming.
#:
#: `doctor-codes.md` names this class in prose. The two spellings are compared by
#: `test_the_documented_obligation_class_is_the_one_the_gate_applies`, because the last time a
#: code joined the class only one of them was edited.
OBLIGATION_CODES = frozenset({
    "undeclared-obligation", "unminted-claim", "compound-normative-bullet", "weak-check",
    "insensitive-check", "unstated-precondition", "relation-without-subject",
})


def _apply_surface_declarations(graph: Graph, findings: list[Finding]) -> None:
    """Apply ``exercised: false`` from each surface's ``index.md`` frontmatter.

    A surface nobody exercises — a legacy app kept documented while a successor replaces it — still
    has every normative bullet it ever had, and doctor would keep asking for a check on each. The
    declaration names the whole surface as documented-but-not-driven, and doctor drops the
    obligation-class findings under it (``OBLIGATION_CODES``): the claims stay in the book, and
    nothing is owed a proof of them. Everything mechanical — a dangling link, a missing bullet, a
    locator collision — still fires, because it is about the book, not about a QA plan.

    It is a declaration, not a register: one key on one file, in the surface it describes, with
    two mechanical exits. ``malformed-declaration`` when the value is not a boolean, and
    ``stale-declaration`` when the surface it sits on has no node to downgrade — the index has
    outlived the surface, and the next surface written under that name would inherit the
    declaration unseen.
    """
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
    """Apply every ``known-defect:`` bullet, and report the ones that have gone stale.

    A ``known-defect:`` says: this finding is real, the code is the side at fault, and the
    seed named is the work that fixes it. Doctor drops exactly that code on exactly that node
    while the seed is active. The record has two exits and both are mechanical, which is what
    makes it a record rather than a waiver:

    - ``stale-defect`` when the seed is resolved, dropped, deferred or unknown — the pointer
      outlived the work, and the finding it excused is back in the report;
    - ``stale-defect`` when the excused finding no longer fires — the code was fixed, and the
      bullet now excuses the next genuine occurrence at the same spot.

    On the exploration profile no epic is loaded, so no seed can be checked; the suppression
    and the second exit still apply, and the first waits for the full profile. A value that
    names neither a seed nor a code is ``malformed-defect``: the one way to write the bullet
    so that it excuses nothing.
    """
    seeds: dict[str, str] | None = None
    if graph.profile == "full":
        seeds = {seed.id: seed.status for epic in graph.epics for seed in epic.seeds}

    suppressed: set[int] = set()
    stale: list[Finding] = []
    for node in graph.ui_nodes:
        rel = node.path.relative_to(graph.root).as_posix()
        # Indexed: `known-defect:` repeats, and each bullet excuses a different finding.
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


def _check_epic(graph: Graph, epic: Epic, all_slugs: set[str], f: list[Finding]) -> None:
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

        # `## Dependencies` in the story's own body resolves to sibling stories
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

        # The shape of that section. A bullet stating anything but a blocker is how a rewrite
        # empties the DAG silently — the edges vanish and nothing else reports it.
        for stray in story.dependency_strays:
            f.append(Finding("error", "malformed-dependency-bullet",
                             f"story '{story.slug}' has a bullet under "
                             f"`## {registry.STORY_DEPS_HEADING}` that states no blocker: "
                             f"{stray!r}", epic.name, story.slug,
                             suggestion=f"write it as `- {registry.STORY_DEPS_LABEL}: <slug>`, "
                                        f"or `{registry.STORY_DEPS_NONE}` with no bullet at all"))

        # story.md file present
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
            # An adjudicator that found two acceptance criteria in conflict may not rewrite
            # intent, and rule 2 forbids leaving the finding open: the story carries it until
            # an operator edits the story and clears the key.
            if story.conflict:
                rel = story.story_md.relative_to(graph.root).as_posix()
                f.append(Finding(
                    "error", "story-conflict",
                    f"story '{story.slug}' has acceptance criteria in conflict — "
                    f"{story.conflict}",
                    epic.name, story.slug, path=rel, line=1,
                    suggestion="rewrite the criteria so one intent holds, then "
                               f"`ostler conflict {story.slug} --clear`"))
            # story.md says something — a file that is still the scaffold `ostler create story`
            # wrote is not an authored story, and must not pass as one just by existing.
            if story.unwritten_sections:
                rel = story.story_md.relative_to(graph.root).as_posix()
                f.append(Finding("error", "unwritten-story",
                                 f"story '{story.slug}' is still a bare scaffold — "
                                 f"{', '.join(story.unwritten_detail)}",
                                 epic.name, story.slug, path=rel, line=1))
            # Two paths add a missing section — the scaffolder and an author writing free-hand
            # — and presence alone lets them produce documents that read differently. Order is
            # what makes them one path, so it is checked rather than assumed.
            if story.misordered_sections:
                rel = story.story_md.relative_to(graph.root).as_posix()
                f.append(Finding("error", "story-section-order",
                                 f"story '{story.slug}' orders its required sections against "
                                 f"the contract — {'; '.join(story.misordered_sections)}",
                                 epic.name, story.slug, path=rel, line=1))
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
        # An unclassified seed is not an error — every seed written before `layers` existed is
        # one — but it costs the author a design turn it may not need, so it is worth seeing.
        if s.active and not s.layers:
            f.append(Finding("warn", "unclassified-seed",
                             f"seed '{s.id}' has no `layers:` — every story covering it keeps "
                             f"the mockup turn by default", epic.name, s.id,
                             suggestion=f"ostler seed add {epic.name} {s.id} --layer "
                                        f"<{'|'.join(registry.SEED_LAYERS)}>"))


def _check_fixtures(graph: Graph, f: list[Finding]) -> None:
    """Hold every story's ``## Fixtures`` to the repo's declarations and to its own plan.

    A fixture is held to the bar a test is held to, and that bar is *named, declared, used*.
    Three ways a name can be a lie, all checkable without running anything:

    * The repo's declarations do not stand up at all — malformed, naming a tool nobody opted
      into, or a module with no file. `preflight_errors` is the one implementation of that,
      shared with the run's own preflight, so a repo cannot pass `doctor` and then fail to boot.
    * A story names a fixture the repo does not declare. Nothing would arrange that state; the
      scenario would reach for it after the app booted and be reported as blocked.
    * A story's plan and its story.md disagree about which fixtures the story arranges with.
      Both directions matter and they are not the same defect: an *undeclared* use is a story
      whose arrangement is invisible to a reader deciding whether it is safe to change, while an
      *unused* declaration is a story claiming an arrangement it no longer makes.

    A story with no `qa_plan.py` yet is not in disagreement with anything — the plan phase has
    not run — so only the repo-level half applies to it.
    """
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
            # `None` is not `set()`: no plan yet means nobody has said whether an undeclared
            # name is an arrangement or a word, and that is a third answer, not an empty one.
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
            # Only names the repo *does* declare. An undeclared name is one fact, and
            # `unknown-story-fixture` above has already spent this same evidence on saying
            # which repair it wants; reporting it a second time under a second code pairs an
            # error with a warning that prescribe opposite repairs for one bullet.
            for name in sorted((stated & known) - names):
                f.append(Finding(
                    "warn", "unused-story-fixture",
                    f"story '{story.slug}' names fixture '{name}' but its qa_plan.py never asks "
                    f"for it ({plan_rel})",
                    epic.name, name, path=rel, line=1))


def _undeclared_fixture_repair(name: str, referenced: set[str] | None, plan_rel: str) -> str:
    """Say what to do about a `## Fixtures` name the repo does not declare.

    The spelling of the name cannot say whether someone forgot to declare an arrangement or
    wrote a domain noun that was never one — *a name that nothing declares and nothing uses is
    not an undeclared thing; it is not a thing, and only what reaches for the name says which*.
    The story's own plan is what reaches, so the plan picks the repair. Measured over stablemate
    and all five paddock apps at the time this was written: eleven undeclared names, **none**
    used by a plan, eleven unused — so the single suggestion this replaced ("declare it") was
    wrong in every case in existence, and the correct repair was the one filed beside it at the
    lower severity as a separate warning.

    `referenced is None` is the story whose plan phase has not run. It gets no repair, because
    neither is supported yet — the same rule as *undetermined ⇒ do not emit executable code*,
    one level up, at the advice.
    """
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
    """A `capture:` bullet is a name and a source, in the grammar a `$name` reference can spell.

    Ungated by profile and by node type, because what it reads is neither: every node type that
    admits a `capture:` key admits the same grammar, and a book with no capture bullets is
    already a no-op here. Written from the book alone — whether the fact is captured *early
    enough* for a given `$name` is `compile_plan`'s `unresolved-precondition` question, the same
    division `_check_fixture_undeclared_provides` keeps.

    The reason this exists at all is that the packet builder's docstring used to say a
    malformed `capture:` was "left for `ostler doctor` to report", and doctor had no capture
    checker of any kind — so the rule lived only in a docstring nothing enforced, and a
    misspelled bullet was reported by nobody while a later `$name` took the blame.
    """
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
    """A `fixture:` bullet in the book names an arrangement this repo actually declares.

    The book says what a claim is true of and how to observe it; a `fixture:` bullet says
    which state it is true *in*, and that is a fact about the invariant rather than about any
    one plan — which is why it is written here and not left for each plan to rediscover. The
    bar is the story bullet's, for the same reason: a name nothing declares arranges nothing,
    and a compiler reading the book would emit a call the harness refuses at run time.
    """
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
                # The bullet states this node arranges nothing and says why. There is no
                # name to resolve, and refusing it would leave a node that needs no
                # arrangement no way to say so except by omitting the bullet — which is
                # the undecided case, and `unarranged-journey` exists to tell them apart.
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
    """The state a `fixture:` bullet says it is arranged in, against what the fixture declares.

    The tail after the em dash is the *consumer's* precondition, and `compile_plan` copies it
    verbatim into the scenario's `preconditions=[...]` — so a scenario states what must hold
    before it runs in words written by the node that uses the arrangement, about work the node
    that performs it may never have claimed to do. A book fixture node with no `provides:` at
    all is exactly that case: the precondition reads as settled, nothing on the producing side
    says the arrangement leaves that state behind, and no run can tell the difference, because
    a precondition is a sentence the harness carries rather than a thing it observes.

    Only a *book* fixture node can reach this. The hand-written `qa: {fixtures:}` tier refuses
    an entry with no `provides:` in `fixtures.declared()`, so a name that resolves only there
    has already been held to it — `target is None` is that case, not a missing check.
    """
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


#: A `fixture` node's own `## Steps` are restricted to this narrower set, not the runbook's
#: full `STEP_KINDS` — a fixture arranges state for a scenario, it does not bring a stack up
#: or drive one, so `prepare`/`service`/`health`/`drive` say something a fixture cannot mean.
_FIXTURE_STEP_KINDS: frozenset[str] = frozenset({"seed", "run", "verify"})


def _check_entry_properties(graph: Graph, f: list[Finding]) -> None:
    """An entry of an ``entries=True`` key may only carry the properties its key declares.

    ``BulletKey.properties`` empty means *no vocabulary is declared*, and a key with no declared
    vocabulary is not checked — the alternative would make every entry in every book a finding on
    the day this check landed, which is a statement about the check's arrival rather than about
    any book. A key adopts the check by writing its vocabulary down.
    """
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


#: A bullet key is spelled like this: a lowercase letter followed by up to 24 more lowercase
#: letters, digits or hyphens. `_check_undeclared_container_properties` uses it to tell a genuine
#: `- childkey: value` line apart from a numbered-list item whose "key" is a run of prose.
_BULLET_KEY_SPELLING = re.compile(r"^[a-z][a-z0-9-]{0,24}$")


def _check_undeclared_container_properties(graph: Graph, f: list[Finding]) -> None:
    """A bullet key the node type does not declare can still bury a bullet key it does.

    `_check_record_properties` catches this when the parent key is itself declared and marked
    ``record=True`` — the grammar that governs its children is known, so a child spelled like a
    node key is unambiguous. A key the type never declared has no grammar on file at all, so
    `model` falls back to treating it as a plain nested list: every descendant, flattened to
    `"childkey: childvalue"` strings, lands in `UINode.meta[key]` exactly as an undeclared key's
    children always do — there is no raw markdown to walk here, and no `record:`/`entries:`
    distinction to consult, because none was ever declared.

    That fallback is why a child key the node type *does* declare can still hide inside an
    undeclared parent: `- request:` on an `endpoint` is not itself a bullet the type recognizes,
    so its `- method:`/`- path:` children arrive as flattened strings under `meta["request"]`
    rather than as the top-level `method:`/`path:` bullets the type is grading against. The
    parent key being undeclared is *why* the child is invisible, not merely misplaced, which the
    message says explicitly — the reader needs to know the fix promotes the child out from under
    a key the node's own type never wrote down.

    One finding per buried child key, not one per parent, matching `_check_record_properties`.
    A `ref` names one subject so the finding can be closed on its own: promoting `method:` and
    leaving `path:` under the same parent discharges half the problem, and a ref naming the set
    would still fire afterwards with a subject that is now partly false.
    """
    for node in graph.ui_nodes:
        declared = registry.declared_keys(node.type)
        rel = _rel_path(graph, node)
        for key, value in node.meta.items():
            if key in declared or not _BULLET_KEY_SPELLING.match(key) or not isinstance(value, list):
                continue
            children = [item.split(":", 1)[0].strip() for item in value]
            hits = [child for child in children if child in declared]
            if not hits:
                continue
            for child in hits:
                f.append(Finding(
                    "error", "misnested-bullet",
                    f"{node.id}: `{child}:` nested under `{key}:` is a property spelling of "
                    f"{node.type}'s own `{child}:` bullet, but `{key}:` is not a key {node.type} "
                    f"declares, so it is invisible rather than merely misplaced",
                    path=rel, line=node.line, ref=f"{key}:{child}", fixable=True,
                    suggestion=f"promote `- {child}:` to a top-level bullet of the node"))


def _prose_burial_keys() -> frozenset[str]:
    """Every key that makes a node's meta subtree normative or observational wherever it surfaces.

    Shared normative keys mint an obligation on every type; `_OBSERVATION_KEYS` (defined later in
    this module) says what proving one looks like. A book buries both kinds under the same prose
    paragraph, and neither is more buried than the other, so `_check_prose_buried_bullets` reads
    them as one set rather than asking twice. Computed lazily, not at import time, because
    `_OBSERVATION_KEYS` is itself assembled later in the module than this function's own
    definition needs to sit.
    """
    return frozenset(registry.SHARED_NORMATIVE_KEYS) | _OBSERVATION_KEYS


def _check_prose_buried_bullets(graph: Graph, f: list[Finding]) -> None:
    """A numbered list item is prose, and a bullet filed beneath one is invisible to the node.

    `model` gives an undeclared meta key the same flat-subtree fallback whatever the key looks
    like: every descendant becomes a `"childkey: childvalue"` string in `UINode.meta[key]`,
    whether the key reads as a plausible bullet the type simply never declared —
    `_check_undeclared_container_properties`'s case — or is the running text of a numbered list
    item, which is this one. The container being prose rather than merely undeclared changes
    nothing about what `model` does with it and nothing about what the grammar can read back out
    of it: `registry.declared_keys(node.type)` is asked the same question either way, and a key
    that fails it is unstated no matter what wrote it.

    Scope is the burial, not the parent's shape. `key in declared` and `_BULLET_KEY_SPELLING`
    both have to fail before a key is even considered, so a genuine declared multi-word key
    (`consistency rule`, `consistency group`) is excluded before the check ever looks at its
    children — the same guard `_check_undeclared_container_properties` applies, and for the same
    reason: a predicate that tested only the spelling would report every one of them. A prose
    key whose subtree buries nothing `doctor` grades — an ordinary aside, a definition-list
    idiom — stays silent here, the large legitimate population this check has to leave alone.

    One finding per buried container key, not one per node: a node can carry more than one
    prose-shaped meta key, and each one that buries a normative or check key is its own defect
    with its own line and its own `line`. Within one container, though, the finding names every
    buried child at once — `consistency` and `verify` filed under the same numbered item are one
    broken container, and an edit that promotes only one of them out leaves the other exactly as
    buried as it was, so the ref names the whole set and the finding does not read as closed
    until none of it is.

    Deliberately not a compiler gap kind. Nothing here is undetermined the way an unresolved
    reference or a missing arrangement is — `compile_plan` never reaches this node's buried
    bullets to have an opinion about them, because the book itself already states, in a place
    nothing reads, that they exist. That is a fact about the book, true whether or not any
    scenario ever compiles this node, so it is a doctor code rather than a `Gap`.
    """
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
    """A property nested under a ``record=True`` key may not be a bullet key the node declares.

    A record's children are properties of the one thing its key names, so a child spelled like a
    key of the node itself states nothing the node is held to: ``- status: 200`` written under
    ``- response:`` is a property of the response, and the endpoint's own ``status:`` claim — the
    one that mints an obligation a scenario has to prove — is absent. The two readings are both
    grammatical and only one is what the author meant, which is why this is reported against the
    nesting rather than resolved in favour of either.

    Only keys the type declares are reported. If the record key also declares a ``properties``
    vocabulary, a child of any other spelling is checked instead by the arm below, as
    ``unknown-record-property``: the two are mutually exclusive, since a child spelled like a
    node key can never also be one the record key admits. A record key with no declared
    vocabulary leaves a child of any other spelling unchecked by either arm — an undeclared
    vocabulary is checked by nothing here, for the same reason ``_check_entry_properties`` skips
    one, and adopting the check is what declaring it means.

    Deliberately not a compiler gap kind, on ``_check_bullet_value_kinds``'s reasoning: it is a
    statement about the book alone, true whether or not any scenario ever compiles the node.
    """
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


def _route_kind_parser(predicate: Callable[[str], bool], reason: str) -> Callable[[str], str]:
    """Compose a `routes.route_grammar` pair into a `values.VALUE_KINDS`-shaped parser.

    `ROUTE_GRAMMAR` holds `(predicate, reason)`; every `VALUE_KINDS` entry is a single
    `Callable[[str], str]` that returns `""` for an acceptable value and a reason otherwise.
    Two different contracts for the same job — this is where they meet, so `_check_bullet_
    value_kinds` can treat a `"route"`-kinded key exactly like any other kind once it has
    the driver's row, rather than growing a third, bespoke shape of its own.
    """
    def parse(value: str) -> str:
        return "" if predicate(runbook_mod.bullet_text(value)) else reason
    return parse


def _check_bullet_value_kinds(graph: Graph, ui_data: dict | None, f: list[Finding]) -> None:
    """A bullet whose key declares a ``value_kind`` must carry a value its kind's parser accepts.

    Modeled on ``_check_entry_properties`` — the same shape, a declaration on ``BulletKey``
    checked against what an author actually wrote, applied to plain bullet values instead of
    ``entries:`` children. ``value_kind`` empty means no grammar is declared, so nothing is
    checked; an *empty* authored value is not malformed, it is *absent*, and `missing-required-
    bullet` already owns that case, so this check skips it rather than doubling it.

    Deliberately not a compiler gap kind. `invalid-http-method` and `unidentifiable-screen` are
    consequences at the scenario level, raised only once a plan tries to compile; this is a
    statement about the book alone, true whether or not any scenario ever compiles it.

    ``ui_data`` (the same dump ``_check_reachability`` reads, or ``None`` when the graph would
    not build — see ``_ui_graph``) is read only to pick the surface's declared driver for a
    ``"route"``-kinded key: that key is not looked up in ``VALUE_KINDS`` at all. Instead this
    check asks ``routes.route_grammar(driver)`` directly for the ``(predicate, reason)`` pair
    the resolved (or unresolved — ``route_grammar(None)`` names the same default grammar every
    other driver falls back to) driver is held to, and composes the two into the same
    empty-string-or-reason shape a ``VALUE_KINDS`` parser returns. ``routes.ROUTE_GRAMMAR`` is
    thereby the single statement of what a ``route:``/``path:`` bullet may say, for every
    driver at once: adding a row there is sufficient to change what this check accepts, with
    no second edit here. Every other kind reads ``VALUE_KINDS[key.value_kind]`` unchanged.
    """
    surface_by_id = {n["id"]: n.get("surface", "") for n in ui_data["nodes"]} if ui_data else {}
    driver_by_surface: dict[str, str | None] = {}

    def _driver_for(node: UINode) -> str | None:
        if ui_data is None:
            return None
        surface = surface_by_id.get(node.id, "")
        if not surface:
            return None
        if surface not in driver_by_surface:
            try:
                driver_by_surface[surface] = reach.surface_driver(ui_data, surface)
            except reach.UnsettledSurfaceDriver:
                # Already reported by `_check_conflicting_surface_driver` or
                # `_check_undeclared_walkthrough_runbook`; not this check's finding to
                # duplicate. Treat as undeclared so this surface's nodes still get
                # checked against the grammar they have always used.
                driver_by_surface[surface] = None
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
            if kind == "route":
                predicate, route_reason = routes_mod.route_grammar(_driver_for(node))
                parser = _route_kind_parser(predicate, route_reason)
            else:
                parser = values_mod.VALUE_KINDS[kind]
            for index, value in enumerate(_bullet_values(node.meta.get(key.key, "")), 1):
                if not value.strip():
                    continue
                reason = parser(value)
                if not reason:
                    continue
                f.append(Finding(
                    "error", "unparsable-bullet-value",
                    f"{node.id}: `{key.key}: {value}` does not parse as a `{key.value_kind}` "
                    f"value — {reason}",
                    path=rel, line=node.line,
                    ref=refs_mod.bullet_ref(node.id, key.key, index)))


def _check_fixture_grammar(graph: Graph, f: list[Finding]) -> None:
    """The fixture-node grammar (`docs/okf-runbook.md`'s fixture tier), held to its own rules.

    Gated to ops-runbook services, the same way `_check_runbook`'s shape checks are: a repo
    with no stack to bring up has nothing a fixture arranges state in front of.
    """
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
    """Each `provides:` entry says where its fact comes from: observed, or asserted.

    A fact a fixture provides is either **observed** from a step's output — `from:` the step
    whose stdout holds it, `read:` the path within that stdout — or **asserted** by the
    fixture's own construction, and then `is:` states the value the construction makes true.
    Only the book can say which. The two are byte-identical downstream, and the difference is
    not cosmetic: a fixture that empties a directory by restarting the service holding it is
    not reading the zero out of anything, and a fixture that seeds a widget and reports its
    name is not asserting it.

    An entry declaring neither leaves the source undetermined, and the harness used to guess —
    the fixture's last step, its whole stdout parsed as JSON. That is right only for a fixture
    whose last step happens to print JSON; every other one aborted its scenario in `json.loads`,
    naming a step the author had never pointed at. An entry declaring both is the same defect
    seen from the other side: two answers is not one answer.

    Raised by walking the book alone, so the author hears it while writing the fixture rather
    than from a scenario that aborted three services later.
    """
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


#: A `secrets:` child must be a bare environment-variable name — no value, no mint recipe.
#: The harness resolves it from its own `os.environ` at run time, so anything this pattern
#: rejects (`FOO=bar`, `foo-bar`, a recipe) is a name no process's environment could hold.
_ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _check_fixture_secret_names(graph: Graph, fixtures: dict[str, UINode], f: list[Finding]) -> None:
    """Every `secrets:` child is a plausible environment-variable name, nothing else.

    Unlike a runbook's `secrets:` (`NAME: mint-recipe`, run once per stack bring-up), a
    fixture's `secrets:` is a flat list of NAMES the harness resolves from its own
    environment at run time — no recipe, because a fixture runs once per scenario and
    minting a fresh credential that often is the plan's problem, not the fixture's.
    """
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
    """A `needs:` chain that composes a fixture on top of itself is unbuildable, not deferrable.

    `needs:` is the only `link=True` bullet the `fixture` node type carries, so every link a
    fixture node's own bullets contribute is a `needs:` target — the same fact
    `_check_runbook_environment` leans on for `environment:`, applied here instead.
    """
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
    """The fact names a fixture node's `provides:` bullet declares, one per child.

    Each child may carry trailing prose after the same em dash `fixture:` bullets use to
    separate a reference from what it leaves behind — only the head names the fact.
    """
    keys: set[str] = set()
    for value in _bullet_values(node.meta.get("provides", "")):
        head = value.partition("—")[0].split()
        if head:
            keys.add(head[0])
    return keys


def _needs_binding(graph: Graph, node: UINode, by_name: dict[str, UINode],
                    value: str) -> tuple[UINode, tuple[str, ...]] | None:
    """A `needs:` child's target fixture and the `arg=value` tokens it binds, if any.

    A `needs:` child is a link, not a bare name (`needs.link is True`) — the same grammar
    `fixture:` uses otherwise, so the link is resolved the way `_check_fixture_needs_cycles`
    resolves every `needs:` link, and whatever text remains once the link markup is stripped is
    parsed as `fixture:`-style args by substituting the target's own name back in.
    """
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
    """Names the fixture's own `needs:` bindings supply into its env before it runs.

    Runtime (`Qa._exec_book_fixture`) runs a needed fixture with `{}` first, then binds the
    binding's `name=value` tokens into the *calling* fixture's own env — so these names are
    already supplied by the time a `fixture:` caller's args are applied, the same as a
    directly-passed arg.
    """
    supplied: set[str] = set()
    for value in _bullet_values(node.meta.get("needs", "")):
        binding = _needs_binding(graph, node, by_name, value)
        if binding is None:
            continue
        _target, args = binding
        supplied.update(tok.partition("=")[0] for tok in args if "=" in tok)
    return supplied


def _check_needs_binding_args(graph: Graph, by_name: dict[str, UINode], f: list[Finding]) -> None:
    """A `needs:` binding's `name=value` tokens name the CONSUMER's own declared `args:`.

    Runtime runs a needs target with `{}` (it is a shared, once-per-scenario dependency and
    cannot be parameterized), then binds the tokens into the *consumer's own* env — so a
    binding's names are the consumer's own argument names, never the target's, and validating
    them against the target's `args:` (as this used to) produces false positives whenever the
    consumer legitimately declares the name itself.

    A needs target that itself declares `args:` is a separate, unconditional error
    (`fixture-needs-target-args`): runtime can never pass it anything, so a declared `args:`
    on a needs target can never be satisfied.
    """
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
    """A `fixture:` bullet's `name=value` args must match the target's declared `args:`.

    Checked both directions: a passed arg the target does not declare, and a declared arg the
    call never passes and the target's own `needs:` bindings do not already supply — the
    grammar has no default values, so an omitted, unsupplied declared arg leaves a call without
    a value it requires just as surely as an unknown one is a typo. An arg the target's `needs:`
    bindings already supply is already covered before the caller's args apply — a caller that
    passes it anyway is a second source for the same arg, which is its own finding.
    Only checkable for a target naming a *book* fixture — an app-language or Python-module
    fixture's parameters are declared in `agents.yml`/its own code, not in this book at all.
    """
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
    """An `@node.key` reference must name a fact the target fixture actually declares.

    Static and order-free only: whether some fixture *is arranged early enough* in a given
    scenario for the fact to be there yet is `compile_plan`'s `unresolved-precondition` gap,
    not this — this only asks whether the target ever declares the key at all. A `$name`
    reference is never checked here for the same reason: whether an earlier `capture:` in the
    same scenario produced it is also a `compile_plan` question, not a fact about the book.
    """
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
    """`compile_plan`'s gap report, in doctor's own vocabulary.

    `Gap.kind` is already spelled the way `compile_plan_gaps` names it —
    `unresolved-precondition`, `uncompilable-claim` — so the mapping is the identity on the
    code and a wrapper on everything else: a `Gap` names a state `compile_plan` could not
    reach or a claim it had no action for, and either one is an error, not a warning, the
    same way an undeclared reference is. This is the doctor side of the split the fixture
    checks above describe: whether a fixture is arranged *early enough*, or a `$name`
    produced *before* it is read, is a property of one compiled plan against one context
    packet, not of the book alone — so it is computed here from a `Gap` list a caller
    already has (`compile_plan_gaps`), never rediscovered by walking the graph.
    """
    findings: list[Finding] = []
    for gap in gaps:
        # Every `Gap.kind` `compile_plan_gaps` can mint is spelled out as its own literal
        # `Finding(...)` call, on purpose: `test_every_doctor_code_is_classified_on_purpose`
        # (workflows/tests/okf_builder/test_drift_tripwire.py) reads doctor's codes off its
        # AST and cannot resolve a code passed through a variable assigned from an attribute
        # access like `gap.kind` — nor should it, since the whole point of that tripwire is
        # that a *new* kind forces a deliberate classification decision here, not a silent
        # pass-through. An empty or unrecognized kind — which `compile_plan_gaps` should
        # never produce, but this function does not trust that — falls back to
        # `uncompilable-claim`, the existing code for "this obligation compiles to no action
        # at all".
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
        elif gap.kind == "conflicting-entry-origin":
            findings.append(
                Finding("error", "conflicting-entry-origin", message, ref=gap.obligation_id)
            )
        elif gap.kind == "conflicting-surface-driver":
            findings.append(
                Finding("error", "conflicting-surface-driver", message, ref=gap.obligation_id)
            )
        elif gap.kind == "undeclared-walkthrough-runbook":
            findings.append(
                Finding("error", "undeclared-walkthrough-runbook", message, ref=gap.obligation_id)
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
            # The second kind whose compiler spelling is not a doctor code of its own, for the
            # same reason `no-verify-declared` below is not: `_check_book_fixtures` already
            # raises `qa-fixture-bullet` on this very bullet, from the book alone, and a second
            # code would grade one defect twice depending on which component noticed it. What
            # the compiler adds is not a new defect but the consequence — which obligations
            # went uncompiled because of it — and that belongs in the message, not in the code.
            findings.append(Finding("error", "qa-fixture-bullet", message, ref=gap.obligation_id))
        elif gap.kind == "undetermined-provided-fact":
            # Unlike the two kinds around it, this one keeps its own spelling: `_check_provided_facts`
            # raises exactly this code from the book alone, so the identity mapping grades one defect
            # one way. What the compiler adds is which obligations the entry withheld — the message —
            # and the finding it produces points at the same `provides:` bullet the book check does.
            findings.append(
                Finding("error", "undetermined-provided-fact", message, ref=gap.obligation_id)
            )
        elif gap.kind == "unparsed-check-bullet":
            # Same reasoning as the kind above, and the same existing code: doctor
            # already refuses this bullet as `unparsed-check` from the book alone (`_check_ui`),
            # and what the compiler adds is the consequence — which obligations went unproven
            # because of it — which belongs in the message, not in a second code.
            findings.append(Finding("error", "unparsed-check", message, ref=gap.obligation_id))
        elif gap.kind == "unparsed-capture-bullet":
            # And the same again for `capture:`: `_check_book_captures` refuses the bullet from
            # the book alone, and the compiler adds which fact went unminted because of it.
            findings.append(Finding("error", "unparsed-capture", message, ref=gap.obligation_id))
        elif gap.kind == "uncaptured-declaration":
            # A declared `capture:` no builder emitted. Not a new code: the book is not wrong —
            # it named a fact and where to read it, which is exactly what the grammar asks for —
            # and what went missing is an *action*, which is what `uncompilable-claim` already
            # names. A second code would grade "this compiler has no way to bind that value" as
            # a different defect depending on whether the thing unbound was a check's subject or
            # a capture's, and an author reading either one has the same nothing to rewrite. The
            # branch is explicit rather than left to the catch-all below because a kind that
            # falls through there is indistinguishable from one nobody decided about.
            findings.append(Finding("error", "uncompilable-claim", message, ref=gap.obligation_id))
        elif gap.kind == "no-verify-declared":
            # The other kind whose compiler spelling is not a doctor code: "the book declares no
            # check for this obligation to prove" is `undeclared-obligation`, which doctor
            # already raises from the book alone. It keeps that code's own severity — a `warn`
            # here and an `error` there would be one rule graded two ways depending on which
            # component noticed it.
            findings.append(
                Finding("warn", "undeclared-obligation", message, ref=gap.obligation_id)
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
    """OKF conformance + per-type frontmatter schema, walking every Concept on disk.

    Conformance is the one hard OKF rule: a non-reserved ``.md`` must carry a non-empty ``type``
    (``okf-missing-type`` otherwise). On top of that, ostler validates each Concept's frontmatter
    against **its own declared type's** schema (warn-level), which OKF permits for known types.

    Dispatch is by the file's declared ``base_type`` — *not* by the glob that discovered it. That
    is deliberate (profile §5): a ``type: screen`` doc under ``features/`` is a first-class UI node
    (no schema), so it must not be validated as a ``feature`` just because it matches
    ``features/**/*.md``. The glob only discovers the file; the frontmatter decides the ruleset.
    """
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
                # Read-only, so through the shared accessor: `_check_ui_file` and the graph
                # load want the same parse of the same file, and the index makes it survive
                # the process. A copy of the frontmatter, because the mapping behind it is
                # shared with every other reader in this run.
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
    """A typed book page that has moved (or was authored) outside every doc root is invisible.

    `_check_conformance` walks *in* from ``graph.doc_roots`` — it can only ever complain about
    a file it finds under a root. The file that stopped being read is the one that isn't under
    any of them any more, and until now that move produced no diagnostic at all: a real book
    page with a real declared ``type`` that a `git mv` (or a first draft) dropped outside
    ``docs/features``, ``docs/epics``, ``specs``, or a paddock app's own doc roots simply
    disappears from the graph. Only a surviving referrer shows anything, as `dangling-link`; an
    unreferenced page vanishes with zero findings.

    Enumeration is `git ls-files`, not a filesystem walk. A walk would sweep `.venv/`,
    `node_modules/`, and every other untracked directory a real repo accumulates, inventing
    findings out of files nobody is claiming as a book page. The tree's standing core property
    for "is this file even in scope" is *git-tracked*, and where that property is undetermined —
    `graph.root` is not inside a git repository at all — the rule is "do not emit", the same
    rule the rest of ostler applies to every other undetermined case: silence, not a guess.
    """
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
        # A nested book -- a paddock app under paddock/data/apps/<app>/, or any other
        # subtree that `model.find_root` would resolve as its own root (its own `docs/`,
        # `ostler.yml` or `agents.yml`) -- owns this file under its own `doc_roots`. It is
        # not this graph's to flag; skip anything whose nearest root isn't `graph.root`.
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
    """A typed page can sit inside *a* doc root and still be inside the *wrong* one.

    `_check_misplaced_book_pages` catches a page that moved outside every root; this is the
    sibling case it deliberately does not cover: a file whose declared `type:` and the root
    it was actually found under disagree. `_feature_paths` admits any file under
    `docs/features` that declares *some* type -- it does not ask whether that type's
    registered `doc_root` (`registry.REGISTRY_BY_NAME[base].doc_root`) is `features` at all.
    `type: spec.qa-okf-context` (registered under `specs`) committed under `docs/features`
    is the concrete case this was written for -- `committed`, because enumeration is
    `git ls-files` (the sibling's docstring carries that reasoning), and `ostler qa context`
    writes its scratch files untracked, so this fires on the durable form of the defect and
    deliberately not on the transient one: its file-level node is correctly suppressed
    (`spec` is not a `UINodeType`), but `_parse_ui_nodes` still recurses into its `##`
    sections, seeding `untyped` UI nodes with no finding anywhere -- `okf-missing-type`
    doesn't fire (a type is present), `unknown-type` doesn't fire (`spec` is registered), and
    `misplaced-book-page` doesn't fire (the file *is* under a doc root, just the wrong one).

    The join runs in both directions, because `registry.doc_root_of` answers for both
    registries: the five `EntityType`s carry an explicit root each, and every `UINodeType`
    carries `features`. A `type: screen` page sitting under `docs/specs` used to raise
    nothing at all -- not here (no `doc_root` to disagree with), not from
    `misplaced-book-page` (it *is* under a root), and it never became a UI node either,
    since `_feature_paths` only admits files under `docs/features`. It was a book page
    nothing read and nothing reported, and it could reach none of the compile targets,
    because a surface is where the file sits. A `type:` this registry does not recognize at
    all is `unknown-type`'s finding, not this one.
    """
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


# ---------------------------------------------------------------------------
# OKF UI profile — mandatory linter (docs/okf-ui-support §7)
# ---------------------------------------------------------------------------
# Every finding below is an *error* the agent is expected to fix, each with a deterministic remedy
# (`ostler fmt` or `ostler scaffold`) so a strict `doctor` converges instead of nagging (§7.1).
#
# `code:` grounding IS checked here (`_check_code_grounding`), reversing an earlier decision that
# deferred it to a later QA gate on the grounds that it "couples doc authoring to code existing".
# It does — and that coupling is the point: `code` is declared `BulletKey("code", link=True)` but
# nothing validated it, so two path conventions could silently coexist in one tree and a citation
# could outlive the symbol it names. Coverage is a join over these targets; an unvalidated target
# is a join key nobody checked.
#
# `verify:` was deferred here for years on the grounds that its value was a test id as often as a
# `path::symbol`, so it had no single shape to hold it to. It has one now, and it is a different
# shape entirely: a named check from `ostler.checks`, an *observation* rather than the name of the
# code that ran. That is what makes it groundable — and what makes an assertion unable to be
# weaker than the claim it is filed under, since the declaration is the assertion.
#
# A `code:` ref names something that exists, full stop — there is no escape hatch for a target
# that has been deleted. The QA grounding gate does not require a deletion to be cited at all
# (`workflows`' `verify_story_documentation` treats a `changedCode` entry with `status: deleted`
# as satisfied on its own); documenting the absence of something is not documentation.
_UI_HEADING_BY_LOWER = {h.lower(): h for h in registry.UI_HEADING_TO_TYPE}
# A symbol's parts, as a book writes them: `(*FirebaseClaimsWriter).SetRoleClaims` → the receiver
# and the method; `Alpha.handle` → the class and the method; `Diff` → itself.
_SYMBOL_PART = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_SPACE = re.compile(r"\s")


def _known_types(graph: Graph) -> set[str]:
    return (set(registry.REGISTRY_BY_NAME) | set(registry.UI_TYPES_BY_NAME)
            | {k.name for k in graph.template_kinds})


def _check_container_siblings(doc: markdown.MarkdownDoc, rel: str, f: list[Finding]) -> None:
    """No parent heading owns the same container heading twice (`### Fields` under one concept).

    This is what a heading inserted into the middle of a file looks like from the graph's side.
    Write `## concept: SlugCollisionError` just above the `### Fields` that belonged to the
    concept above it, and markdown re-parents that block to the new concept without a word of
    complaint: the fields are still fields, the file still parses, `doctor` was still silent —
    the only trace is that one concept has lost its attributes and another has grown two `Fields`
    blocks. Two of the same container under one parent has no legitimate reading, which is what
    makes it a usable proxy for the mistake that produces it.
    """
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

    # bad-heading-type: a case/spelling variant of a known UI heading (its `### id` children would
    # otherwise be silently unrecognized) — `ostler fmt` canonicalizes the casing.
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
            # Both codes are spelled as literals rather than selected into one `code` variable:
            # the code list is enumerated statically — by `doctor-codes.md`'s join test and by
            # okf-builder's drift tripwire — and a code a reader has to execute a ternary to
            # learn is a code neither of them can see.
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
    """Whether the file at *path* declares *symbol* — `inventory`'s grammar, not a second one.

    This delegates on purpose. It used to ask whether every part of the symbol appeared as a
    *word* in the file, which is not the same question and answered it wrong in the one
    direction that matters: a facade module re-exporting a name (``from .renderer import
    Renderer``) still contains the word, so a citation whose definition had moved away stayed
    green — the drift this check exists to catch. The inventory already knew how to read a
    declaration; grounding just wasn't asking it.

    It delegates to the *indexed* accessor rather than reading the file here, which is what
    makes a hot file's symbol table cost one extraction per run rather than one per citation —
    and nothing per run at all once a previous process has left it on disk.
    """
    return inventory.declares_at(path, symbol)


def _check_test_subject(node, rel: str, f: list[Finding]) -> None:
    """`code:` cites the product, never the test suite (`refs.is_test_source`).

    A book is a contract a user can assert against the running product. A mock, a fake declared
    in a test file or a fixture helper is how the product's tests are built, so a node citing
    only those documents an implementation detail no user can observe, and every obligation
    doctor then asks of it — a `verify:` per claim, a grounded symbol — is work spent making a
    test double provable. Two findings, because the remedies differ:

    - `test-subject`: every citation is test source. The node documents no product and is
      deleted — the whole page when it is the page's own node.
    - `code-cites-test`: product and test citations mixed. The test citations come out of
      `code:`; a test that proves the claim belongs under `tests:`.
    """
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
    """`code:` targets name a file that exists, and a symbol that file declares.

    Checked on every node, regardless of the node's registry type: `code:` owns and grounds on
    every type (`registry.owning_keys`'s docstring — a flow or a screen cites the code it is
    grounded in whether or not its profile lists the key, and always has), so this reads
    `node.meta.get("code")` directly, the same way `_check_test_subject` already does, rather
    than skipping a node whose type happens not to declare the key.

    This is what stops two path conventions from silently coexisting, what keeps the book
    honest as the source moves under it, and what surfaces a documented unit that has since
    been deleted. The grammar is the book's own (OKF UI profile §5):
    `<path-relative-to-repo-root>::<symbol>`, the symbol qualified by its owner when it has one.

    A target qualified with a repository other than the book's own (per
    `source_snapshots.book_repository`) is checked against *checkouts[repository]* — the same
    existence, `@digest` and symbol checks a local ref gets, just read off that checkout instead
    of `graph.root`. A repository this run was given no checkout for earns `unreachable-citation`
    instead: there is nothing under this checkout to check it against, and that is a fact about
    the run, not the book, so its `suggestion` names what the run needs (a `--checkout` for that
    repository), never a fix to the book or a command to run.

    Every ref that does resolve to a source root gets the same three: `stale-citation` when its
    `@digest` disagrees with the file's current content, `unstamped-citation` while it carries no
    digest yet — a warning, not an error, since a book earns its first stamp only once a turn
    touches the node or `ostler stamp --from-catalog` migrates it — and `missing-code-symbol`
    when the file no longer declares the cited symbol.

    Note this cannot route through the link scan: `links.is_doc_link` rejects any href
    containing `::`, and a backticked `` `x.go::S` `` is inline code, not a markdown link — so
    `markdown.iter_links` never yields it. The bullets are read directly, as the
    required-bullet loop does.
    """
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
                    pass  # unreadable tells us nothing; same call this check makes below
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
                # "Existence is enough" holds only for a node whose subject genuinely IS a
                # whole file. `registry.UINodeType.kind` is the axis that says so, and not by
                # coincidence: a `kind == "file"` type (screen, cli, server, concept, format,
                # flow, runbook, environment, fixture) is declared by a page and documents that
                # page's whole subject, while a `kind == "section"` type (component, command,
                # endpoint, interaction, invocation, method, field, step, untyped) is declared
                # as a *part* under a heading. A whole-file reference names a container; a
                # reference to a container is not a reference to the part it contains. So a
                # section node citing a bare path has not said where it is grounded, only where
                # to start looking.
                uitype = registry.UI_TYPES_BY_NAME.get(node.type)
                if uitype is None or uitype.kind == "file":
                    continue
                # …and only where naming a region is *possible*. `inventory.SOURCE_SUFFIXES` is
                # the set of languages whose declarations this repo can read, and it is the same
                # set `_declares` gates on — so outside it there is no `path::symbol` an author
                # could write that `missing-code-symbol` would accept. A component citing
                # `static/index.html`, a step citing `compose.yml`, a fixture citing a Maestro
                # `.yaml` are not under-specified citations: they are citations in a grammar with
                # no parts to name, and an error nobody can act on is not a rule (D-3j).
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
                # The profile admits `path::symbol` **or a `file` region** — and a region is
                # prose ("notification permission bootstrap"), not a name. There is nothing to
                # ground but the file, and holding prose to a symbol's bar would flag the
                # convention the profile itself grants. When the book and the tool disagree
                # about grammar, the book wins.
                continue
            try:
                grounded = _declares(target, symbol)
            except OSError:
                # A file that exists but cannot be read tells us nothing about the citation, and
                # silence about a file is not evidence against the book.
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
    """The node ids *node*'s `key:` links resolve to — dangling links contribute nothing
    (they are `unresolved-relation`'s finding, not this caller's)."""
    out: set[str] = set()
    for value in _bullet_values(node.meta.get(key, "")):
        for _text, href in markdown.extract_refs(value).links:
            target = resolver.resolve(node.path, href)
            if target is not None and target.resolved:
                out.add(target.node_id)
    return out


def _arranges_anything(node) -> bool:
    """Whether *node* declares an arrangement at all, by value rather than by key.

    Every authorable key is scaffolded onto a node as an empty bullet, so `"arrange" in
    node.meta` is true of a node that arranges nothing — the presence of the key says the
    template ran, not that the author wrote one.
    """
    return any(_bullet_values(node.meta.get(key, ""))
               for key in registry.arrange_keys(node.type))


def _alternation_conflict(a: checks.CheckCall, b: checks.CheckCall) -> bool:
    """Whether *a* and *b* are the same check, on the same subject, claiming two different
    expected values — `unspelled-alternation`'s predicate.

    "Same subject" is read from the check's signature, not from how many arguments happen to
    differ. The two calls must share every argument but one, and that one must be a parameter
    the signature marks as an *expectation* — `CheckParam.identifies` is false. An argument
    that names which thing is observed cannot be the difference: two calls differing on it are
    two claims about two different things.

    `http_status(201, path="/api/widgets")` against `http_status(400, path="/api/widgets")`
    differs on `code`, an expectation, and is one route claimed two ways. `count(subject="a",
    equals=1)` against `count(subject="b", equals=1)` differs on `subject`, an identifier, and
    is two counts of two collections — reading it as a conflict tells the author to delete a
    distinction the book made correctly. `removed(subject="a")` / `removed(subject="b")` is
    the same case, and is also excluded by the arity test: a single-argument check has nothing
    left to call the subject once its one argument differs.

    The lookup is a direct index, not a `.get`: `parse_check` returns a `CheckCall` only for a
    name in the vocabulary, so a call reaching here always has a signature, and a default arm
    would be a guess at the two roles standing in for the one fact that decides them.
    """
    if a.name != b.name or len(a.args) < 2 or a.args.keys() != b.args.keys():
        return False
    diffs = [key for key in a.args if a.args[key] != b.args[key]]
    if len(diffs) != 1:
        return False
    spec = checks.CHECK_BY_NAME[a.name]
    return not any(param.name == diffs[0] and param.identifies for param in spec.params)


def _check_self_relation(graph: Graph, f: list[Finding],
                         resolver: links_mod.LinkResolver) -> None:
    """`self-relation` — a relation bullet whose target resolves to the node it is written on.

    A relation is between two things. `- detail: [this page](this-page.md#this-node)` has a
    source and a target that are one node, so there is no second thing for the relation to
    hold between — not an under-specified claim to be filled in later, but an ill-formed one,
    and every reading of it is false: a node is not a detail of itself, and `exclusive-with:`
    pointing home says the node rules itself out.

    Checked over every key in `registry.RELATION_KEYS` rather than per key, because nothing
    about the defect is particular to a key — it is a property of the relation form. A target
    that does not resolve contributes nothing here; that is `unresolved-relation`'s finding.

    It is not inert. A self-reference reads as a satisfied relation everywhere a consumer walks
    one, so a check that excludes a group because some member adjudicates another can be
    cleared by a member adjudicating *itself*. A self-reference both makes a claim that cannot
    be true and launders whatever reads the edge.
    """
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
    """The judgment gap: a succession the book records without adjudicating.

    A conformant node can be entirely true and still leave a reader stranded on the one
    question that bites — *which one do I use?* Structure cannot answer it, so this check
    does not try; it finds the place where the answer is owed and missing. It is a warn:
    naming the successor is the author's judgment, not a rewrite the finding can dictate.

    A second check lived here, `competing-implementations`, and grouped same-type nodes by
    a shared `code:` citation. It is gone, because the grouping could not be evidence: a
    citation is a directed dependency, and that relation is many-to-one in both directions
    — one container has many members, one helper has many callers — so co-citation is
    guaranteed by construction and says nothing about whether two nodes describe one thing.
    Measured across a large reverse-engineered book, all 257 groups it could form were one
    of those two shapes and none was a competition. Rivalry is a claim the book makes with
    `same-as:`, not a number this module can count.
    """
    # `deprecation-without-successor` — a concept that resolves a `deprecates:` but names
    # no successor. Only a *resolved* deprecation is asked: a dangling one is already
    # `unresolved-relation`, and stacking a second finding on the same broken link would
    # have the repair chase two codes for one defect.
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
            # No index: the defect is that the node states no successor at all —
            # a whole-node property, not one `deprecates:` bullet's.
            path=rel, line=node.line, ref=refs_mod.bullet_ref(node.id, "deprecates"),
            suggestion="- prefers: [<winning node>](<path>)   # or a `rule:` stating "
                       "when the deprecated one is still the right call"))


def _check_same_as_symmetry(graph: Graph, f: list[Finding],
                            resolver: links_mod.LinkResolver) -> None:
    """`one-way-same-as` — a `same-as:` claim declared on one side only.

    Sameness is symmetric: if A declares `- same-as: [B](...)`, a reader who arrives at B
    and finds no `same-as:` pointing back at A still sees two separate things, while a
    reader who arrives at A sees one — the exact divergence `same-as:` exists to close, so
    the claim has to be written on both occurrences. A `same-as:` value that does not
    resolve at all is not this check's finding: `same-as:` is in `RELATION_KEYS`, so a
    dangling target is already reported as `unresolved-relation` by the document-wide link
    pass in `_check_ui`; this only judges a claim once it lands on a real node.

    Per-edge, not per-family: a node need only be named back by the specific node that
    named it, not by every other member of a larger `same-as:` group. A reciprocated chain
    (A↔B, B↔C, C↔D) is a legal, cheaper way to write a four-occurrence family and raises
    nothing here.
    """
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
    """`same-as-disagreement` — a `same-as:` family states two different values for one
    normative key.

    `same-as:` says the members are one documented thing, written down more than once —
    `_check_same_as_symmetry` above already makes the relation reciprocated per edge. What
    it does not make true is that the occurrences *agree*: a fact stated twice is a fact
    that can disagree with itself, and nothing before this check ever read the members'
    bullets against each other.

    **Family** is the transitive closure over declared `same-as:` edges alone, undirected —
    mirroring `qa/context.py::_same_as_component`, not `_family_root`. `_family_root`
    collapses three kinds of structure for `_CONTAINER_FANOUT`'s different question (whether
    two citations are one fan-out owner or two): the `same-as:` component, an `extends:`
    base case, and a section node's containing file. The other two are wrong here on
    purpose. `extends:` is specialization, not sameness — a narrower arm's normative claims
    are its own, and treating a base and its specialization as one fact stated twice would
    fire on exactly the case `extends:` exists to express. Containment (`path#anchor`
    collapsing to `path`) puts a file and its own `###` subsections in one group, but they
    own different bullets by construction — a screen and one of its components do not state
    the same claim twice, they state two different claims. So this check's grouping is
    narrower than `_family_root`'s: `same-as:` edges only, nothing else.

    **Scope is `registry.normative_keys(node.type)`** — exactly the keys the QA obligation
    packet mints one obligation per bullet for (`qa/context.py:2868`), unioned over the
    family's member types. `parent:` and `same-as:` are relation keys, not normative ones,
    so they are already outside this set without a hand-maintained exemption list. The
    boundary matters because the packet is about to collapse a family into one obligation
    per key; a key that mints nothing cannot be silently discharged by that collapse, and a
    key this check does not compare is a key the collapse would still discharge safely.

    A `same-as:` target that resolves to something that is not a UI node contributes no
    edge, mirroring `_check_same_as_symmetry`: this judges a claim only once it lands on a
    real node, and a target that never does is `unresolved-relation`'s finding. Without that
    filter an unresolvable id could win `min()` and silently take its whole family with it.

    A member that **omits** a key is not a disagreement — only members that *declare* it
    (a non-empty value list) are compared. Silence is not a contradiction; `same-as:` exists
    precisely so one occurrence can be written cheaply without repeating every claim the
    other already made. Two declaring members disagree when their **sorted** tuple of
    stripped values differs: sorting means a differing *order* is not a disagreement (the
    collapse keeps one member's order and no fact is lost) while a differing *count* or
    *content* is. One finding per (family, key) — a single fact disagreeing with itself is
    one defect, not one per pair and not one per node — anchored on the family root
    (`min()` of the component's ids, the same deterministic representative `_family_root`
    computes for its own `same-as:` stage), naming every declaring member and its values.
    The `ref` carries that root alongside the key, not the key alone: two unrelated families
    disagreeing about `consistency:` are two defects with two remedies, and a shared `ref`
    would collapse them into one worklist item and let one waiver accept both.
    """
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
    """`ungrounded-unspecified` — a resolved-by-design claim with nothing that resolved it.

    An `unspecified:` bullet says a behaviour is deliberately out of contract, which is a
    decision somebody made, and the bullet's authority *is* the record of that decision — a
    decision doc, an acceptance criterion, a stated convention. Without a live citation the
    bullet is indistinguishable from a gap the author decorated, so this one is an error,
    not a warn: the remedy is mechanical — cite what settled it, or delete the bullet.
    """
    for node in graph.ui_nodes:
        # Indexed: a node may state several `unspecified:` bullets and only one be ungrounded.
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


#: How much prose one normative bullet may spend before it stops being one claim. A bullet is
#: minted as a single obligation and proved by a single QA scenario, so length here is not a
#: style question: past this, the bullet is several requirements wearing one id, and the
#: scenario that covers it proves whichever clause the planner happened to read.
MAX_NORMATIVE_PROSE = 700

#: The shapes a bullet takes when it is carrying more than one observation. Length is the crude
#: version of this rule; these are the specific version, and they fire on bullets well under the
#: limit — the endpoint bullet that restates a 400, two 500s, a 409 and a 200 branch is one
#: `does:` that should have been five, and it is a comfortable 300 characters.
#:
#: Read off the *raw* value, not `_prose`: statuses and error names are normally written in
#: backticks, and `_prose` deletes code spans, so measuring the prose would blind this to
#: exactly the signal it exists to find. `_status_codes` below takes that observation the
#: rest of the way — the backticks are not a hint about where to look, they are the notation,
#: so it reads the parser's code spans rather than scanning the whole string for digits.
#: Every key some type reads as a check (`verify:` today). An observation is not a claim, so
#: `unminted-claim` never reads one — wherever it sits, `unknown-bullet` is the rule for a
#: check on a type that declares none.
_OBSERVATION_KEYS: frozenset[str] = frozenset(
    b.key for t in registry.UI_TYPES for b in t.bullet_keys if b.check)
#: Matched with `fullmatch` against one code span, so it needs no boundary assertions: a span
#: reading `500ms` or `v1.400` is not the whole of it and simply does not match.
_STATUS_CODE = re.compile(r"[1-5]\d{2}")
#: `http_status`/`exit_status` are the only checks in the vocabulary whose one required
#: argument is a number a normative bullet already states in prose — a status code on
#: `status:`, an exit code on `exits:` — which is what makes `misbound-status-check`'s
#: reading provable rather than merely suspicious: the check names a code that is absent
#: from the claim it bound to and present, verbatim, on a sibling bullet of the same node.
_STATUS_LIKE_CHECKS = frozenset({"http_status", "exit_status"})
#: The bullet key, per type, that states the same code a status-shaped `verify:` observes —
#: `command`'s `exits:`, `endpoint`/`invocation`'s `status:`. Only these three types declare
#: one (`registry.UI_TYPES`). `errors:` is deliberately not among the values here even though
#: `endpoint` also declares it: `errors:` is prose about the refusal arm, not a closed list of
#: codes, and a real book legitimately writes `http_status(401, …)` in its *text* — "a stale
#: token is rejected the way an anonymous call is (401)" — while binding the actual 401 check
#: correctly elsewhere. Reading `errors:` as a donor would call that a misbinding; it would
#: also make this code a suppression list, quietly cleared by mentioning a number in prose
#: rather than by fixing where the check sits.
_STATUS_DONOR_KEY = {"command": "exits", "endpoint": "status", "invocation": "status"}
#: Read out of code spans on `_STATUS_CODE`'s reasoning, and matched with `search` rather than
#: `fullmatch` because a span naming a failure often qualifies it — `SlugCollisionError (409)`,
#: `errors.ManifestConflict`. The boundary assertions stay for that reason.
_ERROR_NAME = re.compile(r"\b[A-Z][A-Za-z0-9]*(?:Error|Exception|Conflict|Failure|Denied)\b")
#: A semicolon with a real clause after it. `;` inside a code span or ending a bullet is not a
#: joined requirement, so the tail has to carry at least three words to count.
_SEMICOLON_CLAUSE = re.compile(r";\s+(?:\S+\s+){2}\S")
#: "and … and", specifically the clause-joining kind: at least one `and` following a comma or
#: semicolon, plus another anywhere. Bare repeated `and`s are how anyone lists two nouns, and a
#: rule that fires on `- does: creates the page and its slug` is a rule people learn to ignore.
_CLAUSE_AND = re.compile(r"[,;]\s+and\b")
_ANY_AND = re.compile(r"\band\b")


def _code_in_text(code: int, text: str) -> bool:
    """True when *code* appears in *text* as its own number, not as a run inside a longer one.

    A plain substring test would let a check for `2` match inside a claim reading `"200"`.
    Digit-boundary assertions rather than `\\b`, because `\\b` also accepts a boundary
    against a letter and would still pass `2` against `"v2"`.
    """
    return re.search(rf"(?<!\d){code}(?!\d)", text) is not None


def _status_codes(value: str) -> list[str]:
    """The HTTP statuses this bullet names, in order — read out of its code spans only.

    A three-digit number is a status because it is *written as one*: `` `409` ``, in the
    notation this profile uses for every status in the book, which is why the constant above
    reads the raw value rather than the prose. Scanning the whole string for `[1-5]\\d\\d`
    instead made every three-digit number in a sentence a status, and design bullets are full
    of them — `- does: the label renders at font-weight 500 (vs body's 400)` was reported as
    "names 2 status codes (400, 500)", which is not a finding an author can repair by
    splitting the bullet, because the bullet states one thing.

    An unrepairable finding is worse than a missed one here: the two rules that read this
    are warns an author is expected to act on, and a rule that fires where no edit clears it
    is a rule the whole book learns to ignore. A status genuinely written bare in prose is
    the missed case, and `compound-normative-bullet` needs two before it fires at all — so a
    bullet enumerating a branch table has to spell every one of them outside the notation to
    escape, which is not how any of them are written.

    Reading `markdown.all_code_spans` is also what the parse-don't-match rule asks for: the
    inline tokens are already built, and the span boundaries are the parser's, not a
    lookbehind's guess at them.
    """
    return [span for span in markdown.all_code_spans(value) if _STATUS_CODE.fullmatch(span)]


def _error_names(value: str) -> list[str]:
    """The failures this bullet names, in order — out of its code spans, like `_status_codes`.

    Same notation and the same misfire: a symbol is written as code in this profile, and over
    raw prose the pattern read any capitalised word ending in one of its suffixes as a
    failure. `- does: shows the PaymentDenied banner` names a component; `- returns: the
    ConflictResolution the merge settled on` names a value. Both were counted as failures, and
    a bullet mentioning two of them was told to split into two obligations it does not have.
    """
    return [name for span in markdown.all_code_spans(value)
            for name in _ERROR_NAME.findall(span)]


def _outside_parentheses(value: str) -> str:
    """*value* with every parenthesised span removed, nesting included.

    Read by the semicolon signal only, and the scoping is the point. The question that rule
    asks is whether a semicolon joins two independent clauses *of the obligation* — and a
    semicolon inside an aside joins two clauses of the aside, which the planner never has to
    prove separately because the aside is not what is being proved: `- start: the browser
    lacks navigator.share (this journey exercises the fallback menu; the native hand-off is
    out of scope)` states one precondition, and there is no split of it that clears the
    finding short of deleting the sentence that explains the scope.

    `_prose` keeps parentheticals for the *length* measure and is right to — an aside is
    where a second requirement hides, and a long one costs a reader the same either way. A
    requirement hidden there still shows up as a status code, a failure name or a clause-`and`,
    all of which keep reading the whole value. It is the punctuation *inside* the brackets
    that says nothing about how many obligations the bullet carries: in a real book 80 of
    813 `compound-normative-bullet` findings were a semicolon in an aside and nothing else,
    every one of them a citation or a caveat.
    """
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
        # Named here because splitting is not the remedy for every case this signal catches:
        # the second clause is often the first one's reason, which is no observation and has
        # no bullet of its own to go to. The aside is the form `_outside_parentheses` admits.
        reasons.append("a semicolon joins two independent clauses (when the second only "
                       "explains the first, keep it as an aside in parentheses instead)")
    if _CLAUSE_AND.search(value) and len(_ANY_AND.findall(value)) > 1:
        reasons.append("`and` joins clauses more than once")
    return reasons


def _prose(value: str) -> str:
    """A bullet's prose: link text without its href, no code spans, parentheticals kept.

    A bullet is long because it *says* a lot, so `` `code` `` and an href are measured as
    nothing — a cited symbol, route or flag says one thing however many characters it
    spells, and an href is addressing. `markdown.prose_text` reads that off the parser's
    inline tokens.

    Parentheticals stay deliberately. An aside is where a second requirement hides — "(and
    the audit row records the previous value)" is a whole obligation nobody will write a
    scenario for — so discounting them would exempt the very shape this rule is looking for.
    """
    return markdown.prose_text(value)


def _bullet_values(value) -> list[str]:
    """A bullet's raw values — a repeated key parses to a list, a single one to a string.

    Raw on purpose: its one caller scans relation bullets for markdown links, so the value
    must arrive undecorated. `code:`/`verify:` targets go through `refs.code_refs` instead,
    which knows that one bullet may cite several.
    """
    if isinstance(value, list):
        return [str(item) for item in value]
    return [str(value)] if value else []


#: The verbs whose claim is a change of *existence*. Listed rather than stemmed, and listed
#: only in the inflections a normative bullet actually uses to say what the node *does*
#: ("creates a revision"). The bare stems are dropped because half of them are nouns a book
#: is full of — "the issue", "the register", "the archive" — and a rule that fired on those
#: would be waived everywhere and would stop meaning anything where it is right. The finding
#: quotes the verb it matched, so the misfires that remain are visible at a glance.
#:
#: `issues`/`issuing` were members and came out on that same criterion: their object is an
#: *event*, not a subject that exists afterwards. Every one of the seven claims spelling them
#: in a real book governed an HTTP request or a navigation, none a persisted subject — so the
#: remedy the finding printed, `created(subject=…)`, could not be written for any of them.
#: Emission is `emits:`' and `emitted(...)`'s question, and it already has one.
LIFECYCLE_VERBS = frozenset({
    "creates", "creating", "adds", "adding", "registers", "registering",
    "inserts", "inserting", "provisions", "provisioning",
    "deletes", "deleting", "removes", "removing", "revokes", "revoking",
    "archives", "archiving", "purges", "purging",
})

#: The two checks that observe existence as a *change* — the before-read and the after-read,
#: rather than the after-read alone. Declaring either is what clears `unstated-precondition`.
LIFECYCLE_CHECKS = frozenset({"created", "removed"})

#: The bullet keys that state what the node *does*. A lifecycle verb only carries a lifecycle
#: claim when the bullet it sits in is about this node's own action: `semantics:` explains what
#: a value *means* ("otherwise inserts the value verbatim"), `required:` states a *caller's*
#: obligation ("a route that deletes objects must fail closed"), `default:` names a fallback
#: and `consumes:` names an input. None of them is an action to observe either side of, so a
#: finding on one names a remedy the author cannot write.
NON_ACTION_KEYS = frozenset({"semantics", "required", "default", "consumes"})

_WORD = re.compile(r"[a-zA-Z']+")

#: The words that turn the verb *following* them into a claim of non-occurrence, within two
#: tokens: "without deleting", "never removes", "instead of issuing", "rather than creating".
_NEGATORS = frozenset({"no", "not", "never", "without", "instead", "rather", "than", "nor",
                       "neither", "avoids", "avoid", "skips", "skip"})

#: The determiners that negate the verb *before* them: "creates no page id", "writes no draft".
_NEGATIVE_DETERMINERS = frozenset({"no", "none", "nothing", "neither"})

#: A lifecycle-shaped verb can also be one arm of a state-dependent operation. These
#: deliberately require an alternative, another mutation, and a prior-state cue together;
#: any one alone is common in an unconditional creation claim.
_ALTERNATIVE_MARKERS = frozenset({"or", "otherwise"})
#: `restores`/`unsets` are the other arm a lifecycle verb is most often paired against — a
#: scope that puts back what it shadowed, or clears the name when there was nothing to put
#: back. They are mutations that only make sense against a prior state, which is why they
#: belong here and not in `LIFECYCLE_VERBS`: neither one has a `created`/`removed` direction
#: of its own to observe.
_ALTERNATIVE_MUTATIONS = frozenset({
    "strip", "strips", "stripping", "update", "updates", "updating",
    "replace", "replaces", "replacing", "reuse", "reuses", "reusing",
    "restore", "restores", "restoring", "unset", "unsets", "unsetting",
}) | LIFECYCLE_VERBS
_PRIOR_STATE_CUES = frozenset({
    "already", "existing", "exists", "present", "absent", "missing",
})


def _is_one_arm_of_a_verb_alternation(words: list[str], lifecycle_index: int) -> bool:
    """Whether the verb is coordinated directly against another mutation: `restores or removes`.

    The coordination *is* the prior-state condition. A scope that restores the value it
    shadowed, or removes the name when there was nothing to restore, never says "if it was
    already there" — the branch says it, and demanding a separate cue word misses every claim
    written this way. `removed(subject=…)` then asserts one arm of a choice, which is a check
    that fails whenever the other arm runs.

    Adjacency across the marker is what keeps this from being the sentence-wide test the
    constants above reject. `creates the revision, then updates the manifest row it points at
    or the index that lists it` carries a marker and a second mutation too, but they are not
    two arms of one choice and the creation is unconditional — the finding belongs there.
    """
    pairs = zip(words, words[1:])
    return any(
        (first in _ALTERNATIVE_MUTATIONS and second in _ALTERNATIVE_MARKERS)  # `restores or …`
        or (first in _ALTERNATIVE_MARKERS and second in _ALTERNATIVE_MUTATIONS)  # `… or restores`
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
    """The lifecycle verb this bullet uses, or "" — the word a finding has to quote.

    A verb whose negation is *local to it* states the opposite of a lifecycle change, and
    there is no edit that clears the finding: `created(subject=…)` asserts the thing the
    claim says does not happen, and the `absent(...)`/`unchanged(...)` the author already
    wrote is the complete observation. So the negated verb is not the claim's verb.

    The scoping is the whole correctness of this. A sentence-wide negation test — "any
    negator anywhere" — is measurably wrong: `creates a new claims map and copies every
    existing key … *without* mutating the account's current claims` is a real creation, and
    `an empty 204 No Content *after deleting* the project` is a real deletion. In a real book
    23 claims carried a negator somewhere and only 10 carried one governing the verb.

    This is token work over an English sentence, not a parse, and it does not pretend to be
    one: there is no English parser here and a `warn` does not justify adding one. What it
    buys over the set-membership test it replaces is that the answer is computed from the
    verb's own neighbourhood rather than from the sentence containing a word.
    """
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


#: The modal and outcome verbs that make a sentence read as a requirement rather than a
#: description. Narrow on purpose: "returns" and "rejects" are how a claim about behaviour is
#: written in this profile; "is", "has" and "shows" are how a description is, and a rule that
#: fired on those would fire on every `meaning:` in the book.
_MODAL = re.compile(r"\b(must|shall|never|always|rejects?|returns?|exits? with)\b", re.I)


def _sounds_normative(value: str) -> str:
    """Why this bullet reads like a claim — one short phrase naming the signal — or "".

    The same three readers `compound-normative-bullet` and the lifecycle rule use, plus the
    modal verbs: a status code, an error name, a lifecycle verb, a `must`/`returns`/`rejects`.
    Read off the raw value for the reason `_STATUS_CODE` gives — codes and names live in
    backticks, and `_prose` would delete exactly the evidence this is looking for.

    The status and failure halves go through `_status_codes` / `_error_names`, so a design
    bullet's `font-weight 500` and a `PaymentDenied` banner no longer mint a claim nobody can
    bind an obligation to. This rule fires on a *single* signal, which made it the louder of
    the two misfires.
    """
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


#: A bare, word-bounded `None`/`True`/`False` in a `matches=` pattern — evidence the pattern was
#: authored against `str(value)`/`repr(value)` rather than the JSON encoding `_matchable` (in
#: `ostler/qa/harness/ostler_qa.py`) actually matches against: `json.dumps` never emits these
#: three spellings, so a pattern that names one can only ever fail against a live document and
#: was written against something else. Deliberately narrower than every repr/JSON difference —
#: a bare `'` inside a pattern is not tested here, because a string-typed field can legitimately
#: contain one (an apostrophe in prose, a quoted key in a JSON-shaped string value), so that
#: shape is authoring judgment this check does not try to automate.
_REPR_LITERAL = re.compile(r"\b(?:None|True|False)\b")


def _matches_repr_spelled(pattern: str) -> bool:
    """Whether *pattern*, a `json_path(matches=...)` value, is spelled against Python `repr`."""
    return bool(_REPR_LITERAL.search(pattern))


def _rubber_stamp(call: checks.CheckCall) -> str:
    """Why this call would stay green against the defect its bullet describes, or "".

    Read off the vocabulary rather than second-guessing it: `CheckSpec.excludes` already
    names the defect a weaker assertion admits, and that sentence is the finding — the
    field is the test of whether a check earns a place in the vocabulary at all, so a
    check it cannot describe has no business being judged here.

    Three legal spellings reach this. A 2xx `http_status` naming neither route nor title:
    its one required argument is satisfied by any working request, so it observes only
    that the scenario got this far. `json_path(absent=false)`, the one way left to spell
    presence now that `checks.bind` refuses a `json_path` carrying no comparison at all.
    And a `json_path(matches=...)` whose pattern is loose enough to accept
    `sensitivity._OTHER` — `matches_admits_other` decides that the same way
    `sensitivity._plan` decides whether to bother perturbing the value at all, so a claim
    never reads as sensitive here and insensitive there. Every other check compares
    something the moment its arguments are bound.
    """
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
    """The resolved node/edge dump, or None when it will not build.

    A graph that cannot be assembled is already reported by the checks above, so the UI-profile
    checks stay silent rather than reporting the same breakage in a second vocabulary.
    """
    try:
        return graph_mod.build(graph, resolver=resolver)
    except (OSError, ValueError, RuntimeError, KeyError):
        return None


def _check_reachability(data: dict, f: list[Finding]) -> None:
    """Every screen must be reachable by clicking from the surface's root.

    An unreachable screen is a hole in the book, not a quirk of the app: if no documented path
    leads there, a reader cannot get there and neither can a walk. The remedy is a ``leads-to:``
    on whatever component navigates there — or an ``entry:`` stating the route, when the screen
    really is entered from outside (an emailed deep link, an OAuth callback).

    The root is the screen whose ``route:`` is the path the surface's server serves at
    (``entry-url:`` on the ``walkthrough: true`` server, else ``/``). It is the one seed the
    check trusts unconditionally, because it is the one address the walk opens by construction.
    An ``entry:`` seeds too, but only when its value is a route: prose there is a claim about the
    outside world an edge check cannot verify, and a book where every screen makes that claim has
    no navigation in it and passes. That is exactly the book this check exists to reject.

    Run per surface, because the root is surface-scoped: a screen in ``web`` is not made
    reachable by a root declared in ``legacy``.
    """
    surfaces = {n["surface"] for n in data["nodes"] if n["type"] == "screen"}
    for surface in sorted(s for s in surfaces if s):
        try:
            driver = reach.surface_driver(data, surface)
        except reach.UnsettledSurfaceDriver:
            # Already reported by `_check_conflicting_surface_driver` or
            # `_check_undeclared_walkthrough_runbook`; not this check's finding to
            # duplicate. Treat as undeclared so the rest of this surface's
            # screens still get checked against the grammar they have always used.
            driver = None
        scoped = graph_mod.subset(data, surface)
        screens = reach.screens_of(scoped)
        if not screens:
            continue
        unreachable, root, _seeds, reason = reach.unreachable_screens(
            scoped, driver, surface=surface)
        if root is None:
            # No root means the question is unanswerable, which is not the same as a pass. Warn
            # rather than error: flooding the surface with one error per screen would bury the
            # one fact that matters, which is the root the book has not stated.
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
                if reason == reach.UNSETTLED_LAUNCH_SCREEN:
                    reason_note = "has an unsettled `launch-screen:` on its runbook"
                elif reason == reach.LAUNCH_SCREEN_NOT_SCREEN:
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


def _check_conflicting_surface_driver(data: dict, f: list[Finding]) -> None:
    """Every runbook marked `walkthrough: true` for one surface must agree with every other
    marked runbook on its `driver:`.

    `reach.surface_driver` refuses to pick between two *marked* runbooks that disagree —
    correctly, because its two callers each want a *grammar*, and a grammar has exactly one
    answer per surface or none. `_check_bullet_value_kinds`'s `_driver_for` picks the
    value-kind grammar a node's bullets are held to; `_check_reachability` picks the route
    grammar reachability is computed in, and its own docstring says the root is surface-scoped
    because "a screen in `web` is not made reachable by a root declared in `legacy`". Two
    marked drivers for one surface makes both questions unanswerable, so both readers catch
    `reach.ConflictingSurfaceDriver` and degrade to an undeclared driver rather than guess —
    which is the right thing for a grammar-picker to do, but it means neither of them, nor
    any other reader of `surface_driver`, ever tells the author the book disagrees with
    itself. This check exists solely to be the one that does.

    Several *unmarked* runbooks naming the same surface with different `driver:` values is not
    this check's business — that is normal (a lint runbook, a browser runbook and an IaC
    runbook can all correctly name the same surface) and is `_check_undeclared_walkthrough_runbook`'s
    concern instead. Both checkers call `reach.surface_driver` and must each ignore the other's
    exception rather than let it escape unhandled.

    Run once per surface rather than once per runbook: two marked runbooks disagreeing about
    one surface is one defect with one remedy (settle which driver is right), not one finding
    per runbook naming it.
    """
    surfaces = sorted({n["surface"] for n in data["nodes"] if n.get("surface")})
    for surface in surfaces:
        try:
            reach.surface_driver(data, surface)
        except reach.ConflictingSurfaceDriver as exc:
            named = "; ".join(f"{node} says `driver: {driver}`" for node, driver in exc.drivers)
            f.append(Finding(
                "error", "conflicting-surface-driver",
                f"{surface}: runbooks marked `walkthrough: true` disagree about this surface's "
                f"`driver:` — {named} — every check that needs a driver for this surface treats "
                f"it as undeclared until they agree",
                ref=surface,
                related=sorted(node for node, _driver in exc.drivers)))
        except reach.UndeclaredWalkthroughRunbook:
            pass


def _check_undeclared_walkthrough_runbook(data: dict, f: list[Finding]) -> None:
    """Several runbooks naming one surface with different `driver:` values must mark exactly
    one of them `walkthrough: true`.

    A runbook's `driver:` states what that runbook drives, not which runbook is how the
    surface is exercised — a real surface routinely has several correct runbooks (a lint
    runbook, a browser runbook, an IaC runbook), and `surfaces:` is the only join recording
    which code each one operates on. So the remedy is to mark the one that stands for the
    surface `walkthrough: true`, never to strip `surfaces:` from the others — that bullet is a
    true claim about what code each runbook covers, and deleting it to silence this finding
    destroys that claim rather than resolving the ambiguity it flags.

    `reach.surface_driver` raises `reach.UndeclaredWalkthroughRunbook` for exactly this shape;
    this check is the one that turns the refusal into a finding, the same way
    `_check_conflicting_surface_driver` does for its own exception. Each checker calls
    `surface_driver` and must ignore the other's exception rather than let it escape.

    Run once per surface: several unmarked runbooks disagreeing about one surface is one
    defect with one remedy (mark the walkthrough runbook), not one finding per runbook naming
    it.
    """
    surfaces = sorted({n["surface"] for n in data["nodes"] if n.get("surface")})
    for surface in surfaces:
        try:
            reach.surface_driver(data, surface)
        except reach.UndeclaredWalkthroughRunbook as exc:
            f.append(Finding(
                "error", "undeclared-walkthrough-runbook",
                f"{surface}: several runbooks cover this surface with different `driver:` "
                f"values and none is marked `walkthrough: true` — mark the one that is how "
                f"this surface is exercised, keeping `surfaces:` on the others",
                ref=surface,
                related=sorted(node for node, _driver in exc.drivers)))
        except reach.ConflictingSurfaceDriver:
            pass


def _check_conflicting_entry_origin(data: dict, f: list[Finding]) -> None:
    """Every source stating a surface's `entry-url:` must agree with every other on its origin.

    `reach.entry_origin` refuses to pick between a `server` node and a `runbook` that name
    different `scheme://host[:port]` for one surface, and its sole reader — `qa context` —
    catches the refusal, stores `entryUrl: None` and writes the exception's text into
    `entryUrlError`. Nothing in the repo reads `entryUrlError`, so the report goes nowhere:
    the degrade is right, but until this check existed no reader told the author the book
    states the surface's address twice and disagrees with itself.

    Unlike `conflicting-surface-driver`, the degrade is not the end of it. A surface with no
    `entryUrl` falls back to the operator's `--base-url`, which is an answer for a book that
    states no address, not an adjudication between two the book does state — so the compiler
    now gaps `conflicting-entry-origin` for that surface instead of falling back, and this
    finding is what tells the author which two sources to settle.

    Run once per surface, for the same reason the driver check is: two sources disagreeing
    about one surface is one defect with one remedy, not one finding per source.
    """
    surfaces = sorted({n["surface"] for n in data["nodes"] if n.get("surface")})
    for surface in surfaces:
        try:
            reach.entry_origin(data, surface)
        except reach.ConflictingEntryOrigin as exc:
            named = "; ".join(f"{node} says `entry-url:` on {origin}" for node, origin in exc.origins)
            f.append(Finding(
                "error", "conflicting-entry-origin",
                f"{surface}: this surface's address is stated more than once and the "
                f"statements disagree — {named} — a service has one address, so QA cannot "
                f"pick between them and every obligation on this surface is gapped",
                ref=surface,
                related=sorted(node for node, _origin in exc.origins)))


def _check_unknown_driver(data: dict, f: list[Finding]) -> None:
    """A runbook's `driver:` must be one of the seven values `drivers.DRIVERS` declares.

    Nothing else in this file ever asks whether the string a book wrote there is a *word this
    vocabulary has*. `routes.ROUTE_GRAMMAR` and `routes.SURFACE_PERFORMABLE_TYPES` are both
    keyed by the seven legal spellings and both default an unrecognized key to "nothing is
    known" rather than to a rejection — `_DEFAULT_ROUTE_GRAMMAR` gives a misspelling the
    benefit of the doubt on a grammar it never claimed, and `performable_surface_types`
    answers an unrecognized driver with an empty set. An empty performable set is exactly
    what `_check_runbook_driver_surface` reads as "nothing to hold this driver to" and skips
    on — its own docstring says so. So `driver: htttp` does not merely go unvalidated: it is
    *more* permissive than `driver: http` typed correctly, because it silently opts the node
    out of the one check that would have caught a browser driver pointed at a server-only
    surface, and out of `reach.surface_driver`'s route derivation besides. A vocabulary
    nobody can check is a vocabulary the book is not held to, and a typo is currently the
    cheapest way to leave it.

    An absent or empty `driver:` is not this check's business — `missing-required-bullet`
    already owns that book, the same boundary `_check_runbook_driver_surface` draws for the
    same reason: with no driver there is nothing here to validate.

    The suggestion lists the vocabulary rather than guessing a correction. A closest-spelling
    guess is itself an unverified claim about what the author meant, and a wrong guess taken
    on faith is the same defect this check exists to catch, one level up.
    """
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
    """A runbook's `driver:` must be able to perform against at least one of its `surfaces:`.

    `driver:` says who carries out the steps; `surfaces:` says what is stood up — and until
    `routes.SURFACE_PERFORMABLE_TYPES` existed, nothing read the two against each other, so a
    book scaffolded from a template could drift: three of the corpus's seven runbooks stayed at
    `driver: web` over a `surfaces:` list whose only entry was a `type: server` node, a browser
    driver pointed at something with no screen in it.

    Fires only when the driver's performable set is non-empty (`performable_surface_types`) and
    **none** of the runbook's resolved surfaces has a type in it. A driver with an empty
    performable set — `iac`, `artifact`, `none`, or an unrecognized spelling — is skipped: the
    table has nothing to hold it to, not a green light for every surface. An unrecognized
    spelling is not silently let through by that skip, though — `_check_unknown_driver` reports
    it separately, as `unknown-driver`, which is the finding that names the typo this check
    can only decline to have an opinion about. A runbook with no
    `driver:` at all is skipped too: `missing-required-bullet` already owns that book, and with
    no driver there is nothing to hold the surfaces to. A runbook that declares a driver and no
    `surfaces:` at all does fire — it names a performer and then names nothing for it to
    perform against, which is this same defect stated by omission rather than by mismatch.

    Surface links are read the same way `reach.surface_driver` reads them — the runbook node's
    own resolved out-edges, filtered to `surfaces:` — rather than re-walking the raw markdown.
    """
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
    """The book must say how this system comes up, and say it in a shape QA can run.

    A repo with no `runbook` node has no declared stack, and the way that used to surface was
    a QA run that passed against nothing: the bring-up found no manifest, reported "nothing to
    bring up", and the lane routed that identically to a healthy stack. Reporting it here moves
    the discovery to author time, where the remedy is one node instead of a repair loop.

    Error, not warn, for the missing case: this is the doctor gate the live-audit lane relies
    on to keep it from ever reaching a QA run with nothing to run against. A repo that
    documents a served surface and never says how it starts is not a style nit to note and
    move past — it is the one finding that must stop `ostler doctor` clean, because the flow's
    own "blocked" path is only a defensive backstop, not the intended gate. A book that
    documents a library, a CLI, or a surface nobody serves is exempt from this branch entirely
    (`has_served_surface` is false for it), so a library-only book never trips this check. The
    shape checks below are errors for the same reason: a runbook that exists and cannot be run
    is a promise the lane will believe.

    Only *stack* runbooks are held to that shape. `runbook` is the general ops type — "preview
    the plan", "rotate the keys" — and a procedure that starts nothing is not an incomplete
    stack, it is a different document. `is_stack_runbook` draws that line, and a book carrying
    only procedures still gets the missing-stack error.
    """
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
            # A procedure runbook: its steps and its environment are still checked above and
            # below, but nothing here is supposed to start a system.
            _check_runbook_environment(graph, node, rel, f)
            continue

        if not services:
            f.append(Finding("error", "runbook-incomplete",
                             f"{rel}: declares a launch but has no `kind: service` step — "
                             f"nothing here starts the system",
                             path=rel, line=node.line, ref=node.id,
                             suggestion="### start\n- kind: service\n- run: <bring-up command>"))
        elif len(services) > 1:
            # The reader takes the first and keeps going, so this is a book to repair rather
            # than a run to stop; it is an error because which one launched is otherwise luck.
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
    """A `local-only: true` environment must name only local services.

    The bullet exists so a book can say "this recipe drops databases and reseeds fixtures; it
    is for a laptop". Honouring it is cheap here and impossible later — by the time the recipe
    runs it is already talking to whatever it was pointed at.

    The evidence is the `services:` hosts, not the `selector:`: a selector is free prose (an
    env-var assignment, a profile name, a sentence), so reading intent out of it would both
    miss `prod-eu` and libel `GROOM_BIND=127.0.0.1`. A host is a fact.
    """
    for _text, href, _line in node.links:
        # Through `resolve_doc_ref`, because a runbook cites its environment the way every
        # other doc cites: relative to itself. A raw `href` lookup only ever finds the
        # citation that happened to be written as a node id.
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


#: The bullets a `step` node shells (`ensure_stack`, `book_fixtures`) rather than parses —
#: see `_check_step_command_bullets`.
_STEP_COMMAND_KEYS: tuple[str, ...] = ("run", "health")


def _check_step_command_bullets(step: UINode, rel: str, f: list[Finding]) -> None:
    """A `run:`/`health:` bullet is shelled, never parsed — a check expression there is wrong.

    `ensure_stack` and `book_fixtures` both hand these bullets to `bash -c` verbatim
    (`runbook._step_command`, `runbook._from_runbook`'s health gate); neither reads
    `verify:`'s grammar. A value that nonetheless *parses* as a check call
    (`checks.is_check_expression`) was written for `verify:` and put on the wrong key — an
    author reaching for `http_status(200, path="/healthz")` here meant a check, not a
    command, and bash would only ever answer with a syntax error, one stage after this
    stage already reported green. `error`, not `warn`: the whole point is to replace that
    bring-up-time bash failure with a doctor finding an author sees before the stack runs at
    all — the same bar `undeclared-check-locator` holds for a locator argument.
    """
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
    """A runbook step's `working-directory: scenario:` names a frame that does not exist yet.

    The token means "this scenario's own directory" (`runbook.SCENARIO_FRAME_TOKEN`), which
    is only meaningful on a *fixture* step — a fixture runs inside a scenario. A runbook step
    runs at bring-up, before any scenario has been created, so the same token here names
    nothing: `error`, the same bar `check-expression-as-command` holds, so an author sees
    this before bring-up runs into it.
    """
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


#: Hosts a `local-only: true` environment may name. `*.localhost` and `*.local` resolve on the
#: machine too, so they are matched by suffix rather than listed.
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


#: Words a `states:` bullet uses to say the control cannot be acted on. Matched as whole
#: words so `disabled-until-valid` counts and `disabledate` does not. Spelled out rather
#: than inferred from prose: the finding below is only ever as narrow as this list, and a
#: list that grows by guesswork starts reporting states nobody claimed anything about.
_UNAVAILABLE_WORDS = frozenset({
    "disabled", "greyed", "grayed", "readonly", "read-only", "inactive", "unclickable",
})

#: The two checks that observe whether a user can act on a control. Either one discharges
#: an availability `states:` bullet: a book may say the control is usable in this state or
#: unusable in it, and both are observations of the same question.
_AVAILABILITY_CHECKS = frozenset({"actionable", "inert"})


def _availability_observed(graph: Graph) -> set[str]:
    """Every node id some `actionable(...)`/`inert(...)` call in this book points at.

    Graph-wide rather than per-node, because the check that observes a component is
    routinely not written on it: a screen or an interaction is what carries the `verify:`
    bullet, and the component is what the `locator=` names. Collecting the targets first is
    what makes the finding below say "nothing in this book observes it" rather than
    "this node does not observe itself".
    """
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
    """A `states:` bullet saying the control cannot be used, with nothing observing it.

    `states:` mints an obligation, and until `actionable`/`inert` existed an availability
    state had no member of the vocabulary that could observe it — `visible` passes on a
    greyed-out button, which is on the screen and reads the right label. So the book's own
    guidance was to leave the fact documented and unverified, and that guidance is now
    wrong: the claim is about what the user can do, and there is a check that asks exactly
    that. A `warn` rather than an `error` because the remedy is authoring a check against a
    real anchor, not a mechanical rewrite of the bullet in place.
    """
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
    """One bullet, read exactly as the runbook reader reads it, folded for comparison.

    Shared rather than re-implemented so the doctor can never bless a spelling the reader
    then refuses — `` - reuse: `never` `` has to be the same value to both.
    """
    return runbook_mod.bullet_value(meta, key).lower()


def _rel_path(graph: Graph, node) -> str:
    try:
        return node.path.resolve().relative_to(graph.root.resolve()).as_posix()
    except (ValueError, OSError):
        return node.path.as_posix()


def _check_locators(data: dict, f: list[Finding]) -> None:
    """Every documented control must map to exactly one Playwright locator.

    ``role:``/``name:`` being required gets the forward half for free — every component yields a
    locator. The reverse half needs checking: two controls on one screen sharing a role and an
    accessible name yield a locator that matches both, which Playwright rejects at runtime as a
    strict-mode violation. Caught here, it is a doc defect with an obvious remedy; caught in CI it
    is an intermittent test failure nobody traces back to the book.

    ``unnamed-interactive`` is the accessibility half of the same fact. A button with no accessible
    name is one a screen reader announces as "button" and a test cannot address at all — the same
    omission, failing two audiences.
    """
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
                # The ref names the *collision*, not the node: one component reached from
                # several screens collides once per screen, and every one of those used to
                # arrive at `ref=node_id`. See `refs.collision_ref`.
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

    # The repeat grammar (`one-per:`) is opt-in per node; all four checks below are inert on a
    # book that never declares it.
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
    """A structural component says where it sits, and says it in a form QA can check.

    `role:` and `name:` are the accessibility contract, and a scenario asserting on them
    passes whether the page lays the component out across the window or crushes it into a
    column against one margin — that defect reached a green run, which is why the bullet
    exists. It is only asked of the roles that carry a page: a button's placement is brittle
    and proves nothing about the layout.
    """
    values = _bullet_values(node.meta.get("placement", ""))
    role = str(node.meta.get("role", "")).strip()
    if not values:
        if role in placement_mod.PLACED_ROLES:
            f.append(Finding(
                "error", "missing-placement",
                f"{node.id}: role={role} carries the page but no `placement:` says where it "
                f"sits — a role+name assertion passes on a component crushed into a sliver",
                # No index: the bullet is absent, so the ref names the key to add.
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
    """A component's `selector:` names a form nothing in this tree can resolve.

    `placement_mod.is_addressable` accepts two different kinds of value, for two different
    reasons, and this check only fires outside both. One is a web-DOM form the render census
    itself mints (`#id`, `tag.class:nth(i)`) or matches by role — anything else in that
    grammar reads `missing` on every render regardless of what actually rendered, which is
    the census-specific defect the message below names. The other is a self-identifying
    `scheme=value` address (`testID=widget-table`): the census never reads it — there is no
    web render to scan — but it is not a fabricated locator either, it is the real,
    documented address a non-web driver (React Native's `testID`, Maestro's `id:`) resolves
    by. A value that is neither — most often an attribute-value or boolean-attribute
    predicate typed as if it were CSS, or a scheme this vocabulary does not recognize — names
    nothing at all, which is what this finding reports.
    """
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
    """Every `arrange:` bullet is an act this repo can perform, on a control this book declares.

    The sibling of the `unparsed-check` loop, and deliberately not folded into it: the two keys
    share a call *grammar* (`checks.parse_call`) and not a vocabulary, so `fill` is a name under
    one and nothing under the other. Sharing the parse is what keeps `f(a=1,)` legal or illegal
    on both at once; sharing the loop would have made an unknown check and an unknown act the
    same finding, and the repair for each names a different list of names.
    """
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
            # `undeclared-check-locator`'s reason, one key over: an act pointed at a raw
            # selector goes green against an element the book never declared, so renaming that
            # element breaks the run and leaves the book undisturbed. A separate code because
            # the two carry different repairs — a check observes a control, an act operates one,
            # and the anchor an author reaches for is not the same anchor.
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
    """The UI-profile per-file and per-node checks.

    A caller that also resolves the same links — ``doctor.run``, which builds the graph right
    after — passes its ``resolver`` in, so the anchors of a link target are computed once for the
    run instead of once per resolver. Left None, these checks own a resolver for their own
    lifetime, which is what a standalone caller wants.
    """
    _check_availability_states(graph, f)
    if resolver is None:
        resolver = links_mod.LinkResolver(graph)
    froot = graph.doc_roots.get("features")
    if froot is not None and froot.is_dir():
        for path in sorted(froot.rglob("*.md")):
            if path.is_file() and path.name not in registry.RESERVED_FILES:
                _check_ui_file(graph, path, f)
    _check_code_grounding(graph, f, checkouts)

    # required-bullet checks stay per-node — they need the node's declared type + schema.
    by_id = {n.id: n for n in graph.ui_nodes}
    for node in graph.ui_nodes:
        uitype = registry.ui_type(node.type)
        if uitype is None:
            continue
        rel = node.path.relative_to(graph.root).as_posix()
        # An `interaction`/`invocation` arm that `extends:` a same-type base case (D51) inherits
        # the base's control identity in `qa/context.py` — `on:`/`trigger:`/`role:`/`name:`/
        # `keyboard:` are exempt from this node's own required-bullet check because the arm
        # never has to restate what it inherits, and `unresolved-relation` already covers an
        # `extends:` link that does not resolve at all.
        extends_ok = False
        if node.type in ("interaction", "invocation"):
            targets = _resolved_targets(node, "extends", resolver)
            extends_ok = any(by_id[t].type == node.type for t in targets if t in by_id)
            # A target that resolves but is not the same node type is not a dangling link —
            # `unresolved-relation` already catches a missing one — it is the arm pointing at
            # the wrong kind of thing, and `qa/context.py` cannot inherit a control identity
            # from it either, so it is its own finding rather than silently falling through
            # to `missing-required-bullet` on every inherited key.
            for target_id in sorted(targets):
                target = by_id.get(target_id)
                if target is not None and target.type != node.type:
                    f.append(Finding(
                        "error", "extends-type-mismatch",
                        f"{node.id}: `extends:` names {target_id} ({target.type}), not "
                        f"another {node.type} — an arm can only extend its own node type",
                        path=rel, line=node.line, ref=refs_mod.bullet_ref(node.id, "extends"),
                        suggestion=f"- extends: [{node.type} base case](#anchor)"))
            # An arm inherits the base case's *identity* and none of its arrangements — an
            # arrangement exists to make a `when:` true, and an extending arm either restates
            # `when:` (a different condition, so the base's acts would arrange the state this
            # arm says is false) or inherits it (the same condition, but `qa/context.py` reads
            # acts from the arm's own `bulletOrder`, so nothing carries them over). Either way
            # an arm whose base arranges and which arranges nothing itself has no reachable
            # precondition, and the compiler withholds it as `unarranged-interaction-
            # precondition` — a refusal only a compiled plan surfaces. Say it here, off the
            # book alone, where the author is still writing the arm.
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

            # The mechanical, cross-validated signal that a node claims two outcomes at once:
            # two `verify:` bullets calling the same check with the same identifying argument
            # (a `path=`, a `locator=`, a `subject=`) but a different value for whichever
            # argument is left — `http_status(201, path="/api/widgets")` beside
            # `http_status(400, path="/api/widgets")` is not one scenario's two checks, it is
            # two scenarios' worth of check sharing a node. `≥2 does: bullets` was tried and
            # dropped — it fires on most of the real corpus and teaches nothing — so this reads
            # the checks themselves rather than the prose above them.
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
            # One role, one accessible name: a second bullet under either key does not give
            # the control two identities, it leaves the book unable to say which one it has.
            # Reported here as the book's own defect. `collisions` skips the node meanwhile,
            # because grouping on the first of two names would raise `ambiguous-locator` — a
            # claim about the code — off a malformation the book alone explains.
            for key in loc_mod.malformed_identity({"bullets": node.meta}):
                f.append(Finding(
                    "error", "duplicate-bullet",
                    f"{node.id}: `{key}:` is stated {len(node.meta[key])} times — a component "
                    f"has one {key}, so the node cannot say which it is; keep the bullet the "
                    f"source supports and drop the rest",
                    # No index: the defect *is* that a single-valued key was stated N
                    # times, so the finding is about the set, not one occurrence of it.
                    path=rel, line=node.line, ref=refs_mod.bullet_ref(node.id, key),
                    suggestion=f"- {key}: <the one value the source renders>"))

        # A profile key on a type that does not declare it is inert: a `verify:` on a concept is
        # read by nobody, a `does:` on a component mints nothing, a `code:` on a field is never
        # grounded — while the author, who knows what the key does elsewhere, believes otherwise.
        # A `warn`, because the remedy is a judgment: the claim belongs under a key this type
        # mints from, the observation belongs on the node that states the claim, or the bullet
        # wanted to be prose. A key no type declares is left alone — it is the author's own
        # vocabulary (`meaning:`, `constraints:`), and a claim hiding under one is
        # `unminted-claim`'s to find, not a spelling to police.
        for key in registry.unknown_bullet_keys(node.type, node.meta):
            minted = ", ".join(f"`{k}:`" for k in registry.NORMATIVE_KEYS_BY_TYPE.get(
                node.type, ()))
            f.append(Finding(
                "warn", "unknown-bullet",
                f"{node.id}: `{key}:` is not a bullet {node.type} declares, so here it is "
                f"inert — nothing orders it, grades it, grounds it or binds a `verify:` "
                f"to it; move the claim under a key {node.type} mints from "
                f"({minted or 'none — this type states no claims'}) or into prose",
                # No index: an unknown key is inert in every one of its occurrences.
                path=rel, line=node.line, ref=refs_mod.bullet_ref(node.id, key)))

        normative = 0
        for key in registry.normative_keys(node.type):
            # `index` is the 1-based occurrence of *this key* — the number
            # `registry.normative_claims` returns and `qa context` mints obligation ids from,
            # so a ref here and an obligation id name the same claim. A node states `does:` a
            # dozen times; without it every one of those bullets shares one address, the
            # repair drain collapses them into one worklist row, and the turn reads whichever
            # sibling it lands on. See `refs.bullet_ref`.
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
                # A `warn`, alone among the UI checks, and for the reason the header states in
                # reverse: there is no deterministic remedy. Splitting a bullet is authoring
                # judgment — which branch is its own claim, what each one is called — so a
                # strict `doctor` cannot converge on it the way it converges on `fmt`. What the
                # rule buys is that the judgment gets made once, at the node, instead of once
                # per story that touches it for as long as the node exists.
                # Not an error: a book written before subjects existed has none anywhere, and a
                # finding it cannot clear in one sitting is one an author learns to page past.
                # What the subject buys is the join — two nodes are known to be about the same
                # record only when both name it, and prose never says so, because every
                # persistence bullet in a real book is a unique sentence. Without one, the node
                # is invisible to the one-hop rule that would have owed it live evidence when
                # the record changed under it.
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

        # The other half of `undeclared-obligation`: a bullet that reads like a claim — a status
        # code, an error name, a lifecycle verb, a `must` — under a key this type never grades
        # (`meaning:`, `behaviour:`, an `errors:` on a concept). Nothing will ever ask a plan to
        # prove it, and the author, who wrote a requirement, believes something does. Asked of
        # every node, not only one that mints nothing: minting is a property of a bullet, not of
        # the node, so a `persistence:` bullet already in QA's sight says nothing about whether
        # this node's `errors:` bullet is — a node-wide flag would let the one satisfied bullet
        # vouch for its siblings. The type's own normative and declared keys are exempt by
        # construction, so what is left examined is only the author's free vocabulary. Bullets
        # only — `UINode` carries no prose, so a paragraph is not read.
        # A `warn`, for the usual reason: where the claim belongs is the author's call.
        instrumented = (frozenset(registry.normative_keys(node.type))
                        | frozenset(registry.RELATION_KEYS)
                        | frozenset(registry.check_keys(node.type))
                        | frozenset(registry.arrange_keys(node.type))
                        | _OBSERVATION_KEYS)
        # Every key the type declares is exempt, the descriptive ones included: `backing:`
        # on an environment or `trigger:` on an interaction holds description because the
        # profile says so. What is left is the author's own vocabulary and the keys of an
        # untyped section — the places a requirement hides with nothing reading it.
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
                # No index: the `break` below makes this deliberately one finding per
                # node — the remedy is a decision about the node's vocabulary, not a
                # rewrite of one bullet.
                path=rel, line=node.line, ref=refs_mod.bullet_ref(node.id, key)))
            break

        check_keys = registry.check_keys(node.type)
        declared = 0
        for key in check_keys:
            # Indexed for `refs.bullet_ref`'s reason, and acutely here: `verify:` is the
            # most-repeated key in a real book — one node in this repo carries twelve
            # unparseable ones, which without an index arrive as twelve copies of one address.
            for index, value in enumerate(_bullet_values(node.meta.get(key, "")), 1):
                # Counted before it is parsed: a node that declared and got the call wrong is
                # already told so by `unparsed-check`, and telling it twice buys the author
                # nothing and costs a second thing to waive.
                declared += 1
                parsed = checks.parse_check(value)
                if isinstance(parsed, checks.Refusal):
                    said: dict[str, Any] = dict(
                        message=f"{node.id}: `{key}:{index}` ({value}) {parsed.message}",
                        path=rel, line=node.line,
                        ref=refs_mod.bullet_ref(node.id, key, index),
                        # Composed by the refusal, because the refusal is what classified the
                        # value: a test reference is suggested under `tests:`, a mis-called
                        # check under its own signature, and only a value whose check nobody
                        # can name gets the whole vocabulary. Re-deriving any of that here is
                        # how the message and the suggestion came to contradict each other.
                        suggestion=parsed.bullet(key))
                    if parsed.kind == "misfiled-test-ref":
                        f.append(Finding("error", "misfiled-test-ref", **said,
                                         fixable=(key == "verify"
                                                  and "tests" in registry.declared_keys(
                                                      node.type)
                                                  and checks.relocatable_to_tests(value))))
                    else:
                        f.append(Finding("error", "unparsed-check", **said))
                    continue
                # A locator argument is a reference into the book, not a string the driver
                # happens to accept: written as free text it type-checks, runs, and goes green
                # against an element the book has never heard of, so renaming that element
                # breaks the run and leaves the book undisturbed — the staleness lands on the
                # wrong artifact. Resolved here for the reason `dangling-link` is: an
                # unresolvable reference is visible in the book alone, before any driver runs.
                # An `error`, and mechanical rather than an obligation finding: what it says is
                # that the book does not contain the thing the check names, which is true of the
                # book whether or not anyone ever writes a QA plan against it.
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

        # Every check the node declared could go red for the reason the node exists, or the
        # claim it was written under proves nothing. Per claim rather than per node: a node
        # declaring one discriminating check used to silence this for every sibling bullet,
        # which is the same fan-out that credited one strong call to a claim nothing observed
        # — and the binding of a check to a claim is written down now (`attributed_checks`).
        # An `error`, unlike the prose heuristics around it, because the remedy is mechanical:
        # the check names the value, the route or the title the claim turns on, or it does not.
        verify_key = check_keys[0] if check_keys else "verify"
        contract_checks, claim_checks = registry.attributed_checks(
            node.type, node.bullet_order, node.combiners)

        # `attributed_checks` binds each check to the nearest normative bullet above it — a check
        # that was written against the wrong claim still binds, silently, to whichever claim
        # happens to sit above it. Two checks piled onto one claim while its neighbor carries none
        # is what that binding failure looks like from outside: not absence (that is
        # `undeclared-obligation`'s node-wide zero) but an imbalance between two claims on the
        # *same* node, which only reading both sides of `attributed_checks` together can see.
        # An `error`, `unstated-claim-combiner`'s reason: the remedy is mechanical — move a check
        # up to the claim it actually names — not a judgment call about prose.
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

        # A `command` node's `usage:`/`flags:`/`args:` are the invocation's prose synopsis — a
        # set of ways to call it, not any one of them — so a claim checked with `exits:`/
        # `verify:` still compiles to nothing unless the same claim also binds a `run:`: one
        # concrete argv, bound by the same document-order rule `attributed_checks` reads above.
        # `_gap_cli_obligations` (`qa/compile.py`) already withholds the scenario at compile
        # time for exactly this reason — this is the same defect, caught in the book itself,
        # before a plan is ever compiled, the way `undeclared-obligation` catches a node with no
        # check at all rather than waiting for `qa validate` to find nothing bound.
        # `error`, `uneven-claim-coverage`'s reason: the remedy is mechanical — add the `run:`
        # this claim names — not a judgment call about prose.
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

        # Fan-out is sound over a list of parts and unsound over a list of alternatives, and the
        # grammar records neither unless the author says so. Against "page stays put", a check
        # written for the success branch is not uninformative — it is a *refutation*, and an
        # unqualified fan-out files it as a proof. That is the one way a green run can be
        # evidence for a claim the run disproved, which is why this is an `error` and why the
        # word is stated rather than derived: a child label the vocabulary did not anticipate
        # would read as `all`, and guessing wrong in that direction is the whole defect.
        # Required only where it changes an outcome — more than one child, and a check bound to
        # them — so a book is not asked to annotate lists nobody observes.
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
        # The same two conditions `undetermined_claims` applies, against the stated word: a
        # `branches` list nobody wrote a check under has no check to have been misfiled, so
        # there is nothing here to report.
        _, fanned = registry.attributed_checks(node.type, node.bullet_order, {})
        for position, group in registry.claim_groups(node.type, node.bullet_order).items():
            if node.combiners.get(position, "") != "branches" or len(group) < 2:
                continue
            if not any(fanned.get(claim) for claim in group):
                continue
            line = node.bullet_lines.get(position, node.line)
            # Stated, and now the debt is visible: under `branches` the check above binds to no
            # child, so each one is an obligation nothing observes. The remedy is not a word —
            # it is splitting the alternatives into sibling authored bullets, each carrying the
            # `verify:` that is true of it, which is the shape a branch's own check can exist in.
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
        # Parsed once and read by both rules below, which ask different questions of the same
        # binding: `weak-check` asks whether a claim's checks can go red at all, and
        # `unstated-precondition` asks whether they read the change or only its aftermath.
        calls_by_claim = {ck: _calls(values) for ck, values in claim_checks.items()}

        # The claim id and the ref are one string: this used to name the claim in the message
        # and then throw the index away in the ref, so every weak claim on a node arrived under
        # the same address and the repair turn could not tell which one it was sent for.
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

        # A prose-driven heuristic, `warn` for `compound-normative-bullet`'s reason — the
        # remedy is authoring judgment, not a rewrite a tool can compute — and meant to be
        # waived per finding where the book knows better than the rule.
        # Per claim, and only where that claim is observed. Node-wide, this read every
        # `creates`/`registers` on the node against every check on the node: one `created(...)`
        # anywhere silenced a genuine lifecycle claim beside it, and a claim nothing observes at
        # all — a DI constructor's `- does: creates the process logger` — was reported against
        # some *other* bullet's checks, quoting a verb from a third. That last shape is the one
        # no edit could clear, because there is no after-read to turn into a before-and-after and
        # no subject a harness could read either side of. The unobserved claim is not this rule's
        # to raise: `undeclared-obligation` below covers the node that declares nothing, and
        # `qa validate`'s `claimed-but-unasserted` covers the bullet nothing asserts.
        claim_values = registry.normative_claims(node.type, node.bullet_order)
        for (key, index), calls in calls_by_claim.items():
            if key in NON_ACTION_KEYS:
                continue
            if not calls or any(c.name in LIFECYCLE_CHECKS for c in calls + contract_calls):
                continue
            verb = _states_a_lifecycle_claim(claim_values.get((key, index), ""))
            if not verb:
                continue
            # The claim quoted, not just its key. A node states `does:` several times, and
            # `node#does` names all of them at once — so on a node whose *other* `does:`
            # already declares `removed(...)`, every sentence this finding prints is true of
            # the answered bullet too. A repair turn reads it there, finds the book correct,
            # and reports `documented` with the finding still standing; three of those and an
            # adjudication is a run blocked on a defect whose remedy was one bullet away.
            # `key:index` is how obligation ids are already minted, so the id in the message
            # is the id `qa context` and the worklist use for the same claim.
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
            # One per node, as before: a node whose claims all read the aftermath has one
            # thing wrong with it, and N copies of that sentence is N waivers to write.
            break

        # The gap `unparsed-check` cannot see: a node that declares nothing at all. `verify:` is
        # on no type's required list, so a book stays green while every obligation it mints goes
        # into QA with nothing to bind — `qa validate` has no declaration to enforce and the
        # evidence map has no deficit to report. Node-level and not a count even though the
        # binding is written down now (`registry.attributed_checks`): the per-claim gap — this
        # bullet is claimed and nothing observes it — is `qa validate`'s `claimed-but-unasserted`,
        # raised against the plan that has to prove it. What is left for the book is the whole
        # of it: a node that declares no observation at all.
        # A `warn` for `compound-normative-bullet`'s reason — the remedy is authoring judgment,
        # and books written before the rule carry these by the hundred.
        # A `field` is observed through the record that carries it: its `default:` and
        # `required:` are proven by the check on the endpoint or entity that reads or writes
        # the record, and a check per attribute is one nobody binds. A field may still
        # declare `verify:`, and one that does not parse is `unparsed-check`'s as before.
        if check_keys and normative and not declared and node.type != "field":
            f.append(Finding(
                "warn", "undeclared-obligation",
                f"{node.id}: {normative} normative bullet{'s' if normative > 1 else ''} and no "
                f"`{check_keys[0]}:` — nothing says what observing them looks like, so a QA plan "
                f"claiming them can assert anything and still pass; declare a check per "
                f"observation (`ostler checks` lists the vocabulary and its signatures)",
                # No index: no check bullet exists, so the ref names the key to add.
                path=rel, line=node.line,
                ref=refs_mod.bullet_ref(node.id, check_keys[0]),
                # Nothing was declared, so there is no attempted name to echo back — but an
                # example is one check out of ten, and the author has to pick from all of them.
                suggestion=f'- {check_keys[0]}: http_status(code=409, title="Conflict")'
                           f'   # or: {", ".join(s.name for s in checks.CHECKS)}'))

    # A broken link that comes from a relation bullet (on/parent/extends/detail/…) is the more
    # specific `unresolved-relation`; index those (file, href) pairs so the link scan can classify.
    relation_hrefs: dict[tuple[str, str], str] = {}
    for node in graph.ui_nodes:
        for key in registry.RELATION_KEYS:
            for value in _bullet_values(node.meta.get(key, "")):
                for _text, href in markdown.extract_refs(value).links:
                    relation_hrefs[(str(node.path), href)] = key

    # LINK validation is **document-wide**: resolve every link in every doc file, whether or not it
    # sits inside an indexed node — a broken link is broken either way. (Links inside code are
    # skipped by `markdown.iter_links`.)
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
                # The ref carries the citing location, not the bare href. Link validation is
                # document-wide, so one broken href cited from three files produced three
                # findings at one address — and the fix is in a different file each time.
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
    """A claim's checks must be able to go red, not just able to run.

    `weak-check` above catches the two spellings that are *statically* rubber stamps — a bare
    2xx `http_status`, a presence-only `json_path` — by reading the call's own arguments. That
    is a list of known shapes; the property it stands in for is bigger, and `sensitivity.report`
    measures it directly by experiment: a witness observation is synthesized from the claim's
    declared calls, perturbed the way a real defect would perturb it, and re-verified. A claim
    whose checks stay green through every perturbation would have passed whatever the product
    did, which is `weak-check`'s finding widened past the two shapes it can see statically.

    Skips `undeclared` claims (no `verify:` at all) — that is `undeclared-obligation`'s finding,
    not this one's; asking sensitivity of a claim with no check would just repeat it.

    A `json_path(matches=...)` whose pattern admits `sensitivity._OTHER` is skipped the
    same way: `sensitivity._plan` drops its value mutation, so it never enters `report` as
    `insensitive`, and `_rubber_stamp` above already reports it as `weak-check`. That is the
    same split `unwitnessed-check` below draws in the other direction — a claim this rule
    cannot speak to belongs to the finding built to speak to it, not to a `reasons or ...`
    that would blur the two into one wrong verdict.

    Skips `unwitnessed` claims for the opposite reason, into `unwitnessed-check` below: there
    the experiment did not run, so there is nothing to report about the check. This used to
    read `reasons or 'no perturbation could be witnessed'` and raise the same error with the
    same suggestion either way — an `or` that turned "not measured" into "measured and
    failed", and aimed *assert a value the defect would actually change* at checks whose only
    fault was being too specific for the synthesizer to invent a witness for.
    """
    for row in sensitivity.report(graph):
        if row.status == "unwitnessed":
            notes = "; ".join(f"`{t.call}` — {t.note}" for t in row.trials if not t.witnessed)
            f.append(Finding(
                "warn", "unwitnessed-check",
                f"{row.claim}: `ostler qa sensitivity` could not build a witness observation "
                f"any check on this claim accepts, so no perturbation was tried — {notes}",
                path=row.path, line=row.line, ref=row.claim,
                # Not a repair instruction. The subject of this finding is the harness, and
                # the one edit that would silence it — a looser pattern the synthesizer can
                # satisfy — is the edit that would make `insensitive-check` true here.
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
    """`ostler doctor` as an outcome: `ok` = no error-severity finding, `data` = the report.

    Warnings do not fail it. A warning is a finding doctor deliberately declined to make
    blocking, and a caller that gates on `ok` should get the same verdict the CLI's exit
    code gives — errors only.
    """
    report = run(graph, epic_filter=epic, check_schema=check_schema)
    message = f"{report.errors} error(s), {report.warnings} warning(s)"
    return QaOutcome(ok=not report.errors, message=message, data=report.as_dict())
