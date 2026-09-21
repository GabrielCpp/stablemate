"""OKF UI profile — the eleven UI/concept node types (docs/okf-ui-profile.md)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from ostler import doctor, drivers, graph, query, reach, registry
from ostler.model import load

from conftest import present, write


def codes(report, severity="error"):
    return {f.code for f in report.findings if f.severity == severity}


def write_cited_code(repo: Path) -> None:
    """The source `SCREEN`'s `code:` bullets point at."""
    write(repo / "groom/groom/render.py", "def _changes_worker(diff):\n    return diff\n")
    write(repo / "groom/groom/templates/dashboard.html",
          "<script>function wireChanges() {}</script>\n")


def write_stack_runbook(repo: Path) -> None:
    """A minimal stack runbook — `SCREEN` describes a served surface, so a green doctor now requires one (`runbook-missing` is an error; see `doctor._check_runbook`)."""
    write(repo / "docs" / "features" / "app" / "ops" / "qa-stack.md", (
        "---\ntype: runbook\ntitle: QA stack\n---\n\n# QA stack\n\n"
        "- driver: web\n- entry-url: http://localhost:18084\n\n"
        "## Steps\n\n### serve\n\n- kind: service\n- run: ./serve.sh\n"
    ))


SCREEN = """\
---
type: screen
slug: changes-view
title: Changes view
---
# Changes view

- route: `/changes`
- requires: none
- params: none

Groups every worker's working-tree diff per repo.

## Components

### changes-file-row
- selector: `div.tree-file`
- role: treeitem
- name: the file's repo-relative path
- keyboard: `up`/`down` to move, `enter` to open
- extends: [tree-node](../components/design-system.md#tree-node)
- code: `groom/groom/render.py::_changes_worker`

A leaf of the per-worker file tree.

### single-file-diff
- selector: `div.diff-pane`
- role: region
- name: Diff
- placement: width 40-100%, x 30-100%, y 10-100%
- keyboard: none, because it is read rather than operated
- code: `groom/groom/render.py::_changes_worker`

The pane the selected file's diff is rendered into.

## Interactions

### click-file-opens-diff
- on: [changes-file-row](#changes-file-row)
- trigger: click
- role: treeitem
- name: the file's repo-relative path
- keyboard: `enter`
- when: `mode == changes`
- does: all
  - state: mark row `.active`, clear siblings
  - dom: render single-file diff
- code: `groom/groom/templates/dashboard.html::wireChanges`
- verify: visible(locator="#single-file-diff")
- tests: `groom/tests/test_render.py::test_changes_groups_diffs_per_repo`
"""


def test_ui_types_registered():
    assert set(registry.UI_TYPES_BY_NAME) == {
        "screen", "component", "interaction", "cli", "command", "server", "endpoint",
        "invocation", "flow", "concept", "format",
        "method", "field",
        "runbook", "environment", "step",
        "fixture",
        "untyped",
    }


def test_heading_to_type_map():
    assert registry.UI_HEADING_TO_TYPE == {
        "Components": "component", "Commands": "command", "Endpoints": "endpoint",
        "Interactions": "interaction", "Invocations": "invocation",
        "Methods": "method", "Fields": "field",
        "Steps": "step",
    }


def test_is_known_type():
    assert registry.is_known_type("screen")
    assert registry.is_known_type("concept")
    assert registry.is_known_type("feature")
    assert not registry.is_known_type("bogus")
    assert not registry.is_known_type("")


NODE_TYPE_PAGES = Path(__file__).resolve().parents[2] / (
    "base-library/library/skills/ostler/okf/references/node-types")


def _example_bullets(block: str) -> list[tuple[str, str, int]]:
    """A fenced example's top-level `key: value` bullets, in the shape `bullet_order` has."""
    order: list[tuple[str, str, int]] = []
    for line in block.split("\n"):
        matched = re.match(r"^- ([a-z-]+):\s*(.*)$", line)
        if matched is not None:
            order.append((matched.group(1), matched.group(2), len(order)))
    return order


def test_a_reference_example_binds_each_check_to_its_own_claim():
    """A page's example is a book, and until now no checker read one."""
    misbound: list[str] = []
    for page in sorted(NODE_TYPE_PAGES.glob("*.md")):
        uitype = registry.ui_type(page.stem)
        if uitype is None:
            continue
        for block in re.findall(r"```markdown\n(.*?)```", page.read_text(), re.S):
            order = _example_bullets(block)
            _, per_claim = registry.attributed_checks(uitype.name, order, {})
            claims = registry.normative_claims(uitype.name, order)
            uncovered = [claim for claim in claims if claim not in per_claim]
            crowded = [claim for claim, found in per_claim.items() if len(found) > 1]
            if uncovered and crowded:
                misbound.append(
                    f"{page.name}: {crowded} each carry several checks while {uncovered} "
                    f"carry none")
    assert not misbound, (
        "a node-type page's example binds two checks to one claim and none to another — "
        "the example is what an author copies, so it teaches the misbinding:\n  "
        + "\n  ".join(misbound))


def test_ui_type_lookup_by_base():
    assert present(registry.ui_type("interaction")).heading == "Interactions"
    assert present(registry.ui_type("screen")).kind == "file"
    assert registry.ui_type("epic") is None


DESIGN_SYSTEM = """\
---
type: feature
slug: design-system
title: DS
---
# DS

## Components

### tree-node
- selector: `div.tree-file`
- role: treeitem
- name: none
"""


def test_screen_doc_under_features_keeps_doctor_green(repo: Path):
    write(repo / "docs/features/groom/gui/screens/changes-view.md", SCREEN)
    write(repo / "docs/features/groom/gui/components/design-system.md", DESIGN_SYSTEM)
    write_stack_runbook(repo)
    write_cited_code(repo)
    report = doctor.run(load(repo))
    schema_hits = [f for f in report.findings
                   if f.code == "schema" and "changes-view.md" in f.message]
    assert schema_hits == []
    assert report.errors == 0, [f.message for f in report.findings if f.severity == "error"]


