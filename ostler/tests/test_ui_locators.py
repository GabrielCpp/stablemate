"""`ostler locators` — the derived Playwright mapping, and the two ways it stops being one-to-one."""

from __future__ import annotations

from pathlib import Path

from ostler import doctor, graph, locators
from ostler.model import load

from conftest import write

SCREENS = "docs/features/web/gui/screens"
DASH = f"{SCREENS}/dashboard.md"

HEAD = """\
---
type: screen
slug: dashboard
title: Dashboard
---
# Dashboard

- route: `/`
- requires: none
- params: none

## Components
"""


def _screen(*components: str) -> str:
    return HEAD + "\n" + "\n".join(components)


SAVE = """\
### save-button
- selector: `.btn-save`
- role: button
- name: Save
- keyboard: `enter`
"""

CANCEL = """\
### cancel-button
- selector: `.btn-cancel`
- role: button
- name: Cancel
"""

# Same role and the same accessible name as SAVE — one locator, two controls.
DUPLICATE_SAVE = """\
### footer-save-button
- selector: `.footer .btn-save`
- role: button
- name: Save
"""

# Operable, but nothing to announce it by.
UNNAMED = """\
### icon-button
- selector: `.icon`
- role: button
- name: none
"""

# No role at all: locatable only by its CSS selector, and only by a machine.
CSS_ONLY = """\
### legacy-widget
- selector: `#legacy`
- role: none
- name: none
"""

# Nothing to point at in either vocabulary.
NOTHING = """\
### ghost
- role: none
- name: none
"""


def _build(repo: Path, body: str):
    write(repo / DASH, body)
    return graph.build(load(repo), surface="web")


def test_role_and_name_become_a_get_by_role_call(repo: Path):
    data = _build(repo, _screen(SAVE))
    entry = locators.screen_locators(data)[0]["locators"][0]
    assert entry["locator"] == 'getByRole("button", { name: "Save", exact: true })'
    assert entry["strategy"] == "role"
    assert entry["keyboard"] == "enter"  # the code fence is presentation, not content


def test_selector_is_a_fallback_and_is_marked_as_one(repo: Path):
    """A CSS locator works, so it is not an error — but it is not the a11y contract either."""
    data = _build(repo, _screen(CSS_ONLY))
    entry = locators.screen_locators(data)[0]["locators"][0]
    assert entry["locator"] == 'locator("#legacy")'
    assert entry["strategy"] == "css"


def test_a_node_with_neither_is_unlocatable(repo: Path):
    data = _build(repo, _screen(NOTHING))
    entry = locators.screen_locators(data)[0]["locators"][0]
    assert entry["strategy"] == "none" and entry["locator"] == ""
    assert locators.build(load(repo), surface="web")["counts"]["unlocatable"] == 1


def test_quotes_in_an_accessible_name_are_escaped(repo: Path):
    """The locator is emitted as JS source, so a name with a quote must not end the string."""
    data = _build(repo, _screen('### q\n- role: button\n- name: Say "hi"\n'))
    assert locators.screen_locators(data)[0]["locators"][0]["locator"] == (
        'getByRole("button", { name: "Say \\"hi\\"", exact: true })')


def test_distinct_names_do_not_collide(repo: Path):
    assert locators.collisions(_build(repo, _screen(SAVE, CANCEL))) == []


def test_two_controls_sharing_role_and_name_collide(repo: Path):
    """The reverse direction of one-to-one: this locator would match two nodes, not one."""
    collisions = locators.collisions(_build(repo, _screen(SAVE, DUPLICATE_SAVE)))
    assert len(collisions) == 1
    assert collisions[0]["role"] == "button" and collisions[0]["name"] == "Save"
    assert [n.split("#")[-1] for n in collisions[0]["nodes"]] == [
        "footer-save-button", "save-button"]


def test_an_interaction_may_share_its_components_locator(repo: Path):
    """An interaction's role/name describe the control it fires `on:` — matching it is the point."""
    body = _screen(SAVE) + """
## Interactions

### click-save
- on: [save-button](#save-button)
- trigger: click
- role: button
- name: Save
- keyboard: `enter`
- does:
  - state: persist the draft
"""
    assert locators.collisions(_build(repo, body)) == []


def test_two_interactions_on_one_control_do_not_collide(repo: Path):
    """A click and a keyboard shortcut on the same button are two behaviors, one locator."""
    body = _screen(SAVE) + """
## Interactions

### click-save
- on: [save-button](#save-button)
- trigger: click
- role: button
- name: Save
- keyboard: none
- does:
  - state: persist the draft

### keyboard-save
- on: [save-button](#save-button)
- trigger: keydown
- role: button
- name: Save
- keyboard: `ctrl+s`
- does:
  - state: persist the draft
"""
    assert locators.collisions(_build(repo, body)) == []


