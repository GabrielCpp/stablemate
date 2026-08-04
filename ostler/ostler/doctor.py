"""`ostler doctor` — deterministic referential-integrity checks over the organization graph.

Computes (never asserts) per-epic seed/story counts and flags cross-epic references, orphan seeds,
missing story files, and dangling dependencies / knowledge paths.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from ostler import (dynamic_registry, freeze, inventory, links as links_mod, markdown,
                    registry, schemas)
from ostler import graph as graph_mod, locators as loc_mod, reach, waivers as waivers_mod
from ostler import refs as refs_mod
from ostler.refs import normalize_ref
from ostler.model import Graph, Epic, section_gaps


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

    _check_surfaces(graph, f)
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
            # story.md says something — a file that is still the scaffold `ostler create story`
            # wrote is not an authored story, and must not pass as one just by existing.
            if story.unwritten_sections:
                rel = story.story_md.relative_to(graph.root).as_posix()
                f.append(Finding("error", "unwritten-story",
                                 f"story '{story.slug}' is still a bare scaffold — "
                                 f"{', '.join(story.unwritten_sections)} "
                                 f"{'is' if len(story.unwritten_sections) == 1 else 'are'} empty",
                                 epic.name, story.slug, path=rel, line=1))
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
# is a join key nobody checked. `verify:` stays deferred — its value is a test id as often as a
# `path::symbol`, so it has no single shape to hold it to.
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

    ftype = registry.ui_type(declared)
    if ftype is not None and ftype.kind == "file":
        for spec, gap in section_gaps(doc, ftype.required_sections):
            code = "missing-required-section" if gap == "missing" else "empty-required-section"
            state = "is missing" if gap == "missing" else "leaves empty"
            f.append(Finding("error", code,
                             f"{rel}: {ftype.name} {state} its required `## {spec.heading}` "
                             f"section", path=rel, line=1,
                             suggestion=f"## {spec.heading}", fixable=(gap == "missing")))


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


def _bullet_values(value) -> list[str]:
    """A bullet's raw values — a repeated key parses to a list, a single one to a string.

    Raw on purpose: its one caller scans relation bullets for markdown links, so the value
    must arrive undecorated. `code:`/`verify:` targets go through `refs.code_refs` instead,
    which knows that one bullet may cite several.
    """
    if isinstance(value, list):
        return [str(item) for item in value]
    return [str(value)] if value else []


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