def test_real_feature_still_schema_checked(repo: Path):
    write(repo / "docs/features/x.md", "---\ntype: feature\nslug: x\n---\n# X\n")
    report = doctor.run(load(repo))
    assert any(f.code == "schema" and "x.md" in f.message for f in report.findings)


def test_typeless_feature_flagged(repo: Path):
    write(repo / "docs/features/y.md", "---\nslug: y\n---\n# Y\n")
    report = doctor.run(load(repo))
    assert "okf-missing-type" in codes(report)


def test_located_finding_carries_path(repo: Path):
    write(repo / "docs/features/y.md", "---\nslug: y\n---\n# Y\n")
    report = doctor.run(load(repo))
    finding = next(f for f in report.findings if f.code == "okf-missing-type")
    assert finding.path == "docs/features/y.md"
    assert finding.line == 1


CONCEPT = """\
---
type: concept
slug: diff
title: Diff
---
# Diff

- code: `{ref}`

A unified diff.
"""


def _concept_report(repo: Path, ref: str, checkouts: dict[str, Path] | None = None):
    write(repo / "docs/features/groom/concepts/diff.md", CONCEPT.format(ref=ref))
    return doctor.run(load(repo), checkouts=checkouts)


def test_code_ref_to_a_missing_file_is_an_error(repo: Path):
    report = _concept_report(repo, "groom/groom/gone.py::Diff")
    assert "dangling-code-ref" in codes(report)


def test_code_ref_to_a_missing_symbol_is_an_error(repo: Path):
    write(repo / "groom/groom/diff.py", "class Other:\n    pass\n")
    report = _concept_report(repo, "groom/groom/diff.py::Diff")
    assert "missing-code-symbol" in codes(report)


def test_a_grounded_code_ref_is_green(repo: Path):
    write(repo / "groom/groom/diff.py", "class Diff:\n    pass\n")
    report = _concept_report(repo, "groom/groom/diff.py::Diff")
    assert not (codes(report) & {"dangling-code-ref", "missing-code-symbol"})


def test_an_unstamped_code_ref_is_a_warning(repo: Path):
    write(repo / "groom/groom/diff.py", "class Diff:\n    pass\n")
    report = _concept_report(repo, "groom/groom/diff.py::Diff")
    assert "unstamped-citation" in codes(report, "warn")
    assert not (codes(report) & {"stale-citation"})
    finding = next(f for f in report.findings if f.code == "unstamped-citation")
    assert finding.node


def test_a_stamped_code_ref_whose_file_changed_is_stale(repo: Path):
    from ostler.stamp import digest_file
    write(repo / "groom/groom/diff.py", "class Diff:\n    pass\n")
    stale_digest = digest_file(b"class Diff:\n    pass\n    x = 1\n")
    report = _concept_report(repo, f"groom/groom/diff.py::Diff@{stale_digest}")
    assert "stale-citation" in codes(report)
    assert "unstamped-citation" not in codes(report, "warn")


def test_a_stamped_code_ref_matching_the_file_is_green(repo: Path):
    from ostler.stamp import digest_file
    text = "class Diff:\n    pass\n"
    write(repo / "groom/groom/diff.py", text)
    report = _concept_report(repo, f"groom/groom/diff.py::Diff@{digest_file(text.encode())}")
    assert not (codes(report) & {"stale-citation", "dangling-code-ref", "missing-code-symbol"})
    assert not (codes(report, "warn") & {"unstamped-citation"})


def test_a_foreign_repository_ref_with_no_checkout_is_unreachable_not_unstamped(repo: Path):
    report = _concept_report(repo, "repo://api-service/src/service.py::create_invoice")
    assert "unreachable-citation" in codes(report, "warn")
    assert "unstamped-citation" not in codes(report, "warn")
    assert not (codes(report) & {"dangling-code-ref", "missing-code-symbol", "stale-citation"})


def test_a_foreign_repository_ref_with_a_checkout_is_checked_like_a_local_one(repo: Path):
    checkout = repo.parent / "checkouts" / "api-service"
    write(checkout / "src/service.py", "def create_invoice():\n    return 1\n")
    report = _concept_report(
        repo, "repo://api-service/src/service.py::create_invoice",
        checkouts={"api-service": checkout},
    )
    assert "unstamped-citation" in codes(report, "warn")
    assert not (codes(report) & {"dangling-code-ref", "missing-code-symbol"})
    assert "unreachable-citation" not in codes(report, "warn")


def test_a_foreign_repository_ref_whose_checked_out_file_changed_is_stale(repo: Path):
    from ostler.stamp import digest_file

    checkout = repo.parent / "checkouts" / "api-service"
    write(checkout / "src/service.py", "def create_invoice():\n    return 1\n")
    stale_digest = digest_file(b"def create_invoice():\n    return 0\n")
    report = _concept_report(
        repo, f"repo://api-service/src/service.py::create_invoice@{stale_digest}",
        checkouts={"api-service": checkout},
    )
    assert "stale-citation" in codes(report)
    assert not (codes(report, "warn") & {"unstamped-citation", "unreachable-citation"})


def test_a_missing_symbol_in_a_foreign_checkout_is_an_error(repo: Path):
    checkout = repo.parent / "checkouts" / "api-service"
    write(checkout / "src/service.py", "def other():\n    return 1\n")
    report = _concept_report(
        repo, "repo://api-service/src/service.py::create_invoice",
        checkouts={"api-service": checkout},
    )
    assert "missing-code-symbol" in codes(report)