def test_unnamed_interactive_is_found(repo: Path):
    unnamed = locators.unnamed_interactives(_build(repo, _screen(UNNAMED)))
    assert [u["role"] for u in unnamed] == ["button"]


def test_a_non_interactive_role_may_be_unnamed(repo: Path):
    """`name: none` on a decorative element is a legitimate claim, not a defect to flag."""
    data = _build(repo, _screen("### divider\n- role: separator\n- name: none\n"))
    assert locators.unnamed_interactives(data) == []


def _codes(repo: Path, severity: str = "error"):
    return [f.code for f in doctor.run(load(repo)).findings if f.severity == severity]


def test_doctor_errors_on_an_ambiguous_locator(repo: Path):
    _build(repo, _screen(SAVE, DUPLICATE_SAVE))
    codes = _codes(repo)
    # one per node, so each offending doc gets the finding on its own line
    assert codes.count("ambiguous-locator") == 2


def test_doctor_errors_on_an_unnamed_interactive(repo: Path):
    _build(repo, _screen(UNNAMED))
    assert "unnamed-interactive" in _codes(repo)


def test_doctor_is_green_on_a_clean_screen(repo: Path):
    _build(repo, _screen(SAVE, CANCEL))
    assert "ambiguous-locator" not in _codes(repo)
    assert "unnamed-interactive" not in _codes(repo)


def test_missing_role_is_a_required_bullet_finding(repo: Path):
    """The forward half of one-to-one is enforced by the registry, not by this module."""
    _build(repo, _screen("### bare\n- selector: `.bare`\n"))
    assert "missing-required-bullet" in _codes(repo)


def test_a_role_with_prose_stapled_to_it_is_not_a_role(repo: Path):
    """The common real-world shape: a true role, plus a parenthetical the locator cannot use."""
    data = _build(repo, _screen(
        "### spinner\n- selector: `.spin`\n- role: `progressbar` (implicit MUI role)\n- name: none\n"))
    assert [b["role"] for b in locators.invalid_roles(data)] == [
        "`progressbar` (implicit MUI role)"]
    # and it falls back rather than emitting a getByRole that matches nothing
    assert locators.screen_locators(data)[0]["locators"][0]["strategy"] == "css"


def test_doctor_errors_on_an_invalid_role(repo: Path):
    _build(repo, _screen("### spinner\n- role: a spinny thing\n- name: none\n"))
    assert "invalid-role" in _codes(repo)


def test_every_interactive_role_is_a_real_aria_role():
    """The two lists must not drift: an interactive role outside ARIA_ROLES could never be set."""
    assert locators.INTERACTIVE_ROLES <= locators.ARIA_ROLES


def test_doctor_builds_the_ui_graph_once(repo: Path, monkeypatch):
    """Reachability and locators share one build.

    Each rebuild resolves every node in the book, so on a large book a per-check rebuild costs more
    than every other check combined — and the cost is invisible in a small fixture, which is why it
    is pinned here rather than left to notice in production.
    """
    from ostler import graph as graph_mod

    _build(repo, _screen(SAVE, CANCEL))
    calls = []
    real = graph_mod.build

    def counting(*a, **kw):
        calls.append(kw.get("surface"))
        return real(*a, **kw)

    monkeypatch.setattr(graph_mod, "build", counting)
    doctor.run(load(repo))

    # one unscoped build for both checks; per-surface scoping is a filter, not a rebuild
    assert calls.count(None) == 1
    assert [c for c in calls if c is not None] == []


LIB = "docs/features/web/gui/components/app-shell.md"

SHARED = """\
---
type: feature
slug: app-shell
title: App shell
---
# App shell

## Components

### navbar-home-link
- selector: `.nav-home`
- role: `link` — renders an `<a>` via ListItemButton
- name: Home
"""


def test_a_shared_component_is_checked_too(repo: Path):
    """A navbar lives in a component library, not on a screen — and renders on every screen.

    Scoping the locator checks to screen docs would exempt exactly the controls with the widest
    blast radius, which is the opposite of the intent.
    """
    write(repo / LIB, SHARED)
    _build(repo, _screen(SAVE))
    bad = locators.invalid_roles(graph.build(load(repo), surface="web"))
    assert [b["node"].split("#")[-1] for b in bad] == ["navbar-home-link"]
    assert "invalid-role" in _codes(repo)


