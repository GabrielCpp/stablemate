"""`ostler doctor` — deterministic referential-integrity checks over the organization graph.

Computes (never asserts) per-epic seed/story counts and flags cross-epic references, orphan seeds,
missing story files, and dangling dependencies.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from ostler import (checks, dynamic_registry, freeze, inventory, links as links_mod, markdown,
                    registry, schemas, select)
from ostler import graph as graph_mod, locators as loc_mod, reach, waivers as waivers_mod
from ostler.vet import placement as placement_mod
from ostler import refs as refs_mod
from ostler.refs import normalize_ref
from ostler.model import Graph, Epic, required_section_problems


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
    waived: bool = False       # an accepted-defect waiver downgraded this from error to warn


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


def _epic_matches(epic: Epic, epic_filter: str) -> bool:
    """Whether ``--epic <filter>`` names this epic — by directory or by bare slug.

    Epic directories are numbered, so `--epic checkout-flow` has to keep finding
    `0001-checkout-flow`; a filter nobody matches still narrows to nothing, as before.
    """
    return (epic_filter in (epic.name, epic.directory.name)
            or registry.epic_slug(epic.name) == registry.epic_slug(epic_filter))


def run(graph: Graph, epic_filter: str | None = None, check_schema: bool = True) -> Report:
    report = Report(org=graph.org_name, profile=graph.profile)
    f = report.findings

    _check_ui(graph, f)
    # One build, shared. Each of these needs the resolved node/edge dump, and on a large book a
    # rebuild costs more than every other check in this function put together.
    ui_data = _ui_graph(graph)
    if ui_data is not None:
        _check_reachability(ui_data, f)
        _check_locators(ui_data, f)
    if check_schema:
        _check_conformance(graph, f)

    if graph.profile != "full":
        _check_frozen(graph, report.findings)
        _apply_waivers(graph, report.findings)
        return report

    all_story_slugs = graph.all_story_slugs()

    _check_milestones(graph, f)

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

    _apply_waivers(graph, report.findings)
    return report


def _apply_waivers(graph: Graph, findings: list[Finding]) -> None:
    """Downgrade every error finding that carries an accepted-defect waiver from error to warn.

    A waiver never removes the finding — it stays in the report at ``warn`` with its reason and the
    backlog id tracking the real fix, so ``doctor --json`` still shows it while the gate (which
    counts only ``error``) stops treating it as a blocker. See ostler/waivers.py. Imported locally to
    keep the module import graph acyclic, matching ``_check_locators``' local ``locators`` import.
    """
    table = waivers_mod.load(graph)
    if not table:
        return
    for fd in findings:
        if fd.severity != "error":
            continue
        entry = table.get((fd.code, normalize_ref(fd.ref)))
        if entry is None:
            continue
        fd.severity = "warn"
        fd.waived = True
        fd.fixable = False
        tag = f" [waived — see backlog {entry['backlog']}]" if entry.get("backlog") else " [waived]"
        reason = f": {entry['reason']}" if entry.get("reason") else ""
        fd.message = f"{fd.message}{tag}{reason}"


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
            # story.md says something — a file that is still the scaffold `ostler create story`
            # wrote is not an authored story, and must not pass as one just by existing.
            if story.unwritten_sections:
                rel = story.story_md.relative_to(graph.root).as_posix()
                f.append(Finding("error", "unwritten-story",
                                 f"story '{story.slug}' is still a bare scaffold — "
                                 f"{', '.join(story.unwritten_detail)}",
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
                fm = (markdown.split(path.read_text(encoding="utf-8")).frontmatter) or {}
            except OSError as exc:
                f.append(Finding("error", "unreadable", f"{rel}: {exc}", path=rel))
                continue
            declared = registry.type_of(fm)
            if not declared:
                f.append(Finding("error", "okf-missing-type",
                                 f"{rel}: Concept has no non-empty `type` in frontmatter",
                                 path=rel, line=1))
                continue
            schema = schema_by_base.get(registry.base_type(declared))
            if schema:
                for msg in schemas.validate(fm, schema):
                    f.append(Finding("warn", "schema", f"{rel}: {msg}", path=rel))
    if graph.ids is not None:
        for msg in schemas.validate(graph.ids, "ids.schema.json"):
            f.append(Finding("warn", "schema", f"ids.json: {msg}"))


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
        doc = markdown.split(path.read_text(encoding="utf-8"))
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
            code = "missing-required-section" if problem == "missing" else "empty-required-section"
            state = "is missing" if problem == "missing" else "leaves empty"
            f.append(Finding("error", code,
                             f"{rel}: {ftype.name} {state} its required `## {spec.heading}` "
                             f"section", path=rel, line=1,
                             suggestion=f"## {spec.heading}", fixable=(problem == "missing")))


def _declares(path: Path, text: str, symbol: str) -> bool:
    """Whether *text* declares *symbol* — `ostler.inventory`'s grammar, not a second one.

    This delegates on purpose. It used to ask whether every part of the symbol appeared as a
    *word* in the file, which is not the same question and answered it wrong in the one
    direction that matters: a facade module re-exporting a name (``from .renderer import
    Renderer``) still contains the word, so a citation whose definition had moved away stayed
    green — the drift this check exists to catch. The inventory already knew how to read a
    declaration; grounding just wasn't asking it.
    """
    return inventory.declares(path, text, symbol)


def _check_code_grounding(graph: Graph, f: list[Finding]) -> None:
    """`code:` targets name a file that exists, and a symbol that file declares.

    This is what stops two path conventions from silently coexisting, what keeps the book
    honest as the source moves under it, and what surfaces a documented unit that has since
    been deleted. The grammar is the book's own (OKF UI profile §5):
    `<path-relative-to-repo-root>::<symbol>`, the symbol qualified by its owner when it has one.

    Note this cannot route through the link scan: `links.is_doc_link` rejects any href
    containing `::`, and a backticked `` `x.go::S` `` is inline code, not a markdown link — so
    `markdown.iter_links` never yields it. The bullets are read directly, as the
    required-bullet loop does.
    """
    for node in graph.ui_nodes:
        uitype = registry.ui_type(node.type)
        if uitype is None or "code" not in uitype.bullet_by_key:
            continue
        rel = node.path.relative_to(graph.root).as_posix()
        for ref in refs_mod.code_refs(node.meta.get("code")):
            target_path, separator, symbol = ref.partition("::")
            target = graph.root / target_path
            if not target.is_file():
                f.append(Finding(
                    "error", "dangling-code-ref",
                    f"{node.id}: `code:` target '{ref}' — no such file '{target_path}'",
                    path=rel, line=node.line, ref=ref,
                    suggestion="a path relative to the repo root, as `path::symbol`"))
                continue
            if not (separator and symbol):
                continue  # a whole-file unit (a template renders a screen): existence is enough
            if _SPACE.search(symbol):
                # The profile admits `path::symbol` **or a `file` region** — and a region is
                # prose ("notification permission bootstrap"), not a name. There is nothing to
                # ground but the file, and holding prose to a symbol's bar would flag the
                # convention the profile itself grants. When the book and the tool disagree
                # about grammar, the book wins.
                continue
            try:
                text = target.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            if not _declares(target, text, symbol):
                f.append(Finding(
                    "error", "missing-code-symbol",
                    f"{node.id}: `code:` target '{ref}' — '{target_path}' does not declare "
                    f"'{symbol}'", path=rel, line=node.line, ref=ref))


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
#: exactly the signal it exists to find.
_STATUS_CODE = re.compile(r"(?<![\w.])[1-5]\d{2}(?![\w.])")
_ERROR_NAME = re.compile(r"\b[A-Z][A-Za-z0-9]*(?:Error|Exception|Conflict|Failure|Denied)\b")
#: A semicolon with a real clause after it. `;` inside a code span or ending a bullet is not a
#: joined requirement, so the tail has to carry at least three words to count.
_SEMICOLON_CLAUSE = re.compile(r";\s+(?:\S+\s+){2}\S")
#: "and … and", specifically the clause-joining kind: at least one `and` following a comma or
#: semicolon, plus another anywhere. Bare repeated `and`s are how anyone lists two nouns, and a
#: rule that fires on `- does: creates the page and its slug` is a rule people learn to ignore.
_CLAUSE_AND = re.compile(r"[,;]\s+and\b")
_ANY_AND = re.compile(r"\band\b")


def _split_signals(value: str) -> list[str]:
    """Why this bullet looks like several observations, one sentence per reason (or none)."""
    reasons: list[str] = []
    statuses = sorted(set(_STATUS_CODE.findall(value)))
    if len(statuses) > 1:
        reasons.append(f"it names {len(statuses)} status codes ({', '.join(statuses)})")
    names = sorted(set(_ERROR_NAME.findall(value)))
    if len(names) > 1:
        reasons.append(f"it names {len(names)} distinct failures ({', '.join(names)})")
    if _SEMICOLON_CLAUSE.search(value):
        reasons.append("a semicolon joins two independent clauses")
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
LIFECYCLE_VERBS = frozenset({
    "creates", "creating", "adds", "adding", "registers", "registering",
    "issues", "issuing", "inserts", "inserting", "provisions", "provisioning",
    "deletes", "deleting", "removes", "removing", "revokes", "revoking",
    "archives", "archiving", "purges", "purging",
})

#: The two checks that observe existence as a *change* — the before-read and the after-read,
#: rather than the after-read alone. Declaring either is what clears `unstated-precondition`.
LIFECYCLE_CHECKS = frozenset({"created", "removed"})

_WORD = re.compile(r"[a-zA-Z']+")


def _states_a_lifecycle_claim(value: str) -> str:
    """The lifecycle verb this bullet uses, or "" — the word a finding has to quote."""
    for word in _WORD.findall(_prose(value)):
        if word.lower() in LIFECYCLE_VERBS:
            return word.lower()
    return ""


def _rubber_stamp(call: checks.CheckCall) -> str:
    """Why this call would stay green against the defect its bullet describes, or "".

    Not a judgment about the check's name: `json_path` and `http_status` are the two calls
    whose *arguments* decide whether anything is being told apart, and both have a spelling
    that asserts only that the code ran. Every other check in the vocabulary compares
    something by construction.
    """
    if call.name == "json_path":
        if "equals" in call.args or "matches" in call.args:
            return ""
        if call.args.get("absent") is True:
            return ""
        return (f"`json_path(path=\"{call.args.get('path', '')}\")` asserts the field is "
                f"present without saying what it holds, so it passes on the default the "
                f"defect also produces")
    if call.name == "http_status":
        code = call.args.get("code")
        if isinstance(code, int) and 200 <= code < 300 and not ({"title", "path"} & set(call.args)):
            return (f"`http_status(code={code})` names neither a `path:` nor a `title:`, so it "
                    f"says the request succeeded and nothing about which request or what it "
                    f"answered")
        return ""
    return ""


def _ui_graph(graph: Graph) -> dict | None:
    """The resolved node/edge dump, or None when it will not build.

    A graph that cannot be assembled is already reported by the checks above, so the UI-profile
    checks stay silent rather than reporting the same breakage in a second vocabulary.
    """
    try:
        return graph_mod.build(graph)
    except (OSError, ValueError, RuntimeError, KeyError):
        return None


def _check_reachability(data: dict, f: list[Finding]) -> None:
    """Every screen must be reachable by clicking from a declared entry point.

    An unreachable screen is a hole in the book, not a quirk of the app: if no documented path
    leads there, a reader cannot get there and neither can a walk. The remedy is a ``leads-to:``
    on whatever component navigates there — or an ``entry:`` bullet, when the screen really is
    entered from outside (an emailed deep link, an OAuth callback, the app root).

    Run per surface, because entry points are surface-scoped: a screen in ``web`` is not made
    reachable by a root declared in ``legacy``.
    """
    surfaces = {n["surface"] for n in data["nodes"] if n["type"] == "screen"}
    for surface in sorted(s for s in surfaces if s):
        scoped = graph_mod.subset(data, surface)
        screens = reach.screens_of(scoped)
        if not screens:
            continue
        unreachable, entries = reach.unreachable_screens(scoped)
        if not entries:
            # No root means the question is unanswerable, which is not the same as a pass. Warn
            # rather than error: a book with no `entry:` anywhere predates the convention, and
            # flooding it with one error per screen would bury the one fact that matters.
            f.append(Finding("warn", "no-entry-point",
                             f"{surface}: no screen declares `entry:` — reachability cannot be "
                             f"checked for this surface",
                             ref=surface, suggestion="- entry: <how this screen is entered>"))
            continue
        for screen in unreachable:
            node = next((n for n in scoped["nodes"] if n["id"] == screen), None)
            f.append(Finding("error", "unreachable-screen",
                             f"{screen}: no documented path reaches this screen from "
                             f"{'/'.join(sorted(entries)[:1])} — add a `leads-to:` on the "
                             f"component that navigates here, or `entry:` if it is entered "
                             f"from outside the app",
                             path=screen, line=node["line"] if node else 0, ref=screen,
                             suggestion="- leads-to: [<this screen>](<path>)"))


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
                ref=node_id,
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
                path=rel, line=node.line, ref=f"{node.id}#placement",
                suggestion="- placement: width 60-100%, x 0-20%   (read off the running UI)"))
        return
    for value in values:
        parsed = placement_mod.parse_placement(value)
        if isinstance(parsed, str):
            f.append(Finding(
                "error", "malformed-placement",
                f"{node.id}: `placement: {value}` is not a placement — {parsed}",
                path=rel, line=node.line, ref=f"{node.id}#placement",
                suggestion="- placement: width 60-100%, x 0-20%"))


def _check_ui(graph: Graph, f: list[Finding]) -> None:
    froot = graph.doc_roots.get("features")
    if froot is not None and froot.is_dir():
        for path in sorted(froot.rglob("*.md")):
            if path.is_file() and path.name not in registry.RESERVED_FILES:
                _check_ui_file(graph, path, f)
    _check_code_grounding(graph, f)

    resolver = links_mod.LinkResolver(graph)

    # required-bullet checks stay per-node — they need the node's declared type + schema.
    for node in graph.ui_nodes:
        uitype = registry.ui_type(node.type)
        if uitype is None:
            continue
        rel = node.path.relative_to(graph.root).as_posix()
        for bk in uitype.bullet_keys:
            if bk.required and bk.key not in node.meta:
                f.append(Finding("error", "missing-required-bullet",
                                 f"{node.id}: {node.type} missing required `{bk.key}:`",
                                 path=rel, line=node.line, ref=bk.key,
                                 suggestion=f"- {bk.key}:", fixable=True))

        if node.type == "component":
            _check_placement(node, rel, f)

        normative = 0
        lifecycle: list[tuple[str, str]] = []
        for key in registry.normative_keys(node.type):
            for value in _bullet_values(node.meta.get(key, "")):
                normative += 1
                verb = _states_a_lifecycle_claim(value)
                if verb:
                    lifecycle.append((key, verb))
                length = len(_prose(value))
                if length > MAX_NORMATIVE_PROSE:
                    f.append(Finding(
                        "error", "overlong-normative-bullet",
                        f"{node.id}: `{key}:` runs {length} characters of prose — too much to "
                        f"prove as one claim; split it into one bullet per provable claim",
                        path=rel, line=node.line, ref=f"{node.id}#{key}"))
                    continue
                # A `warn`, alone among the UI checks, and for the reason the header states in
                # reverse: there is no deterministic remedy. Splitting a bullet is authoring
                # judgment — which branch is its own claim, what each one is called — so a
                # strict `doctor` cannot converge on it the way it converges on `fmt`. What the
                # rule buys is that the judgment gets made once, at the node, instead of once
                # per story that touches it for as long as the node exists.
                reasons = _split_signals(value)
                if reasons:
                    f.append(Finding(
                        "warn", "compound-normative-bullet",
                        f"{node.id}: `{key}:` states more than one observation — "
                        f"{'; '.join(reasons)}. One bullet is one obligation and is proved by "
                        f"one scenario, so the clauses that share it are covered by whichever "
                        f"one the planner read; split it into one bullet per observation",
                        path=rel, line=node.line, ref=f"{node.id}#{key}"))

        check_keys = registry.check_keys(node.type)
        declared = 0
        parsed_calls: list[checks.CheckCall] = []
        for key in check_keys:
            for value in _bullet_values(node.meta.get(key, "")):
                # Counted before it is parsed: a node that declared and got the call wrong is
                # already told so by `unparsed-check`, and telling it twice buys the author
                # nothing and costs a second thing to waive.
                declared += 1
                parsed = checks.parse_check(value)
                if isinstance(parsed, str):
                    f.append(Finding(
                        "error", "unparsed-check",
                        f"{node.id}: `{key}:` {parsed}",
                        path=rel, line=node.line, ref=f"{node.id}#{key}",
                        # The failing check's own signature, never a canned example: an author
                        # shown `http_status(code=…)` after mis-calling `absent` learns nothing
                        # about `absent`, and guesses again on the next lap.
                        suggestion=f"- {key}: {checks.expected_form(value)}"))
                else:
                    parsed_calls.append(parsed)

        # Two ways a node passes `undeclared-obligation` and still proves nothing. Both are
        # `warn` for that rule's reason — the remedy is authoring judgment, not a rewrite a
        # tool can compute — and both are prose-driven heuristics, so both are meant to be
        # waived per finding where the book knows better than the rule.
        if parsed_calls:
            # Every declared check, and not one of them could go red for the reason the node
            # exists. Node-level and all-or-nothing on purpose: a node that declares one
            # discriminating check has made the judgment, and second-guessing which bullet it
            # belongs to is the pairing nobody has written down (see `undeclared-obligation`).
            stamps = [_rubber_stamp(call) for call in parsed_calls]
            if all(stamps):
                f.append(Finding(
                    "warn", "weak-check",
                    f"{node.id}: every declared check passes on the defect it is meant to "
                    f"catch — {stamps[0]}. Name the value, the route or the title the claim "
                    f"turns on, so there is a state of the world in which the check goes red",
                    path=rel, line=node.line, ref=f"{node.id}#{check_keys[0]}",
                    suggestion=f'- {check_keys[0]}: json_path(path="…", equals="…")'))

            if lifecycle and not any(c.name in LIFECYCLE_CHECKS for c in parsed_calls):
                key, verb = lifecycle[0]
                f.append(Finding(
                    "warn", "unstated-precondition",
                    f"{node.id}: `{key}:` says the node {verb}s something, and the checks read "
                    f"only the state afterwards — which is the same state a no-op leaves when "
                    f"the subject was already there. Declare the change as a change, so the "
                    f"before-read is part of the observation rather than an assumption",
                    path=rel, line=node.line, ref=f"{node.id}#{key}",
                    suggestion=f'- {check_keys[0]}: created(subject="…")   # or: removed'))

        # The gap `unparsed-check` cannot see: a node that declares nothing at all. `verify:` is
        # on no type's required list, so a book stays green while every obligation it mints goes
        # into QA with nothing to bind — `qa validate` has no declaration to enforce and the
        # evidence map has no deficit to report. Node-level and not a count, because `verify:`
        # sits on the node rather than the bullet (see `qa/context.py`'s `checksDeclared`):
        # pairing a check to one bullet is a judgment nobody has written down yet, and the
        # honest computable question is whether the node declares any observation at all.
        # A `warn` for `compound-normative-bullet`'s reason — the remedy is authoring judgment,
        # and books written before the rule carry these by the hundred.
        if check_keys and normative and not declared:
            f.append(Finding(
                "warn", "undeclared-obligation",
                f"{node.id}: {normative} normative bullet{'s' if normative > 1 else ''} and no "
                f"`{check_keys[0]}:` — nothing says what observing them looks like, so a QA plan "
                f"claiming them can assert anything and still pass; declare a check per "
                f"observation (`ostler checks` lists the vocabulary and its signatures)",
                path=rel, line=node.line, ref=f"{node.id}#{check_keys[0]}",
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
                body = path.read_text(encoding="utf-8")
            except OSError:
                continue
            seen: set = set()
            for _text, href, line in markdown.iter_links(body):
                if not links_mod.is_doc_link(href) or href in seen:
                    continue
                seen.add(href)
                target = resolver.resolve(path, href)
                if target is None or target.resolved:
                    continue
                rkey = relation_hrefs.get((str(path), href))
                if rkey:
                    f.append(Finding("error", "unresolved-relation",
                                     f"{rel}: `{rkey}:` target '{href}' does not resolve",
                                     path=rel, line=line, ref=href, fixable=True))
                elif not target.file_exists:
                    f.append(Finding("error", "dangling-link",
                                     f"{rel}: link '{href}' target file does not exist",
                                     path=rel, line=line, ref=href, fixable=True))
                else:
                    f.append(Finding("error", "missing-anchor",
                                     f"{rel}: link '{href}' — file exists but `#{target.anchor}` "
                                     f"heading not found", path=rel, line=line, ref=href,
                                     fixable=True))