def test_a_receiver_qualified_symbol_grounds_against_go(repo: Path):
    write(repo / "api/claims.go",
          "package p\ntype FirebaseClaimsWriter struct{}\n"
          "func (w *FirebaseClaimsWriter) SetRoleClaims() {}\n")
    ok = _concept_report(repo, "api/claims.go::(*FirebaseClaimsWriter).SetRoleClaims")
    assert not (codes(ok) & {"dangling-code-ref", "missing-code-symbol"})
    bad = _concept_report(repo, "api/claims.go::(*FirebaseClaimsWriter).Removed")
    assert "missing-code-symbol" in codes(bad)


def test_a_service_relative_ref_is_caught_as_dangling(repo: Path):
    write(repo / "api/internal/claims.go", "package p\nfunc Write() {}\n")
    report = _concept_report(repo, "internal/claims.go::Write")
    assert "dangling-code-ref" in codes(report)
    finding = next(f for f in report.findings if f.code == "dangling-code-ref")
    assert "repo root" in finding.suggestion


def test_a_whole_file_code_ref_needs_only_the_file(repo: Path):
    write(repo / "legacy/templates/Home.html.twig", "<p>hi</p>\n")
    report = _concept_report(repo, "legacy/templates/Home.html.twig")
    assert not (codes(report) & {"dangling-code-ref", "missing-code-symbol"})


def test_a_file_region_is_not_held_to_a_symbols_bar(repo: Path):
    write(repo / "groom/groom/templates/dashboard.html", "<script>//...</script>\n")
    report = _concept_report(
        repo, "groom/groom/templates/dashboard.html::notification permission bootstrap")
    assert not (codes(report) & {"dangling-code-ref", "missing-code-symbol"})


def test_a_file_region_still_grounds_its_file(repo: Path):
    report = _concept_report(repo, "groom/groom/templates/gone.html::some region")
    assert "dangling-code-ref" in codes(report)


def test_a_code_finding_is_located_at_its_node(repo: Path):
    report = _concept_report(repo, "groom/groom/gone.py::Diff")
    finding = next(f for f in report.findings if f.code == "dangling-code-ref")
    assert finding.path == "docs/features/groom/concepts/diff.md"
    assert finding.line > 0
    assert finding.ref == "groom/groom/gone.py::Diff"


def test_a_section_node_citing_a_whole_source_file_is_flagged(repo: Path):
    """`code:` on a `kind == "section"` type (here, a `component`) names a *part* of a file, so a bare path with no `::symbol` has said only where to start looking, not where the node is grounded — unlike `concept` (`kind == "file"`), which the earlier whole-file test shows is exempt because its subject genuinely is the whole file."""
    write(repo / "groom/groom/render.py", "def handler():\n    return 1\n")
    write(repo / "docs/features/groom/gui/screens/s.md",
          "---\ntype: screen\nslug: s\ntitle: S\n---\n# S\n\n"
          "## Components\n\n### body\n"
          "- role: generic\n- name: none\n"
          "- code: `groom/groom/render.py`\n")
    report = doctor.run(load(repo))
    assert "whole-file-code-ref" in codes(report)
    finding = next(f for f in report.findings if f.code == "whole-file-code-ref")
    assert finding.ref == "groom/groom/render.py"


def test_a_code_symbol_cited_against_a_non_utf8_source_file_is_flagged(repo: Path):
    target = repo / "groom/groom/legacy.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"def broken():\n    return b'\xff\xfe'\n")
    write(repo / "docs/features/groom/gui/screens/s.md",
          "---\ntype: screen\nslug: s\ntitle: S\n---\n# S\n\n"
          "## Components\n\n### body\n"
          "- role: generic\n- name: none\n"
          "- code: `groom/groom/legacy.py::broken`\n")
    report = doctor.run(load(repo))
    assert "undecodable-code-symbol" in codes(report)
    finding = next(f for f in report.findings if f.code == "undecodable-code-symbol")
    assert finding.ref == "groom/groom/legacy.py::broken"


def _combined_grounding_refs(repo: Path, name: str) -> str:
    """Write the backing files/dir for all four grounding scenarios under *name*, and return a single multi-target `code:` value citing all four (the comma-separated grammar §4.4's module doc describes) — one `code:` bullet, four independent things to get wrong."""
    from ostler.stamp import digest_file

    write(repo / f"groom/groom/{name}_stale.py", "class Sym:\n    pass\n")
    stale_digest = digest_file(b"class Sym:\n    pass\n    x = 1\n")
    write(repo / f"groom/groom/{name}_unstamped.py", "class Sym:\n    pass\n")
    (repo / f"groom/groom/{name}_dir").mkdir(parents=True, exist_ok=True)
    return (
        f"`groom/groom/{name}_missing.py::Sym`, "
        f"`groom/groom/{name}_dir`, "
        f"`groom/groom/{name}_stale.py::Sym@{stale_digest}`, "
        f"`groom/groom/{name}_unstamped.py::Sym`"
    )