def test_shared_components_collide_within_their_own_file(repo: Path):
    """Two library components sharing role+name collide; the same pair on a screen does not."""
    write(repo / LIB, SHARED.replace(
        "- role: `link` — renders an `<a>` via ListItemButton", "- role: link")
        + "\n### navbar-home-dup\n- role: link\n- name: Home\n")
    _build(repo, _screen(SAVE))
    collisions = locators.collisions(graph.build(load(repo), surface="web"))
    assert len(collisions) == 1
    assert collisions[0]["screen"] == LIB


def test_a_shared_base_may_be_unnamed_but_its_consumers_may_not(repo: Path):
    """`extends:` marks a template whose name each consumer supplies — not a rendered control."""
    write(repo / LIB, """\
---
type: feature
slug: app-shell
title: App shell
---
# App shell

## Components

### row-base
- role: treeitem
- name: none
""")
    write(repo / DASH, _screen("""\
### dash-row
- role: treeitem
- name: none
- extends: [row-base](../components/app-shell.md#row-base)
"""))
    unnamed = locators.unnamed_interactives(graph.build(load(repo), surface="web"))
    # the base is exempt; the screen's concrete row still owes a name
    assert [u["node"].split("#")[-1] for u in unnamed] == ["dash-row"]


def test_na_is_the_same_claim_as_none(repo: Path):
    """`n/a` is what authors actually write, and reading it as a name is a silent wrong answer.

    A `getByRole("menu", {name: "n/a"})` hunts for a control literally called "n/a" and fails at
    runtime looking like the app's fault — strictly worse than the bullet having been left blank.
    """
    data = _build(repo, _screen("### m\n- selector: `.m`\n- role: menu\n- name: n/a\n"))
    entry = locators.screen_locators(data)[0]["locators"][0]
    assert entry["locator"] == 'getByRole("menu")'
    assert "n/a" not in entry["locator"]


def test_na_role_is_the_empty_sentinel_not_an_invalid_role(repo: Path):
    data = _build(repo, _screen("### w\n- selector: `.w`\n- role: n/a\n- name: n/a\n"))
    assert locators.invalid_roles(data) == []
    assert locators.screen_locators(data)[0]["locators"][0]["strategy"] == "css"


def test_an_unnamed_interactive_is_still_caught_when_spelled_na(repo: Path):
    """The synonym must not become a way to smuggle an unlabeled control past the check."""
    data = _build(repo, _screen("### b\n- selector: `.b`\n- role: button\n- name: n/a\n"))
    assert [u["role"] for u in locators.unnamed_interactives(data)] == ["button"]


def test_exclusive_with_clears_a_false_positive_collision(repo: Path):
    """Two controls that share a locator but never co-render are not ambiguous at runtime."""
    write(repo / DASH, _screen("""\
### error-alert
- role: alert
- name: none
- exclusive-with: [match-alert](#match-alert)
""", """\
### match-alert
- role: alert
- name: none
"""))
    # both are `role: alert` with no name → same locator; the declaration makes it not a collision
    assert locators.collisions(graph.build(load(repo), surface="web")) == []
    assert "ambiguous-locator" not in _codes(repo)


def test_exclusive_with_is_symmetric(repo: Path):
    """Annotating one of the two mutually-exclusive siblings is enough."""
    write(repo / DASH, _screen("""\
### a-alert
- role: alert
- name: none
""", """\
### b-alert
- role: alert
- name: none
- exclusive-with: [a-alert](#a-alert)
"""))
    assert locators.collisions(graph.build(load(repo), surface="web")) == []


def test_a_real_co_render_collision_is_not_cleared_by_an_unrelated_exclusion(repo: Path):
    """Three same-named controls, only one pair exclusive → the live pair still reports."""
    write(repo / DASH, _screen("""\
### save-a
- role: button
- name: Save
- exclusive-with: [save-b](#save-b)
""", """\
### save-b
- role: button
- name: Save
""", """\
### save-c
- role: button
- name: Save
"""))
    collisions = locators.collisions(graph.build(load(repo), surface="web"))
    assert len(collisions) == 1
    # a↔b is excluded, but c collides with both a and b, so all three stay in the live conflict
    assert [n.split("#")[-1] for n in collisions[0]["nodes"]] == ["save-a", "save-b", "save-c"]


# ---- generated elements: `one-per:` templates ---------------------------------------------------

REPEATED = """\
### stage-row-button
- role: button
- one-per: `stage` — one button per stage of the report
- name: `{stage.name} — {fmt(stage.totalCost, 2)} $`
- unique-by: `stage.id` — `stage.name` may repeat across stages
"""


def _locator(repo: Path, *components: str) -> dict:
    data = _build(repo, _screen(*components))
    return locators.screen_locators(data)[0]["locators"][0]


