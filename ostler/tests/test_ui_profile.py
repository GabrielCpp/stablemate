"""OKF UI profile — the eleven UI/concept node types (docs/okf-ui-profile.md).

Covers registry recognition + conformance dispatch (§3/§5), the section-node loader and
list/search (§4/§10), `fmt` (§8), `scaffold` (§9), link resolution + located findings (§6),
`trace` (§10), and the mandatory linter (§7).
"""

from __future__ import annotations

from pathlib import Path

from ostler import doctor, query, registry
from ostler.model import load

from conftest import write


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def codes(report, severity="error"):
    return {f.code for f in report.findings if f.severity == severity}


SCREEN = """\
---
type: screen
slug: changes-view
title: Changes view
---
# Changes view

Groups every worker's working-tree diff per repo.

## Components

### changes-file-row
- selector: `.tree-file`
- extends: [tree-node](../components/design-system.md#tree-node)
- code: `groom/groom/render.py::_changes_worker`

A leaf of the per-worker file tree.

## Interactions

### click-file-opens-diff
- on: [changes-file-row](#changes-file-row)
- trigger: click
- when: `mode == changes`
- does:
  - state: mark row `.active`, clear siblings
  - dom: render single-file diff
- code: `groom/groom/templates/dashboard.html::wireChanges`
- verify: `groom/tests/test_render.py::test_changes_groups_diffs_per_repo`
"""


# ---------------------------------------------------------------------------
# §3 — registry recognition
# ---------------------------------------------------------------------------
def test_ui_types_registered():
    assert set(registry.UI_TYPES_BY_NAME) == {
        "screen", "component", "interaction", "cli", "command", "server", "endpoint",
        "invocation", "flow", "concept", "format",
        "method", "field",   # nested typed sections (Methods/Fields containers + inline `type:`)
        "runbook", "environment", "step",   # operational profile (docs/okf-runbook.md)
        "untyped",           # any other heading, promoted so its links/hierarchy are captured
    }


def test_heading_to_type_map():
    assert registry.UI_HEADING_TO_TYPE == {
        "Components": "component", "Commands": "command", "Endpoints": "endpoint",
        "Interactions": "interaction", "Invocations": "invocation",
        "Methods": "method", "Fields": "field",
        "Steps": "step",   # operational profile: a runbook's ordered boot steps
    }


def test_is_known_type():
    assert registry.is_known_type("screen")
    assert registry.is_known_type("concept")
    assert registry.is_known_type("feature")   # built-in still known
    assert not registry.is_known_type("bogus")
    assert not registry.is_known_type("")


def test_ui_type_lookup_by_base():
    assert registry.ui_type("interaction").heading == "Interactions"
    assert registry.ui_type("screen").kind == "file"
    assert registry.ui_type("epic") is None


# ---------------------------------------------------------------------------
# §5 — conformance dispatch by declared type (the feature.schema.json gotcha)
# ---------------------------------------------------------------------------
DESIGN_SYSTEM = """\
---
type: feature
slug: design-system
title: DS
---
# DS

## Components

### tree-node
- selector: `.tree-file`
"""


def test_screen_doc_under_features_keeps_doctor_green(repo: Path):
    write(repo / "docs/features/groom/gui/screens/changes-view.md", SCREEN)
    # the `extends:` target must exist for the referentially-complete doc to be green
    write(repo / "docs/features/groom/gui/components/design-system.md", DESIGN_SYSTEM)
    report = doctor.run(load(repo))
    # No `schema` finding: a type:screen doc is validated as a screen (no schema),
    # NOT double-checked against feature.schema.json.
    schema_hits = [f for f in report.findings
                   if f.code == "schema" and "changes-view.md" in f.message]
    assert schema_hits == []
    assert report.errors == 0, [f.message for f in report.findings if f.severity == "error"]


def test_real_feature_still_schema_checked(repo: Path):
    # A genuine feature missing required `title` still warns against feature.schema.json.
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


# ---------------------------------------------------------------------------
# §4 — the section-node loader
# ---------------------------------------------------------------------------
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
    assert [c.anchor for c in comps] == ["changes-file-row"]
    row = comps[0]
    assert row.kind == "section"
    assert row.id == "docs/features/groom/gui/screens/changes-view.md#changes-file-row"
    assert row.meta["selector"] == "`.tree-file`"
    # its extends: link is captured
    assert any("design-system.md#tree-node" in href for _, href in row.links)

    inters = graph.ui_nodes_of_type("interaction")
    assert [i.anchor for i in inters] == ["click-file-opens-diff"]
    assert inters[0].meta["trigger"] == "click"


def test_section_node_line_is_file_absolute(repo: Path):
    write(repo / "docs/features/groom/gui/screens/changes-view.md", SCREEN)
    graph = load(repo)
    row = graph.ui_nodes_of_type("component")[0]
    # The `### changes-file-row` line resolves back to the exact source line.
    lines = (repo / "docs/features/groom/gui/screens/changes-view.md").read_text().splitlines()
    assert lines[row.line - 1].strip() == "### changes-file-row"


def test_section_nodes_in_a_feature_typed_library(repo: Path):
    # A shared component library is `type: feature` but still holds section-level components.
    write(repo / "docs/features/groom/gui/components/design-system.md",
          "---\ntype: feature\nslug: design-system\ntitle: DS\n---\n# DS\n\n"
          "## Components\n\n### tree-node\n- selector: `.tree-file`\n- states: active, default\n")
    graph = load(repo)
    assert [c.anchor for c in graph.ui_nodes_of_type("component")] == ["tree-node"]


# ---------------------------------------------------------------------------
# §10 — list / search
# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# operational profile — runbook / environment / step (docs/okf-runbook.md)
# ---------------------------------------------------------------------------
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
- provenance: derived

### serve
- kind: service
- run: `groom serve`
- health: port-bound
- provenance: derived
"""

DASHBOARD = "---\ntype: screen\nslug: dashboard\ntitle: Dashboard\n---\n# Dashboard\n"


def _write_runbook_trio(repo: Path) -> None:
    write(repo / "docs/features/groom/ops/local.md", ENVIRONMENT)
    write(repo / "docs/features/groom/ops/web.md", RUNBOOK)
    write(repo / "docs/features/groom/gui/screens/dashboard.md", DASHBOARD)


def test_operational_types_registered():
    rb, env, step = (registry.ui_type("runbook"), registry.ui_type("environment"),
                     registry.ui_type("step"))
    assert rb.kind == "file" and rb.required_sections == ("Steps",)
    assert env.kind == "file"
    assert step.kind == "section" and step.heading == "Steps"
    # the defining bullets are required so `doctor` gates on them
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
    assert "missing-required-section" in bad   # no `## Steps`
    assert "missing-required-bullet" in bad     # no `driver:`
    assert "unresolved-relation" in bad         # `environment:` link is broken