def test_code_grounding_is_uniform_across_previously_ungated_types(repo: Path):
    """`_check_code_grounding` used to skip a whole node whenever its registry type left `code` out of `bullet_by_key` — `screen`, `flow`, `step`, `fixture`, `untyped` — so a dangling, directory, stale or unstamped `code:` citation on any of them went unchecked."""
    docs: dict[str, tuple[str, str]] = {
        "screen": (
            "docs/features/groom/gui/screens/s.md",
            "---\ntype: screen\nslug: s\ntitle: S\n---\n# S\n\n"
            "- route: `/s`\n- requires: none\n- params: none\n- code: {refs}\n",
        ),
        "flow": (
            "docs/features/groom/flows/f.md",
            "---\ntype: flow\nslug: f\ntitle: F\n---\n# F\n\n"
            "- start: begins\n- end: ends\n- code: {refs}\n",
        ),
        "step": (
            "docs/features/groom/concepts/c-step.md",
            "---\ntype: concept\nslug: c-step\ntitle: C\n---\n# C\n\n"
            "## Steps\n\n### boot\n- kind: prepare\n- code: {refs}\n",
        ),
        "fixture": (
            "docs/features/groom/fixtures/fx.md",
            "---\ntype: fixture\nslug: fx\ntitle: FX\n---\n# FX\n\n"
            "- code: {refs}\n\n## Steps\n\n### boot\n- kind: seed\n- run: `groom/boot.sh`\n",
        ),
        "untyped": (
            "docs/features/groom/concepts/c-untyped.md",
            "---\ntype: concept\nslug: c-untyped\ntitle: C\n---\n# C\n\n"
            "## Notes\n\n- code: {refs}\n",
        ),
    }
    for name, (rel_path, template) in docs.items():
        refs = _combined_grounding_refs(repo, name)
        write(repo / rel_path, template.format(refs=refs))

    report = doctor.run(load(repo))
    warns = codes(report, "warn")
    for name in docs:
        for code in ("dangling-code-ref", "directory-code-ref", "stale-citation"):
            hits = [f for f in report.findings
                    if f.code == code and f.ref and f"{name}_" in f.ref]
            assert hits, f"{code} did not fire for {name}"
        unstamped = [f for f in report.findings
                     if f.code == "unstamped-citation" and f.ref and f"{name}_" in f.ref]
        assert unstamped, f"unstamped-citation did not fire for {name}"
    assert "unstamped-citation" in warns


def test_cited_tests_stay_deferred(repo: Path):
    write(repo / "docs/features/groom/gui/screens/changes-view.md", SCREEN)
    write(repo / "docs/features/groom/gui/components/design-system.md", DESIGN_SYSTEM)
    write_cited_code(repo)
    write_stack_runbook(repo)
    report = doctor.run(load(repo))
    assert report.errors == 0, [f.message for f in report.findings if f.severity == "error"]


def test_file_node_loaded(repo: Path):
    write(repo / "docs/features/groom/gui/screens/changes-view.md", SCREEN)
    graph = load(repo)
    screens = graph.ui_nodes_of_type("screen")
    assert len(screens) == 1
    screen = screens[0]
    assert screen.kind == "file"
    assert screen.id == "docs/features/groom/gui/screens/changes-view.md"
    assert screen.title == "Changes view"


def test_section_nodes_loaded_with_anchor_and_meta(repo: Path):
    write(repo / "docs/features/groom/gui/screens/changes-view.md", SCREEN)
    graph = load(repo)
    comps = graph.ui_nodes_of_type("component")
    assert [c.anchor for c in comps] == ["changes-file-row", "single-file-diff"]
    row = comps[0]
    assert row.kind == "section"
    assert row.id == "docs/features/groom/gui/screens/changes-view.md#changes-file-row"
    assert row.meta["selector"] == "`div.tree-file`"
    assert any("design-system.md#tree-node" in href for _, href, _ in row.links)

    inters = graph.ui_nodes_of_type("interaction")
    assert [i.anchor for i in inters] == ["click-file-opens-diff"]
    assert inters[0].meta["trigger"] == "click"


def test_section_node_line_is_file_absolute(repo: Path):
    write(repo / "docs/features/groom/gui/screens/changes-view.md", SCREEN)
    graph = load(repo)
    row = graph.ui_nodes_of_type("component")[0]
    lines = (repo / "docs/features/groom/gui/screens/changes-view.md").read_text().splitlines()
    assert lines[row.line - 1].strip() == "### changes-file-row"


def test_section_nodes_in_a_feature_typed_library(repo: Path):
    write(repo / "docs/features/groom/gui/components/design-system.md",
          "---\ntype: feature\nslug: design-system\ntitle: DS\n---\n# DS\n\n"
          "## Components\n\n### tree-node\n- selector: `div.tree-file`\n- role: treeitem\n"
          "- name: none\n- states: active, default\n")
    graph = load(repo)
    assert [c.anchor for c in graph.ui_nodes_of_type("component")] == ["tree-node"]


def test_list_type_screen(repo: Path):
    write(repo / "docs/features/groom/gui/screens/changes-view.md", SCREEN)
    rows = query.list_entities(load(repo), "screen")
    assert len(rows) == 1
    assert rows[0]["type"] == "screen"
    assert rows[0]["kind"] == "file"


def test_list_type_interaction_reports_path_anchor(repo: Path):
    write(repo / "docs/features/groom/gui/screens/changes-view.md", SCREEN)
    rows = query.list_entities(load(repo), "interaction")
    assert rows[0]["id"].endswith("changes-view.md#click-file-opens-diff")
    assert rows[0]["anchor"] == "click-file-opens-diff"


def test_search_finds_section_node_by_body(repo: Path):
    write(repo / "docs/features/groom/gui/screens/changes-view.md", SCREEN)
    hits = query.search(load(repo), "clear siblings")
    assert any(h.get("anchor") == "click-file-opens-diff" for h in hits)


ENVIRONMENT = """\
---
type: environment
slug: local
title: Local
---
# Local

- selector: `GROOM_BIND=127.0.0.1`
- services:
  - dashboard: `http://127.0.0.1:8787`
- local-only: true
"""

RUNBOOK = """\
---
type: runbook
slug: web
title: Web runbook
---
# Web runbook

- driver: web
- environment: [local](local.md)
- surfaces: [dashboard](../gui/screens/dashboard.md)
- code: `groom/groom/cli.py::serve`

## Steps

### prepare-deps
- kind: prepare
- run: `uv sync`

### serve
- kind: service
- run: `groom serve`
- health: port-bound
"""

DASHBOARD = ("---\ntype: screen\nslug: dashboard\ntitle: Dashboard\n---\n# Dashboard\n\n"
             "- route: `/dashboard`\n- requires: none\n- params: none\n")