def test_a_one_per_node_compiles_to_a_data_only_template(repo: Path):
    """The compiled form is segments — no locator expression in any target language."""
    entry = _locator(repo, REPEATED)
    assert entry["strategy"] == "template"
    assert entry["locator"] == ""          # nothing executable is emitted
    assert entry["iterates"] == "stage"
    assert entry["binds"] == ["stage.name"]
    assert entry["segments"] == [
        {"kind": "bind", "path": "stage.name"},
        {"kind": "literal", "text": " — "},
        {"kind": "opaque", "expr": "fmt(stage.totalCost, 2)"},
        {"kind": "literal", "text": " $"},
    ]


def test_template_reading_is_opt_in_per_node(repo: Path):
    """Without `one-per:`, `{…}` in a name is literal text — exactly today's behavior."""
    entry = _locator(repo, "### t\n- role: button\n- name: {stage.name} — total\n")
    assert entry["strategy"] == "role"
    assert "{stage.name}" in entry["locator"]


def test_a_hole_outside_the_iteration_scope_is_opaque(repo: Path):
    """Classification is total: an unknown root is not an error, it is a wildcard."""
    entry = _locator(repo, "### r\n- role: button\n- one-per: `row`\n- name: `{row.id}: {other.name}`\n")
    assert {"kind": "bind", "path": "row.id"} in entry["segments"]
    assert {"kind": "opaque", "expr": "other.name"} in entry["segments"]


def test_the_repeat_bullets_are_known_to_the_registry(repo: Path):
    _build(repo, _screen(REPEATED))
    assert "unknown-bullet" not in _codes(repo, "warn")
    assert "static-template" not in _codes(repo)
    assert "unproven-unique-name" not in _codes(repo, "warn")


def test_an_all_opaque_template_is_static(repo: Path):
    """`${t("row_edit")}` on every row collides at runtime like two buttons sharing an i18n key."""
    data = _build(repo, _screen('### e\n- role: button\n- one-per: `row`\n- name: `${t("row_edit")}`\n'))
    assert [s["node"].split("#")[-1] for s in locators.static_templates(data)] == ["e"]
    assert "static-template" in _codes(repo)


def test_a_literal_name_on_a_repeated_node_is_static(repo: Path):
    data = _build(repo, _screen("### e\n- role: button\n- one-per: `row`\n- name: Edit\n"))
    assert len(locators.static_templates(data)) == 1
    assert "static-template" in _codes(repo)


def test_a_bind_of_an_ancestor_variable_does_not_discriminate(repo: Path):
    """`{group.name}` is constant across the *inner* repetition, so the inner node is static."""
    body = _screen("""\
### group-panel
- role: group
- one-per: `group`
- name: `{group.name}`
- unique-by: `group.id`
""", """\
### row-toggle
- role: switch
- one-per: `row`
- name: `{group.name} row`
- parent: [group-panel](#group-panel)
""")
    data = _build(repo, body)
    assert [s["node"].split("#")[-1] for s in locators.static_templates(data)] == ["row-toggle"]


def test_display_value_binds_without_unique_by_warn(repo: Path):
    """The book can warn that `name` may repeat across instances; it cannot prove it doesn't."""
    data = _build(repo, _screen("### b\n- role: button\n- one-per: `stage`\n- name: `{stage.name}`\n"))
    assert [u["binds"] for u in locators.unproven_unique_names(data)] == [["stage.name"]]
    assert "unproven-unique-name" in _codes(repo, "warn")


def test_unique_by_clears_the_unproven_name_warning(repo: Path):
    _build(repo, _screen(REPEATED))
    assert "unproven-unique-name" not in _codes(repo, "warn")


def test_a_non_display_bind_needs_no_unique_by(repo: Path):
    data = _build(repo, _screen("### b\n- role: button\n- one-per: `stage`\n- name: `Stage {stage.id}`\n"))
    assert locators.unproven_unique_names(data) == []


def test_a_template_pattern_matching_a_static_sibling_is_ambiguous(repo: Path):
    """A static "Total — 12.00 $" label collides with the stage template at runtime."""
    static = "### total-label\n- role: button\n- name: Total — 12.00 $\n"
    collisions = locators.collisions(_build(repo, _screen(REPEATED, static)))
    assert len(collisions) == 1
    assert collisions[0]["template"] == "{stage.name} — {fmt(stage.totalCost, 2)} $"
    assert [n.split("#")[-1] for n in collisions[0]["nodes"]] == [
        "stage-row-button", "total-label"]
    assert _codes(repo).count("ambiguous-locator") == 2


def test_a_static_sibling_the_pattern_cannot_match_is_fine(repo: Path):
    assert locators.collisions(_build(repo, _screen(REPEATED, SAVE))) == []


def test_exclusive_with_clears_a_template_collision_too(repo: Path):
    body = _screen(REPEATED.rstrip() + "\n- exclusive-with: [total-label](#total-label)\n",
                   "### total-label\n- role: button\n- name: Total — 12.00 $\n")
    assert locators.collisions(_build(repo, body)) == []


def test_an_unbalanced_brace_is_the_one_hard_error(repo: Path):
    data = _build(repo, _screen("### b\n- role: button\n- one-per: `row`\n- name: `{row.name`\n"))
    assert len(locators.malformed_templates(data)) == 1
    assert "malformed-template" in _codes(repo)


def test_variants_parse_into_an_enumerable_axis(repo: Path):
    data = _build(repo, _screen("""\
### property-field
- role: textbox
- one-per: `field`
- variants: `field.type = text | number | select | date`
- name: `{field.label}`
- unique-by: `field.id`
"""))
    node = next(n for n in data["nodes"] if n["id"].endswith("#property-field"))
    assert locators.variants_of(node) == {
        "path": "field.type", "values": ["text", "number", "select", "date"]}
    assert "malformed-variants" not in _codes(repo, "warn")


def test_an_unparsable_variants_axis_is_surfaced_not_dropped(repo: Path):
    data = _build(repo, _screen(
        "### f\n- role: textbox\n- one-per: `field`\n- variants: `whatever goes`\n"
        "- name: `{field.id}`\n"))
    assert len(locators.invalid_variants(data)) == 1
    assert "malformed-variants" in _codes(repo, "warn")


def test_a_templated_name_outside_any_repeat_warns(repo: Path):
    """Holes with no iteration variable to bind are all wildcards — the name pins nothing."""
    data = _build(repo, _screen("### s\n- role: button\n- name: `{stage.name} — total`\n"))
    assert [t["node"].split("#")[-1] for t in locators.templates_outside_repeat(data)] == ["s"]
    assert "template-outside-repeat" in _codes(repo, "warn")


def test_a_repeat_scope_clears_the_outside_repeat_warning(repo: Path):
    """Own `one-per:` and an inherited scope both count — the holes have a variable to bind."""
    body = _screen(REPEATED, """\
### row-label
- role: button
- name: `{stage.name} row`
- parent: [stage-row-button](#stage-row-button)
""")
    data = _build(repo, body)
    assert locators.templates_outside_repeat(data) == []
    assert "template-outside-repeat" not in _codes(repo, "warn")


def test_an_unbalanced_brace_outside_a_repeat_stays_literal(repo: Path):
    """Outside a repeat scope the grammar changes nothing for unbalanced braces — no check reads them."""
    data = _build(repo, _screen("### s\n- role: button\n- name: `{stage.name`\n"))
    assert locators.templates_outside_repeat(data) == []
    assert "template-outside-repeat" not in _codes(repo, "warn")
    assert "malformed-template" not in _codes(repo)


# `name:` twice: not two names, a node that cannot say which one it has.
TWO_NAMES = """\
### copy-button
- selector: `.btn-copy`
- role: button
- name: Copy
- name: Copy datasheet
"""


def test_a_repeated_identity_bullet_is_the_book_s_defect_not_a_collision(repo: Path):
    """A second `name:` (or `role:`) is `duplicate-bullet`, and the node is left out of the
    collision check until it is well-formed. Grouping on the first of the two names would
    raise `ambiguous-locator` against `SAVE`-style siblings — a claim about the code, made off
    a malformation the book alone explains."""
    data = _build(repo, _screen(TWO_NAMES, "### other-copy\n- role: button\n- name: Copy\n"))
    assert locators.malformed_identity(data["nodes"][1]) == ["name"]
    assert locators.collisions(data) == []

    findings = doctor.run(load(repo), check_schema=False).findings
    dup = [f for f in findings if f.code == "duplicate-bullet"]
    assert [f.ref for f in dup] == [f"{DASH}#copy-button#name"]
    assert dup[0].severity == "error" and "2 times" in dup[0].message
    assert "ambiguous-locator" not in [f.code for f in findings]


def test_a_repeated_role_is_reported_under_its_own_key(repo: Path):
    _build(repo, _screen("### x\n- role: button\n- role: link\n- name: X\n"))
    dup = [f for f in doctor.run(load(repo), check_schema=False).findings
           if f.code == "duplicate-bullet"]
    assert [f.ref for f in dup] == [f"{DASH}#x#role"]