def _write_runbook_trio(repo: Path) -> None:
    write(repo / "docs/features/groom/ops/local.md", ENVIRONMENT)
    write(repo / "docs/features/groom/ops/web.md", RUNBOOK)
    write(repo / "docs/features/groom/gui/screens/dashboard.md", DASHBOARD)
    write(repo / "groom/groom/cli.py", "def serve():\n    pass\n")


def test_operational_types_registered():
    rb = present(registry.ui_type("runbook"))
    env = present(registry.ui_type("environment"))
    step = present(registry.ui_type("step"))
    assert rb.kind == "file"
    assert [s.heading for s in rb.required_sections] == ["Steps"]
    assert env.kind == "file"
    assert step.kind == "section" and step.heading == "Steps"
    assert rb.bullet_by_key["driver"].required
    assert step.bullet_by_key["kind"].required


def test_runbook_and_environment_load_as_file_nodes(repo: Path):
    _write_runbook_trio(repo)
    graph = load(repo)
    runbooks = graph.ui_nodes_of_type("runbook")
    assert len(runbooks) == 1
    assert runbooks[0].kind == "file"
    assert runbooks[0].meta.get("driver") == "web"
    assert len(graph.ui_nodes_of_type("environment")) == 1


def test_step_nodes_loaded_under_steps_heading(repo: Path):
    _write_runbook_trio(repo)
    steps = query.list_entities(load(repo), "step")
    assert [s["anchor"] for s in steps] == ["prepare-deps", "serve"]
    assert all(s["id"].endswith(f"web.md#{s['anchor']}") for s in steps)


def test_referentially_complete_runbook_is_green(repo: Path):
    _write_runbook_trio(repo)
    report = doctor.run(load(repo))
    assert report.errors == 0, [f.message for f in report.findings if f.severity == "error"]


def test_runbook_missing_steps_and_driver_is_flagged(repo: Path):
    write(repo / "docs/features/groom/ops/bad.md",
          "---\ntype: runbook\nslug: bad\ntitle: Bad\n---\n# Bad\n\n- environment: [x](x.md)\n")
    report = doctor.run(load(repo))
    bad = {f.code for f in report.findings if f.severity == "error" and "bad.md" in (f.path or "")}
    assert "missing-required-section" in bad
    assert "missing-required-bullet" in bad
    assert "unresolved-relation" in bad


API_SERVER = """\
---
type: server
slug: api
title: API
---
# API

## Endpoints
"""

DEV_CLI = """\
---
type: cli
slug: tally
title: Tally
---
# Tally

## Commands
"""


def _write_driver_surface_book(repo: Path, driver: str, surface_md: str | None,
                                surface_rel: str | None) -> None:
    """A minimal runbook wired to at most one surface node, so `no-drivable-surface` can be exercised without dragging in an entire app's fixtures."""
    write(repo / "docs/features/groom/ops/local.md", ENVIRONMENT)
    surfaces_line = f"- surfaces: [surface]({surface_rel})\n" if surface_rel else ""
    write(repo / "docs/features/groom/ops/rb.md", (
        "---\ntype: runbook\nslug: rb\ntitle: RB\n---\n# RB\n\n"
        f"- driver: {driver}\n- environment: [local](local.md)\n{surfaces_line}\n"
        "## Steps\n\n### serve\n- kind: service\n- run: `run`\n"
    ))
    if surface_md is not None and surface_rel is not None:
        write(repo / "docs/features/groom" / surface_rel.replace("../", ""), surface_md)


def test_web_driver_over_server_only_surface_warns(repo: Path):
    _write_driver_surface_book(repo, "web", API_SERVER, "../http/api.md")
    report = doctor.run(load(repo))
    warns = {f.code for f in report.findings if f.severity == "warn"}
    assert "no-drivable-surface" in warns


def test_web_driver_over_screen_surface_is_clean(repo: Path):
    _write_runbook_trio(repo)
    report = doctor.run(load(repo))
    warns = {f.code for f in report.findings if f.severity == "warn"}
    assert "no-drivable-surface" not in warns


def test_iac_driver_with_no_surfaces_is_clean(repo: Path):
    _write_driver_surface_book(repo, "iac", None, None)
    report = doctor.run(load(repo))
    warns = {f.code for f in report.findings if f.severity == "warn"}
    assert "no-drivable-surface" not in warns


def test_runbook_with_no_driver_is_clean_on_no_drivable_surface(repo: Path):
    write(repo / "docs/features/groom/ops/bad.md",
          "---\ntype: runbook\nslug: bad\ntitle: Bad\n---\n# Bad\n\n- environment: [x](x.md)\n")
    report = doctor.run(load(repo))
    warns = {f.code for f in report.findings if f.severity == "warn"}
    assert "no-drivable-surface" not in warns


def test_cli_driver_over_cli_surface_is_clean(repo: Path):
    _write_driver_surface_book(repo, "cli", DEV_CLI, "../cli/tally.md")
    report = doctor.run(load(repo))
    warns = {f.code for f in report.findings if f.severity == "warn"}
    assert "no-drivable-surface" not in warns


def test_web_driver_with_no_surfaces_at_all_warns(repo: Path):
    _write_driver_surface_book(repo, "web", None, None)
    report = doctor.run(load(repo))
    warns = {f.code for f in report.findings if f.severity == "warn"}
    assert "no-drivable-surface" in warns


def test_cli_driver_over_server_surface_warns(repo: Path):
    _write_driver_surface_book(repo, "cli", API_SERVER, "../http/api.md")
    report = doctor.run(load(repo))
    warns = {f.code for f in report.findings if f.severity == "warn"}
    assert "no-drivable-surface" in warns


def test_every_legal_driver_value_is_clean_on_unknown_driver(repo: Path):
    for driver in drivers.DRIVERS:
        _write_driver_surface_book(repo, driver, None, None)
        report = doctor.run(load(repo))
        errors = {f.code for f in report.findings if f.severity == "error"}
        assert "unknown-driver" not in errors, driver


def test_a_misspelt_driver_raises_exactly_one_unknown_driver_error(repo: Path):
    _write_driver_surface_book(repo, "htttp", None, None)
    report = doctor.run(load(repo))
    found = [f for f in report.findings if f.code == "unknown-driver"]
    assert len(found) == 1
    assert found[0].severity == "error"
    assert "htttp" in found[0].message
    for driver in drivers.DRIVERS:
        assert driver in found[0].message


def test_a_runbook_with_no_driver_bullet_raises_no_unknown_driver(repo: Path):
    write(repo / "docs/features/groom/ops/bad.md",
          "---\ntype: runbook\nslug: bad\ntitle: Bad\n---\n# Bad\n\n- environment: [x](x.md)\n")
    report = doctor.run(load(repo))
    errors = {f.code for f in report.findings if f.severity == "error"}
    assert "unknown-driver" not in errors


def _write_two_runbook_book(repo: Path, driver_a: str, driver_b: str) -> None:
    """Two runbooks in one feature directory, both `surfaces:`-linked into the same server node — the shape a legitimate dev-local runbook takes alongside the deployed one, and the only shape `reach.surface_driver` ever has two drivers to choose between."""
    write(repo / "docs/features/groom/ops/local.md", ENVIRONMENT)
    write(repo / "docs/features/groom/http/api.md", API_SERVER)
    write(repo / "docs/features/groom/ops/deployed.md", (
        "---\ntype: runbook\nslug: deployed\ntitle: Deployed\n---\n# Deployed\n\n"
        f"- driver: {driver_a}\n- environment: [local](local.md)\n"
        "- surfaces: [api](../http/api.md)\n\n"
        "## Steps\n\n### serve\n- kind: service\n- run: `run`\n"
    ))
    write(repo / "docs/features/groom/ops/local-cli.md", (
        "---\ntype: runbook\nslug: local-cli\ntitle: Local CLI\n---\n# Local CLI\n\n"
        f"- driver: {driver_b}\n- environment: [local](local.md)\n"
        "- surfaces: [api](../http/api.md)\n\n"
        "## Steps\n\n### serve\n- kind: service\n- run: `run --local`\n"
    ))


@pytest.mark.parametrize(("driver_a", "driver_b"), [("http", "cli"), ("cli", "http")])
def test_two_runbooks_naming_one_surface_settle_on_the_earlier_driver_in_section_4_1(
        repo: Path, driver_a: str, driver_b: str):
    _write_two_runbook_book(repo, driver_a, driver_b)
    dump = graph.build(load(repo))
    assert reach.surface_driver(dump, "groom") == "http"
    surface_errors = [f for f in doctor.run(load(repo)).findings
                      if f.severity == "error" and f.ref == "groom"]
    assert not surface_errors


def test_two_runbooks_stating_the_same_driver_settle_on_it(repo: Path):
    _write_two_runbook_book(repo, "http", "http")
    dump = graph.build(load(repo))
    assert reach.surface_driver(dump, "groom") == "http"


def test_a_sole_runbook_settles_its_own_driver(repo: Path):
    _write_driver_surface_book(repo, "cli", DEV_CLI, "../cli/tally.md")
    dump = graph.build(load(repo))
    assert reach.surface_driver(dump, "groom") == "cli"


def _write_two_mobile_runbook_book(repo: Path, bundle_id_a: str | None,
                                    bundle_id_b: str | None) -> None:
    """Two runbooks in one feature directory, both `surfaces:`-linked into the same screen node and both `driver: mobile`, each stating its own `bundle-id:` (or none, when the argument is None)."""
    write(repo / "docs/features/groom/ops/local.md", ENVIRONMENT)
    write(repo / "docs/features/groom/gui/screens/dashboard.md", DASHBOARD)
    bundle_a = f"- bundle-id: {bundle_id_a}\n" if bundle_id_a else ""
    bundle_b = f"- bundle-id: {bundle_id_b}\n" if bundle_id_b else ""
    write(repo / "docs/features/groom/ops/legacy.md", (
        "---\ntype: runbook\nslug: legacy\ntitle: Legacy\n---\n# Legacy\n\n"
        "- driver: mobile\n- environment: [local](local.md)\n"
        "- surfaces: [dashboard](../gui/screens/dashboard.md)\n"
        f"{bundle_a}\n"
        "## Steps\n\n### serve\n- kind: service\n- run: `run`\n"
    ))
    write(repo / "docs/features/groom/ops/current.md", (
        "---\ntype: runbook\nslug: current\ntitle: Current\n---\n# Current\n\n"
        "- driver: mobile\n- environment: [local](local.md)\n"
        "- surfaces: [dashboard](../gui/screens/dashboard.md)\n"
        f"{bundle_b}\n"
        "## Steps\n\n### serve\n- kind: service\n- run: `run --current`\n"
    ))


def test_two_runbooks_stating_different_bundle_ids_settle_by_node_id(repo: Path):
    _write_two_mobile_runbook_book(repo, "com.example.legacy", "com.example.current")
    dump = graph.build(load(repo))
    assert reach.surface_bundle_id(dump, "groom") == "com.example.current"


def test_a_bundle_id_falls_through_to_the_next_runbook_when_the_first_is_silent(repo: Path):
    _write_two_mobile_runbook_book(repo, "com.example.legacy", None)
    dump = graph.build(load(repo))
    assert reach.surface_bundle_id(dump, "groom") == "com.example.legacy"


def test_two_runbooks_stating_the_same_bundle_id_settle_on_it(repo: Path):
    """Non-vacuity for the tiebreak above: one value stated twice is not a choice, and the answer must still be that value."""
    _write_two_mobile_runbook_book(repo, "com.example.legacy", "com.example.legacy")
    dump = graph.build(load(repo))
    assert reach.surface_bundle_id(dump, "groom") == "com.example.legacy"


def test_a_sole_runbook_settles_its_own_bundle_id(repo: Path):
    """Real-book shape: only one runbook names this surface at all."""
    write(repo / "docs/features/groom/ops/local.md", ENVIRONMENT)
    write(repo / "docs/features/groom/gui/screens/dashboard.md", DASHBOARD)
    write(repo / "docs/features/groom/ops/web.md", (
        "---\ntype: runbook\nslug: web\ntitle: Web runbook\n---\n# Web runbook\n\n"
        "- driver: mobile\n- environment: [local](local.md)\n"
        "- surfaces: [dashboard](../gui/screens/dashboard.md)\n"
        "- bundle-id: com.example.mobile-app\n\n"
        "## Steps\n\n### serve\n- kind: service\n- run: `run`\n"
    ))
    dump = graph.build(load(repo))
    assert reach.surface_bundle_id(dump, "groom") == "com.example.mobile-app"


def test_a_surface_with_no_bundle_id_at_all_resolves_to_none(repo: Path):
    """The trio's RUNBOOK states no `bundle-id:`, so nothing is a candidate."""
    _write_runbook_trio(repo)
    dump = graph.build(load(repo))
    assert reach.surface_bundle_id(dump, "groom") is None


SETTINGS_SCREEN = ("---\ntype: screen\nslug: settings\ntitle: Settings\n---\n# Settings\n\n"
                    "- route: `/settings`\n- requires: none\n- params: none\n")


def _write_two_launch_screen_runbook_book(repo: Path, launch_a: str | None,
                                           launch_b: str | None) -> None:
    """Two runbooks in one feature directory, both `surfaces:`-linked into the same screen node, each stating its own `launch-screen:` (or none, when the argument is None)."""
    write(repo / "docs/features/groom/ops/local.md", ENVIRONMENT)
    write(repo / "docs/features/groom/gui/screens/dashboard.md", DASHBOARD)
    write(repo / "docs/features/groom/gui/screens/settings.md", SETTINGS_SCREEN)
    line_a = f"- launch-screen: [{launch_a}](../gui/screens/{launch_a}.md)\n" if launch_a else ""
    line_b = f"- launch-screen: [{launch_b}](../gui/screens/{launch_b}.md)\n" if launch_b else ""
    write(repo / "docs/features/groom/ops/legacy.md", (
        "---\ntype: runbook\nslug: legacy\ntitle: Legacy\n---\n# Legacy\n\n"
        "- driver: mobile\n- environment: [local](local.md)\n"
        "- surfaces: [dashboard](../gui/screens/dashboard.md)\n"
        "- bundle-id: com.example.mobile-app\n"
        f"{line_a}\n"
        "## Steps\n\n### serve\n- kind: service\n- run: `run`\n"
    ))
    write(repo / "docs/features/groom/ops/current.md", (
        "---\ntype: runbook\nslug: current\ntitle: Current\n---\n# Current\n\n"
        "- driver: mobile\n- environment: [local](local.md)\n"
        "- surfaces: [dashboard](../gui/screens/dashboard.md)\n"
        "- bundle-id: com.example.mobile-app\n"
        f"{line_b}\n"
        "## Steps\n\n### serve\n- kind: service\n- run: `run --current`\n"
    ))


def test_two_runbooks_stating_different_launch_screens_settle_by_node_id(repo: Path):
    _write_two_launch_screen_runbook_book(repo, "dashboard", "settings")
    dump = graph.build(load(repo))
    assert reach.surface_launch_screen(dump, "groom") == (
        "docs/features/groom/gui/screens/settings.md"
    )


def test_a_launch_screen_falls_through_to_the_next_runbook_when_the_first_is_silent(repo: Path):
    _write_two_launch_screen_runbook_book(repo, "dashboard", None)
    dump = graph.build(load(repo))
    assert reach.surface_launch_screen(dump, "groom") == (
        "docs/features/groom/gui/screens/dashboard.md"
    )


def test_a_sole_runbook_settles_its_own_launch_screen(repo: Path):
    """Real-book shape: only one runbook names this surface at all — the same shape `test_a_sole_runbook_settles_its_own_bundle_id` pins for `bundle-id:`."""
    write(repo / "docs/features/groom/ops/local.md", ENVIRONMENT)
    write(repo / "docs/features/groom/gui/screens/dashboard.md", DASHBOARD)
    write(repo / "docs/features/groom/ops/web.md", (
        "---\ntype: runbook\nslug: web\ntitle: Web runbook\n---\n# Web runbook\n\n"
        "- driver: mobile\n- environment: [local](local.md)\n"
        "- surfaces: [dashboard](../gui/screens/dashboard.md)\n"
        "- bundle-id: com.example.mobile-app\n"
        "- launch-screen: [dashboard](../gui/screens/dashboard.md)\n\n"
        "## Steps\n\n### serve\n- kind: service\n- run: `run`\n"
    ))
    dump = graph.build(load(repo))
    assert reach.surface_launch_screen(dump, "groom") == (
        "docs/features/groom/gui/screens/dashboard.md"
    )


def test_a_surface_with_no_launch_screen_at_all_resolves_to_none(repo: Path):
    """The trio's RUNBOOK states no `launch-screen:`, so nothing is a candidate."""
    _write_runbook_trio(repo)
    dump = graph.build(load(repo))
    assert reach.surface_launch_screen(dump, "groom") is None


def test_a_surface_carrying_a_screen_resolves_its_driver_for_both_grammar_readers(repo: Path):
    _write_two_runbook_book(repo, "cli", "web")
    write(repo / "docs/features/groom/gui/screens/dashboard.md", DASHBOARD)
    dump = graph.build(load(repo))
    assert reach.surface_driver(dump, "groom") == "web"
    codes_seen = codes(doctor.run(load(repo)))
    assert "unknown-driver" not in codes_seen


def test_a_same_size_rewrite_is_not_served_from_the_parse_cache(repo: Path):
    doc = repo / "docs/features/web/login.md"
    write(doc, "---\ntype: screen\n---\n\n# Login\n\n## Components\n\n### aaa\n")
    assert present(load(repo).find_ui_node("docs/features/web/login.md#aaa")).title == "aaa"

    write(doc, "---\ntype: screen\n---\n\n# Login\n\n## Components\n\n### bbb\n")
    reloaded = load(repo)
    assert reloaded.find_ui_node("docs/features/web/login.md#aaa") is None
    assert present(reloaded.find_ui_node("docs/features/web/login.md#bbb")).title == "bbb"


def _write_same_as_concepts(repo: Path, texts: list[str | None]) -> None:
    """A chain of concepts `notify-0`, `notify-1`, ..."""
    n = len(texts)
    for i, text in enumerate(texts):
        same_as = "".join(
            f"- same-as: [notify-{j}](notify-{j}.md)\n"
            for j in (i - 1, i + 1) if 0 <= j < n
        )
        consistency = f"- consistency: {text}\n" if text is not None else ""
        write(repo / f"docs/features/groom/concepts/notify-{i}.md",
              f"---\ntype: concept\nslug: notify-{i}\ntitle: Notify {i}\n---\n"
              f"# Notify {i}\n\n{same_as}{consistency}")


def test_same_as_disagreement_on_two_different_values(repo: Path):
    _write_same_as_concepts(repo, ["at least once", "exactly once"])
    hits = [f for f in doctor.run(load(repo)).findings if f.code == "same-as-disagreement"]
    assert len(hits) == 1
    assert hits[0].severity == "error"
    assert "notify-0" in hits[0].message and "notify-1" in hits[0].message
    assert "at least once" in hits[0].message and "exactly once" in hits[0].message
    assert set(hits[0].related) == {"docs/features/groom/concepts/notify-0.md",
                                     "docs/features/groom/concepts/notify-1.md"}


def test_same_as_disagreement_silent_on_identical_values(repo: Path):
    _write_same_as_concepts(repo, ["exactly once", "exactly once"])
    assert "same-as-disagreement" not in codes(doctor.run(load(repo)))


def test_same_as_disagreement_silent_when_one_side_omits_the_key(repo: Path):
    _write_same_as_concepts(repo, ["exactly once", None])
    assert "same-as-disagreement" not in codes(doctor.run(load(repo)))


def test_same_as_disagreement_silent_on_same_values_different_order(repo: Path):
    write(repo / "docs/features/groom/concepts/notify-0.md",
          "---\ntype: concept\nslug: notify-0\ntitle: Notify 0\n---\n# Notify 0\n\n"
          "- same-as: [notify-1](notify-1.md)\n"
          "- consistency: at least once\n"
          "- consistency: exactly once\n")
    write(repo / "docs/features/groom/concepts/notify-1.md",
          "---\ntype: concept\nslug: notify-1\ntitle: Notify 1\n---\n# Notify 1\n\n"
          "- same-as: [notify-0](notify-0.md)\n"
          "- consistency: exactly once\n"
          "- consistency: at least once\n")
    assert "same-as-disagreement" not in codes(doctor.run(load(repo)))


def test_same_as_disagreement_one_finding_for_a_three_member_family(repo: Path):
    _write_same_as_concepts(repo, ["at least once", "exactly once", "exactly once"])
    hits = [f for f in doctor.run(load(repo)).findings if f.code == "same-as-disagreement"]
    assert len(hits) == 1
    assert set(hits[0].related) == {"docs/features/groom/concepts/notify-0.md",
                                     "docs/features/groom/concepts/notify-1.md",
                                     "docs/features/groom/concepts/notify-2.md"}


def _write_two_origin_book(repo: Path, server_url: str, runbook_url: str | None) -> None:
    """A `server` and a `runbook` that both state the surface's address, so `entry_origin` has two sources to rank — the only shape where the ranking is observable."""
    write(repo / "docs/features/groom/ops/local.md", ENVIRONMENT)
    write(repo / "docs/features/groom/http/api.md", (
        "---\ntype: server\nslug: api\ntitle: API\n---\n# API\n\n"
        f"- entry-url: {server_url}\n\n## Endpoints\n"
    ))
    entry = f"- entry-url: {runbook_url}\n" if runbook_url else ""
    write(repo / "docs/features/groom/ops/deployed.md", (
        "---\ntype: runbook\nslug: deployed\ntitle: Deployed\n---\n# Deployed\n\n"
        "- driver: http\n- environment: [local](local.md)\n"
        f"{entry}"
        "- surfaces: [api](../http/api.md)\n\n"
        "## Steps\n\n### serve\n- kind: service\n- run: `run`\n"
    ))


def test_a_runbook_entry_url_outranks_the_servers(repo: Path):
    _write_two_origin_book(repo, "http://127.0.0.1:8787", "http://127.0.0.1:9999")
    dump = graph.build(load(repo))
    assert reach.entry_origin(dump, "groom") == "http://127.0.0.1:9999"


def test_a_surface_with_no_runbook_entry_url_falls_back_to_the_server(repo: Path):
    _write_two_origin_book(repo, "http://127.0.0.1:8787", None)
    dump = graph.build(load(repo))
    assert reach.entry_origin(dump, "groom") == "http://127.0.0.1:8787"


def test_entry_origin_keeps_only_the_origin_of_what_a_source_states(repo: Path):
    _write_two_origin_book(repo, "http://127.0.0.1:8787/api", "http://127.0.0.1:9999/v2")
    dump = graph.build(load(repo))
    assert reach.entry_origin(dump, "groom") == "http://127.0.0.1:9999"
