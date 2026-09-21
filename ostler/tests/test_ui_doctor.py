"""`ostler doctor` as a mandatory UI-profile linter (docs/okf-ui-support §7)."""

from __future__ import annotations

import json
from pathlib import Path

from ostler import doctor, fmt, links, registry, scaffold
from ostler.model import load

from conftest import write


def codes(report):
    return {f.code for f in report.findings if f.severity == "error"}


def all_codes(report):
    """Every finding, warns included — `codes` reads errors only, and one UI rule is a warn."""
    return {f.code for f in report.findings}


def _run(repo: Path):
    return doctor.run(load(repo))


def test_unknown_type(repo: Path):
    write(repo / "docs/features/x.md", "---\ntype: widget\nslug: x\ntitle: X\n---\n# X\n")
    report = _run(repo)
    assert "unknown-type" in codes(report)
    finding = next(f for f in report.findings if f.code == "unknown-type")
    assert finding.path == "docs/features/x.md" and finding.line == 1


def test_link_validation_is_document_wide(repo: Path):
    write(repo / "docs/features/x.md",
          "---\ntype: concept\nslug: x\ntitle: X\n---\n# X\n\n## Notes\n\nSee [gone](./nope.md).\n")
    assert "dangling-link" in codes(_run(repo))


def test_link_validation_skips_code(repo: Path):
    write(repo / "docs/features/x.md",
          "---\ntype: concept\nslug: x\ntitle: X\n---\n# X\n\n## Notes\n\n"
          "Inline `arr[i](nope.md)` and\n\n```\nf = g[i](also-nope.md)\n```\n")
    assert "dangling-link" not in codes(_run(repo))


def test_known_types_not_flagged(repo: Path):
    write(repo / "docs/features/x.md", "---\ntype: concept\nslug: x\ntitle: X\n---\n# X\n")
    assert "unknown-type" not in codes(_run(repo))


def test_missing_required_section(repo: Path):
    write(repo / "docs/features/workhorse/workhorse.md",
          "---\ntype: cli\nslug: wh\ntitle: WH\n---\n# WH\n\n- binary: `wh`\n")
    report = _run(repo)
    assert "missing-required-section" in codes(report)
    finding = next(f for f in report.findings if f.code == "missing-required-section")
    assert finding.fixable and finding.suggestion == "## Commands"


def test_empty_required_section(repo: Path):
    """A server's `## Endpoints` heading exists but carries no prose."""
    write(repo / "docs/features/api/api.md",
          "---\ntype: server\nslug: api\ntitle: API\n---\n# API\n\n## Endpoints\n")
    report = _run(repo)
    hits = [f for f in report.findings if f.code == "empty-required-section"]
    assert len(hits) == 1
    assert "Endpoints" in hits[0].message


def test_filled_required_section_not_flagged(repo: Path):
    """The same book, but `## Endpoints` says something — no finding at all."""
    write(repo / "docs/features/api/api.md",
          "---\ntype: server\nslug: api\ntitle: API\n---\n# API\n\n"
          "## Endpoints\n\n`GET /widgets` lists the widgets.\n")
    assert "empty-required-section" not in codes(_run(repo))


def test_empty_required_section_excludes_sub_headings(repo: Path):
    """A `## Commands` with only a `### <id>` sub-heading and no prose is still empty."""
    write(repo / "docs/features/workhorse/workhorse.md",
          "---\ntype: cli\nslug: wh\ntitle: WH\n---\n# WH\n\n"
          "- binary: `wh`\n\n## Commands\n\n### run\n")
    assert "empty-required-section" in codes(_run(repo))


def test_missing_required_bullet(repo: Path):
    write(repo / "docs/features/groom/gui/screens/s.md",
          "---\ntype: screen\nslug: s\ntitle: S\n---\n# S\n\n"
          "## Interactions\n\n### click\n- trigger: click\n")
    report = _run(repo)
    missing = {f.ref for f in report.findings if f.code == "missing-required-bullet"}
    assert "on" in missing and "does" in missing
    assert "trigger" not in missing


def _interaction_with_verifies(repo: Path, verifies: list[str]) -> None:
    lines = "\n".join(f"- verify: {v}" for v in verifies)
    write(repo / "docs/features/groom/gui/screens/s.md",
          "---\ntype: screen\nslug: s\ntitle: S\n---\n# S\n\n"
          "## Components\n\n### btn\n- selector: #btn\n- role: button\n- name: Go\n\n"
          "## Interactions\n\n### act\n- on: [btn](#btn)\n- trigger: click\n- role: button\n"
          "- name: Go\n- keyboard: Enter\n- does:\n  - state: go\n" + lines + "\n")


def test_unspelled_alternation_same_check_different_value(repo: Path):
    _interaction_with_verifies(repo, [
        'http_status(201, path="/api/widgets")',
        'http_status(400, path="/api/widgets")',
    ])
    report = _run(repo)
    assert "unspelled-alternation" in all_codes(report)
    finding = next(f for f in report.findings if f.code == "unspelled-alternation")
    assert finding.severity == "warn"


def test_unspelled_alternation_needs_a_shared_identifying_argument(repo: Path):
    _interaction_with_verifies(repo, [
        'http_status(201, path="/api/widgets")',
        'http_status(400, path="/api/reports")',
    ])
    assert "unspelled-alternation" not in all_codes(_run(repo))


def test_unspelled_alternation_ignores_a_single_argument_check(repo: Path):
    _interaction_with_verifies(repo, [
        'removed(subject="the first widget")',
        'removed(subject="the second widget")',
    ])
    assert "unspelled-alternation" not in all_codes(_run(repo))


def test_two_counts_of_two_collections_are_not_one_count_claimed_twice(repo: Path):
    _interaction_with_verifies(repo, [
        'count(subject="open widgets", equals=1)',
        'count(subject="archived widgets", equals=1)',
    ])
    assert "unspelled-alternation" not in all_codes(_run(repo))


def test_the_role_is_read_from_the_signature_not_from_whether_it_is_required(repo: Path):
    _interaction_with_verifies(repo, [
        'http_status(201, path="/api/widgets")',
        'http_status(409, path="/api/widgets")',
    ])
    assert "unspelled-alternation" in all_codes(_run(repo))


def test_a_differing_identifier_is_not_a_conflict_even_where_a_flag_agrees(repo: Path):
    _interaction_with_verifies(repo, [
        'json_path(path="$.state", equals="open")',
        'json_path(path="$.owner", equals="open")',
    ])
    assert "unspelled-alternation" not in all_codes(_run(repo))


def test_unspelled_alternation_not_tripped_by_an_extends_split(repo: Path):
    write(repo / "docs/features/groom/gui/screens/s.md",
          "---\ntype: screen\nslug: s\ntitle: S\n---\n# S\n\n"
          "## Components\n\n### btn\n- selector: #btn\n- role: button\n- name: Go\n\n"
          "## Interactions\n\n### act\n- on: [btn](#btn)\n- trigger: click\n- role: button\n"
          "- name: Go\n- keyboard: Enter\n- does:\n  - state: go\n"
          '- verify: http_status(201, path="/api/widgets")\n\n'
          "### refuse-act\n- extends: [act](#act)\n- does:\n  - state: refuse\n"
          '- verify: http_status(400, path="/api/widgets")\n')
    assert "unspelled-alternation" not in all_codes(_run(repo))


_ARM_BOOK = (
    "---\ntype: screen\nslug: s\ntitle: S\n---\n# S\n\n"
    "## Components\n\n### btn\n- selector: #btn\n- role: button\n- name: Go\n\n"
    "### field\n- selector: #field\n- role: textbox\n- name: Name\n\n"
    "## Interactions\n\n### act\n- on: [btn](#btn)\n- trigger: click\n- role: button\n"
    "- name: Go\n- keyboard: Enter\n- when: `name` non-empty\n"
    '- arrange: fill(locator="#field", value="Widget A")\n'
    "- does:\n  - state: go\n"
    '- verify: http_status(201, path="/api/widgets")\n\n'
)


def test_an_extending_arm_that_arranges_nothing_while_its_base_does_is_a_finding(repo: Path):
    write(repo / "docs/features/groom/gui/screens/s.md", _ARM_BOOK
          + "### refuse-act\n- extends: [act](#act)\n- when: `name` empty\n- does:\n"
          '  - state: refuse\n- verify: http_status(400, path="/api/widgets")\n')
    assert "unarranged-extending-arm" in all_codes(_run(repo))


def test_an_extending_arm_with_its_own_arrangement_is_not_a_finding(repo: Path):
    write(repo / "docs/features/groom/gui/screens/s.md", _ARM_BOOK
          + "### refuse-act\n- extends: [act](#act)\n- when: `name` empty\n"
          '- arrange: fill(locator="#field", value="")\n- does:\n'
          '  - state: refuse\n- verify: http_status(400, path="/api/widgets")\n')
    assert "unarranged-extending-arm" not in all_codes(_run(repo))


def test_an_interaction_that_extends_a_component_instead_of_an_interaction_is_flagged(
        repo: Path):
    """`extends:` can only inherit control identity from another arm of the *same* node type — a component is a real, resolvable target, just the wrong kind of one."""
    write(repo / "docs/features/groom/gui/screens/s.md", _ARM_BOOK
          + "### act-bad\n- on: [btn](#btn)\n- trigger: click\n- role: button\n- name: Go\n"
          "- keyboard: Enter\n- when: `name` non-empty\n"
          '- arrange: fill(locator="#field", value="Widget A")\n'
          "- does:\n  - state: go\n"
          '- verify: http_status(201, path="/api/widgets")\n'
          "- extends: [btn](#btn)\n")
    report = _run(repo)
    assert "extends-type-mismatch" in codes(report)
    finding = next(f for f in report.findings if f.code == "extends-type-mismatch")
    assert finding.ref == "docs/features/groom/gui/screens/s.md#act-bad#extends"


def test_a_selector_written_as_a_css_attribute_predicate_is_flagged_unaddressable(repo: Path):
    """`ostler vet`'s render scan never mints an attribute-value or boolean-attribute string, so a selector shaped like one can never be matched against a real census, however accurate a description of the DOM it is."""
    _screen_with(repo, '- role: generic\n- name: none\n- selector: [data-state="booked"]\n')
    report = _run(repo)
    assert "unaddressable-selector" in codes(report)
    finding = next(f for f in report.findings if f.code == "unaddressable-selector")
    assert finding.ref == "docs/features/groom/gui/screens/s.md#body#selector:1"


def test_a_states_bullet_claiming_the_control_is_disabled_with_no_check_is_flagged(repo: Path):
    """`visible(...)` passes on a greyed-out button, so an unavailability claim needs its own `actionable(...)`/`inert(...)` observer — with none in the book, the claim is unverified."""
    _screen_with(repo, "- role: generic\n- name: none\n- states: disabled until valid\n")
    report = _run(repo)
    assert "unchecked-availability-state" in all_codes(report)
    finding = next(f for f in report.findings if f.code == "unchecked-availability-state")
    assert finding.ref == "docs/features/groom/gui/screens/s.md#body#states:1"


def test_a_scaffolded_empty_arrange_bullet_does_not_count_as_an_arrangement(repo: Path):
    write(repo / "docs/features/groom/gui/screens/s.md", _ARM_BOOK
          + "### refuse-act\n- extends: [act](#act)\n- when: `name` empty\n- arrange:\n"
          '- fixture:\n- does:\n  - state: refuse\n'
          '- verify: http_status(400, path="/api/widgets")\n')
    assert "unarranged-extending-arm" in all_codes(_run(repo))


def _screen_with(repo: Path, bullets: str) -> None:
    write(repo / "docs/features/groom/gui/screens/s.md",
          "---\ntype: screen\nslug: s\ntitle: S\n---\n# S\n\n"
          f"## Components\n\n### body\n{bullets}")


def test_a_self_declared_empty_keyboard_is_not_the_light_sibling(repo: Path):
    _screen_with(
        repo,
        "- role: generic\n- name: none\n"
        "- states: a policy still open reads `Draft`\n"
        '- verify: visible(locator="#body", text="Draft")\n'
        '- verify: visible(locator="#body", text="VIN")\n'
        "- keyboard: none, because it is read rather than operated.\n")
    assert "uneven-claim-coverage" not in all_codes(_run(repo))


def test_a_component_that_carries_the_page_says_where_it_sits(repo: Path):
    """`role:` and `name:` are the accessibility contract, and a scenario asserting on them passes on a component crushed into a column against one margin — which is a defect that reached a green run."""
    _screen_with(repo, "- role: article\n- name: none\n")
    report = _run(repo)
    assert "missing-placement" in codes(report)
    finding = next(f for f in report.findings if f.code == "missing-placement")
    assert finding.ref == "docs/features/groom/gui/screens/s.md#body#placement", finding.ref
    assert finding.path == "docs/features/groom/gui/screens/s.md" and finding.line

    _screen_with(repo, "- role: article\n- name: none\n- placement: width 60-100%, x 0-20%\n")
    assert "missing-placement" not in codes(_run(repo))

    _screen_with(repo, "- role: button\n- name: Save\n")
    assert "missing-placement" not in codes(_run(repo))


def test_a_placement_nobody_could_violate_is_a_finding_not_coverage(repo: Path):
    _screen_with(repo, "- role: article\n- name: none\n- placement: mostly the middle\n")
    report = _run(repo)
    assert "malformed-placement" in codes(report)
    assert "missing-placement" not in codes(report), "it is present, just wrong"
    message = next(f.message for f in report.findings if f.code == "malformed-placement")
    assert "not a `key min-max%` pair" in message, message

    _screen_with(repo, "- role: article\n- name: none\n- placement: width 100-60%\n")
    assert "malformed-placement" in codes(_run(repo))


def test_dangling_link(repo: Path):
    write(repo / "docs/features/groom/concepts/diff.md",
          "---\ntype: concept\nslug: diff\ntitle: Diff\n---\n# Diff\n\n"
          "See [gone](../gui/screens/gone.md).\n")
    report = _run(repo)
    assert "dangling-link" in codes(report)


def test_missing_anchor(repo: Path):
    write(repo / "docs/features/groom/concepts/a.md",
          "---\ntype: concept\nslug: a\ntitle: A\n---\n# A\n")
    write(repo / "docs/features/groom/concepts/b.md",
          "---\ntype: concept\nslug: b\ntitle: B\n---\n# B\n\nSee [a](a.md#ghost).\n")
    report = _run(repo)
    assert "missing-anchor" in codes(report)


def test_unresolved_relation(repo: Path):
    write(repo / "docs/features/groom/gui/screens/s.md",
          "---\ntype: screen\nslug: s\ntitle: S\n---\n# S\n\n"
          "## Components\n\n### row\n"
          "- extends: [nope](../components/missing.md#x)\n")
    report = _run(repo)
    assert "unresolved-relation" in codes(report)


def test_nested_flow_steps_are_checked_as_relation_values(repo: Path):
    write(
        repo / "docs/features/workhorse/concepts/target.md",
        "---\ntype: concept\nslug: target\ntitle: Target\n---\n# Target\n",
    )
    write(
        repo / "docs/features/workhorse/flows/journey.md",
        "---\ntype: flow\nslug: journey\ntitle: Journey\n---\n# Journey\n\n"
        "- start: ready\n"
        "- steps:\n"
        "  1. Open [target](../concepts/target.md)\n"
        "  2. Finish\n"
        "- end: complete\n",
    )

    report = _run(repo)

    assert "unresolved-relation" not in codes(report)


def test_bad_heading_type(repo: Path):
    write(repo / "docs/features/groom/gui/screens/s.md",
          "---\ntype: screen\nslug: s\ntitle: S\n---\n# S\n\n"
          "## interactions\n\n### click\n- on: [x](#s)\n- trigger: click\n- does:\n  - state: x\n")
    report = _run(repo)
    finding = next((f for f in report.findings if f.code == "bad-heading-type"), None)
    assert finding is not None and finding.suggestion == "## Interactions"


def _interaction(does: str) -> str:
    return ("---\ntype: screen\nslug: s\ntitle: S\n---\n# S\n\n"
            "## Interactions\n\n### click\n- on: [S](#s)\n- trigger: click\n"
            f"- does: {does}\n")


def test_overlong_normative_bullet(repo: Path):
    write(repo / "docs/features/groom/gui/screens/s.md", _interaction("the row saves. " * 60))
    report = _run(repo)
    finding = next(f for f in report.findings if f.code == "overlong-normative-bullet")
    assert finding.severity == "error"
    assert finding.path == "docs/features/groom/gui/screens/s.md"
    assert finding.ref == f"{finding.path}#click#does:1"


def test_a_short_normative_bullet_is_not_flagged(repo: Path):
    write(repo / "docs/features/groom/gui/screens/s.md", _interaction("the row saves."))
    assert "overlong-normative-bullet" not in codes(_run(repo))


def test_code_spans_and_link_hrefs_do_not_count_as_prose(repo: Path):
    padding = "`" + "x" * 900 + "` [see](" + "y" * 100 + ".md)"
    write(repo / "docs/features/groom/gui/screens/s.md",
          _interaction(f"the row saves, per {padding}."))
    assert "overlong-normative-bullet" not in codes(_run(repo))


def test_a_parenthetical_counts_as_prose(repo: Path):
    write(repo / "docs/features/groom/gui/screens/s.md",
          _interaction("the row saves (" + "and the audit row records it. " * 30 + ")"))
    assert "overlong-normative-bullet" in codes(_run(repo))


def test_only_normative_bullets_are_measured(repo: Path):
    write(repo / "docs/features/groom/gui/screens/s.md",
          "---\ntype: screen\nslug: s\ntitle: S\n---\n# S\n\n"
          "## Interactions\n\n### click\n- on: [S](#s)\n"
          f"- trigger: {'click the row. ' * 60}\n- does: the row saves.\n")
    assert "overlong-normative-bullet" not in codes(_run(repo))


def test_a_bullet_enumerating_status_branches_is_compound(repo: Path):
    write(repo / "docs/features/groom/gui/screens/s.md",
          _interaction("returns `400` on a malformed body, `409` on a stale manifest, "
                       "and `200` with the published page otherwise"))
    finding = next(f for f in _run(repo).findings if f.code == "compound-normative-bullet")
    assert finding.severity == "warn"
    assert "3 status codes (200, 400, 409)" in finding.message


def test_a_bullet_naming_two_failures_is_compound(repo: Path):
    write(repo / "docs/features/groom/gui/screens/s.md",
          _interaction("raises `SlugCollisionError` for a duplicate slug or "
                       "`ManifestConflict` when the revision moved"))
    assert "compound-normative-bullet" in all_codes(_run(repo))


def test_a_semicolon_joining_clauses_is_compound(repo: Path):
    write(repo / "docs/features/groom/gui/screens/s.md",
          _interaction("the row saves; the audit trail records the previous value"))
    assert "compound-normative-bullet" in all_codes(_run(repo))


def test_a_semicolon_finding_names_the_form_a_reason_takes(repo: Path):
    write(repo / "docs/features/groom/gui/screens/s.md",
          _interaction("does not cast the value; that decision belongs to the caller"))
    finding = next(f for f in _run(repo).findings if f.code == "compound-normative-bullet")
    assert "parentheses" in finding.message


def test_a_semicolon_inside_an_aside_is_not_compound(repo: Path):
    write(repo / "docs/features/groom/gui/screens/s.md",
          _interaction("the fallback menu opens (this journey exercises the fallback; "
                       "the native hand-off is out of scope)"))
    assert "compound-normative-bullet" not in all_codes(_run(repo))


def test_a_semicolon_inside_a_code_span_is_not_compound(repo: Path):
    write(repo / "docs/features/groom/gui/screens/s.md",
          _interaction("returns `\"application/json; charset=utf-8\"` regardless of the "
                       "ext parameter"))
    assert "compound-normative-bullet" not in all_codes(_run(repo))


def test_a_semicolon_outside_an_aside_is_still_compound(repo: Path):
    write(repo / "docs/features/groom/gui/screens/s.md",
          _interaction("the row saves (the audit trail is written first); "
                       "the previous value is shown beside it"))
    assert "compound-normative-bullet" in all_codes(_run(repo))


def test_listing_two_nouns_is_not_compound(repo: Path):
    write(repo / "docs/features/groom/gui/screens/s.md",
          _interaction("the page and its slug are written to the manifest"))
    assert "compound-normative-bullet" not in all_codes(_run(repo))


def test_one_status_code_is_not_compound(repo: Path):
    write(repo / "docs/features/groom/gui/screens/s.md",
          _interaction("returns `409` when the manifest revision moved under the write"))
    assert "compound-normative-bullet" not in all_codes(_run(repo))


def test_a_bare_three_digit_number_is_not_a_status_code(repo: Path):
    write(repo / "docs/features/groom/gui/screens/s.md",
          _interaction("the label renders at font-weight 500 (vs body's 400)"))
    assert "compound-normative-bullet" not in all_codes(_run(repo))


def test_capitalised_prose_words_are_not_two_failures(repo: Path):
    write(repo / "docs/features/groom/gui/screens/s.md",
          _interaction("the PaymentDenied banner shows the ConflictResolution the merge chose"))
    assert "compound-normative-bullet" not in all_codes(_run(repo))


def test_a_bare_three_digit_number_under_a_non_normative_key_mints_nothing(repo: Path):
    write(repo / "docs/features/groom/concepts/lease.md",
          "---\ntype: concept\nslug: lease\ntitle: Lease\n---\n# Lease\n\n"
          "- meaning: a lock over one path\n"
          "- styling: the deadline renders at font-weight 500 (vs body's 400)\n")
    assert "unminted-claim" not in all_codes(_run(repo))


def test_an_overlong_bullet_is_reported_once(repo: Path):
    write(repo / "docs/features/groom/gui/screens/s.md",
          _interaction("returns `400`; then `500`. " * 60))
    found = all_codes(_run(repo))
    assert "overlong-normative-bullet" in found
    assert "compound-normative-bullet" not in found


def _method(verify: str) -> str:
    return ("---\ntype: concept\nslug: publisher\ntitle: Publisher\n---\n# Publisher\n\n"
            "## Methods\n\n### Publish\n- returns: the published revision\n"
            f"- verify: {verify}\n")


def test_verify_naming_a_test_is_refused(repo: Path):
    write(repo / "docs/features/groom/concepts/publisher.md",
          _method("Test_Service_Publish_ShouldConflict"))
    finding = next(f for f in _run(repo).findings if f.code == "unparsed-check")
    assert finding.severity == "error"
    assert "not a check call" in finding.message


def test_verify_naming_an_unknown_check_lists_the_vocabulary(repo: Path):
    write(repo / "docs/features/groom/concepts/publisher.md",
          _method('manifest_unchanged_except(page="getting-started")'))
    finding = next(f for f in _run(repo).findings if f.code == "unparsed-check")
    assert "is not a known check" in finding.message
    assert "keys_unchanged" in finding.message


def test_a_declared_check_grounds(repo: Path):
    write(repo / "docs/features/groom/concepts/publisher.md",
          _method('http_status(409, title="Manifest Conflict")'))
    assert "unparsed-check" not in all_codes(_run(repo))


def _screen_with_locator(locator: str, *, declare_table: bool = True) -> str:
    table = ("### widget-table\n- selector: table[aria-label=\"Widgets\"]\n- role: table\n"
             "- name: Widgets\n\n" if declare_table else "")
    return ("---\ntype: screen\nslug: s\ntitle: S\n---\n# S\n\n"
            f"## Components\n\n{table}"
            "## Interactions\n\n### click\n- on: [S](#s)\n- trigger: click\n"
            "- does: the table appears\n"
            f"- verify: visible(locator=\"{locator}\")\n")


def test_a_raw_selector_is_not_a_locator(repo: Path):
    write(repo / "docs/features/groom/gui/screens/s.md",
          _screen_with_locator("table[aria-label='Widgets']"))
    finding = next(f for f in _run(repo).findings if f.code == "undeclared-check-locator")
    assert finding.severity == "error"
    assert "not a reference into the book" in finding.message
    assert finding.ref == "docs/features/groom/gui/screens/s.md#click#verify:1"


def test_a_locator_naming_no_declared_component_is_reported(repo: Path):
    write(repo / "docs/features/groom/gui/screens/s.md",
          _screen_with_locator("#widget-table", declare_table=False))
    finding = next(f for f in _run(repo).findings if f.code == "undeclared-check-locator")
    assert "names no component this book declares" in finding.message


def test_a_locator_naming_a_declared_component_grounds(repo: Path):
    write(repo / "docs/features/groom/gui/screens/s.md", _screen_with_locator("#widget-table"))
    assert "undeclared-check-locator" not in all_codes(_run(repo))


def test_a_locator_may_name_a_component_in_another_document(repo: Path):
    write(repo / "docs/features/groom/gui/screens/other.md",
          _screen_with_locator("#widget-table"))
    write(repo / "docs/features/groom/gui/screens/s.md",
          _screen_with_locator("other.md#widget-table", declare_table=False))
    assert "undeclared-check-locator" not in all_codes(_run(repo))


def _screen_with_arrangement(act: str, *, declare_field: bool = True) -> str:
    """An interaction whose `when:` is arranged by an act performed on this screen's own form."""
    field = ('### name-field\n- selector: input[name="name"]\n- role: textbox\n'
             "- name: Name\n\n" if declare_field else "")
    return ("---\ntype: screen\nslug: s\ntitle: S\n---\n# S\n\n"
            f"## Components\n\n{field}"
            "## Interactions\n\n### submit\n- on: [S](#s)\n- trigger: click\n"
            "- role: button\n- name: Save\n- keyboard: Enter\n"
            "- when: `name` is non-empty\n"
            f"- arrange: {act}\n"
            "- does: the widget is saved\n")


def test_an_arrange_value_that_is_a_bare_fixture_name_is_relocated(repo: Path):
    write(repo / "docs/features/groom/gui/screens/s.md",
          _screen_with_arrangement("widgets-on-hand"))
    finding = next(f for f in _run(repo).findings if f.code == "unparsed-act")
    assert finding.severity == "error"
    assert "belongs on `fixture:`" in finding.message
    assert finding.suggestion == "- fixture: widgets-on-hand"


def test_an_arrange_value_naming_a_check_gets_the_act_vocabulary(repo: Path):
    write(repo / "docs/features/groom/gui/screens/s.md",
          _screen_with_arrangement('visible(locator="#name-field")'))
    finding = next(f for f in _run(repo).findings if f.code == "unparsed-act")
    assert "is not a known act" in finding.message


def test_an_act_pointed_at_a_raw_selector_is_reported(repo: Path):
    write(repo / "docs/features/groom/gui/screens/s.md",
          _screen_with_arrangement('fill(locator="input[name=\'name\']", value="Widget A")'))
    finding = next(f for f in _run(repo).findings if f.code == "undeclared-act-locator")
    assert finding.severity == "error"
    assert "not a reference into the book" in finding.message
    assert finding.ref == "docs/features/groom/gui/screens/s.md#submit#arrange:1"


def test_an_act_naming_no_declared_component_is_reported(repo: Path):
    write(repo / "docs/features/groom/gui/screens/s.md",
          _screen_with_arrangement('fill(locator="#name-field", value="A")', declare_field=False))
    finding = next(f for f in _run(repo).findings if f.code == "undeclared-act-locator")
    assert "names no component this book declares" in finding.message


def test_an_act_on_a_declared_component_grounds(repo: Path):
    write(repo / "docs/features/groom/gui/screens/s.md",
          _screen_with_arrangement('fill(locator="#name-field", value="A")'))
    codes = all_codes(_run(repo))
    assert "undeclared-act-locator" not in codes
    assert "unparsed-act" not in codes


def test_an_arrange_bullet_is_not_read_as_a_fixture_name(repo: Path):
    """The narrowing that made the key possible: the two fixture checkers iterate every arrangement key, and an act read as a fixture name is a finding against a correct book."""
    write(repo / "docs/features/groom/gui/screens/s.md",
          _screen_with_arrangement('fill(locator="#name-field", value="A")'))
    codes = all_codes(_run(repo))
    assert "unknown-book-fixture" not in codes
    assert "qa-fixture-bullet" not in codes


def _branching_interaction(combiner: str = "", *, check: bool = True) -> str:
    """An interaction whose `does:` nests two outcomes, and the check that observes one of them."""
    return ("---\ntype: screen\nslug: s\ntitle: S\n---\n# S\n\n"
            "## Components\n\n### widget-table\n- selector: table[aria-label=\"Widgets\"]\n"
            "- role: table\n- name: Widgets\n\n"
            "## Interactions\n\n### click\n- on: [S](#s)\n- trigger: click\n"
            f"- does:{' ' + combiner if combiner else ''}\n"
            "  - success: the table appears\n"
            "  - failure: the page stays put\n"
            + ('- verify: visible(locator="#widget-table")\n' if check else ""))


def _claim_bindings(repo: Path) -> dict[tuple[str, int], list[str]]:
    node = load(repo).ui_nodes_of_type("interaction")[0]
    return registry.attributed_checks(node.type, node.bullet_order, node.combiners)[1]


def test_a_nested_claim_list_with_a_check_must_say_how_its_children_combine(repo: Path):
    write(repo / "docs/features/groom/gui/screens/s.md", _branching_interaction())
    finding = next(f for f in _run(repo).findings if f.code == "unstated-claim-combiner")
    assert finding.severity == "error"
    assert finding.ref == "docs/features/groom/gui/screens/s.md#click#does:1"
    assert "branches" in (finding.suggestion or "")


def test_a_nested_claim_list_nobody_observes_needs_no_combiner(repo: Path):
    write(repo / "docs/features/groom/gui/screens/s.md", _branching_interaction(check=False))
    assert "unstated-claim-combiner" not in all_codes(_run(repo))


def test_a_conjunction_fans_the_check_out_to_every_child(repo: Path):
    write(repo / "docs/features/groom/gui/screens/s.md", _branching_interaction("all"))
    assert "unstated-claim-combiner" not in all_codes(_run(repo))
    assert _claim_bindings(repo) == {
        ("does", 1): ['visible(locator="#widget-table")'],
        ("does", 2): ['visible(locator="#widget-table")'],
    }


def test_a_disjunction_binds_the_check_to_no_child(repo: Path):
    write(repo / "docs/features/groom/gui/screens/s.md", _branching_interaction("branches"))
    assert _claim_bindings(repo) == {}
    branches = [f for f in _run(repo).findings if f.code == "unobserved-branch"]
    assert [f.severity for f in branches] == ["warn", "warn"]
    assert "Split the branches into sibling bullets" in branches[0].message


def test_a_stated_combiner_is_not_itself_a_claim(repo: Path):
    write(repo / "docs/features/groom/gui/screens/s.md", _branching_interaction("all"))
    node = load(repo).ui_nodes_of_type("interaction")[0]
    assert [v for k, v, _ in node.bullet_order if k == "does"] == [
        "success: the table appears", "failure: the page stays put"]
    assert node.combiners == {2: "all"}


def test_a_combiner_word_on_a_childless_bullet_stays_prose(repo: Path):
    write(repo / "docs/features/groom/gui/screens/s.md",
          ("---\ntype: screen\nslug: s\ntitle: S\n---\n# S\n\n"
           "## Interactions\n\n### click\n- on: [S](#s)\n- trigger: click\n"
           "- does: all\n"))
    node = load(repo).ui_nodes_of_type("interaction")[0]
    assert node.combiners == {}
    assert [v for k, v, _ in node.bullet_order if k == "does"] == ["all"]


def test_a_node_that_declares_nothing_is_reported(repo: Path):
    write(repo / "docs/features/groom/concepts/publisher.md",
          "---\ntype: concept\nslug: publisher\ntitle: Publisher\n---\n# Publisher\n\n"
          "## Methods\n\n### Publish\n- returns: the published revision\n"
          "- raises: `ManifestConflict` when the revision moved\n")
    finding = next(f for f in _run(repo).findings if f.code == "undeclared-obligation")
    assert finding.severity == "warn"
    assert "2 normative bullets" in finding.message
    assert finding.suggestion is not None and "http_status" in finding.suggestion
    assert finding.ref == f"{finding.path}#publish#verify"


def test_one_declaration_answers_the_node(repo: Path):
    write(repo / "docs/features/groom/concepts/publisher.md",
          "---\ntype: concept\nslug: publisher\ntitle: Publisher\n---\n# Publisher\n\n"
          "## Methods\n\n### Publish\n- returns: the published revision\n"
          "- raises: `ManifestConflict` when the revision moved\n"
          '- verify: http_status(409, title="Manifest Conflict")\n')
    assert "undeclared-obligation" not in all_codes(_run(repo))


def test_a_declaration_that_does_not_parse_is_reported_once(repo: Path):
    write(repo / "docs/features/groom/concepts/publisher.md",
          _method("Test_Service_Publish_ShouldConflict"))
    found = all_codes(_run(repo))
    assert "unparsed-check" in found
    assert "undeclared-obligation" not in found


def test_a_claim_with_two_checks_and_a_bare_sibling_is_reported(repo: Path):
    write(repo / "docs/features/groom/concepts/publisher.md",
          "---\ntype: concept\nslug: publisher\ntitle: Publisher\n---\n# Publisher\n\n"
          "## Methods\n\n### Publish\n"
          "- returns: the published revision\n"
          '- verify: http_status(200, title="OK")\n'
          '- verify: http_status(201, title="Created")\n'
          "- raises: `ManifestConflict` when the revision moved\n")
    finding = next(f for f in _run(repo).findings if f.code == "uneven-claim-coverage")
    assert finding.severity == "error"
    assert finding.ref == f"{finding.path}#publish#returns:1"
    assert "raises:1" in finding.message


def test_a_claim_that_merely_under_verifies_is_not_reported(repo: Path):
    write(repo / "docs/features/groom/concepts/publisher.md",
          "---\ntype: concept\nslug: publisher\ntitle: Publisher\n---\n# Publisher\n\n"
          "## Methods\n\n### Publish\n"
          "- returns: the published revision\n"
          '- verify: http_status(200, title="OK")\n'
          "- raises: `ManifestConflict` when the revision moved\n")
    assert "uneven-claim-coverage" not in all_codes(_run(repo))


def test_a_self_declared_empty_raises_is_not_the_light_sibling(repo: Path):
    write(repo / "docs/features/groom/concepts/publisher.md",
          "---\ntype: concept\nslug: publisher\ntitle: Publisher\n---\n# Publisher\n\n"
          "## Methods\n\n### Publish\n"
          "- returns: the published revision\n"
          '- verify: http_status(200, title="OK")\n'
          '- verify: http_status(201, title="Created")\n'
          "- raises: nothing at all, because a refusal is a returned message rather than "
          "an error.\n")
    assert "uneven-claim-coverage" not in all_codes(_run(repo))


def test_a_bare_none_on_raises_is_still_the_light_sibling(repo: Path):
    write(repo / "docs/features/groom/concepts/publisher.md",
          "---\ntype: concept\nslug: publisher\ntitle: Publisher\n---\n# Publisher\n\n"
          "## Methods\n\n### Publish\n"
          "- returns: the published revision\n"
          '- verify: http_status(200, title="OK")\n'
          '- verify: http_status(201, title="Created")\n'
          "- raises: none\n")
    finding = next(f for f in _run(repo).findings if f.code == "uneven-claim-coverage")
    assert "raises:1" in finding.message


def test_a_node_whose_only_claim_self_declares_empty_owes_no_check(repo: Path):
    write(repo / "docs/features/groom/concepts/publisher.md",
          "---\ntype: concept\nslug: publisher\ntitle: Publisher\n---\n# Publisher\n\n"
          "## Methods\n\n### Publish\n"
          "- raises: nothing at all, because a refusal is a returned message rather than "
          "an error.\n")
    assert "undeclared-obligation" not in all_codes(_run(repo))


def test_a_node_whose_only_claim_is_a_bare_none_still_owes_a_check(repo: Path):
    write(repo / "docs/features/groom/concepts/publisher.md",
          "---\ntype: concept\nslug: publisher\ntitle: Publisher\n---\n# Publisher\n\n"
          "## Methods\n\n### Publish\n"
          "- raises: none\n")
    assert "undeclared-obligation" in all_codes(_run(repo))


def test_a_live_claim_beside_a_self_declared_empty_one_still_owes_a_check(repo: Path):
    write(repo / "docs/features/groom/concepts/publisher.md",
          "---\ntype: concept\nslug: publisher\ntitle: Publisher\n---\n# Publisher\n\n"
          "## Methods\n\n### Publish\n"
          "- returns: the published revision\n"
          "- raises: nothing at all, because a refusal is a returned message rather than "
          "an error.\n")
    finding = next(f for f in _run(repo).findings if f.code == "undeclared-obligation")
    assert "1 normative bullet " in finding.message


def test_a_check_that_cannot_go_red_is_reported(repo: Path):
    write(repo / "docs/features/groom/concepts/publisher.md",
          _method('json_path(path="$.revision", absent=false)'))
    finding = next(f for f in _run(repo).findings if f.code == "weak-check")
    assert finding.severity == "error"
    assert "passes on the default" in finding.message
    assert "#publish#returns:1" in finding.message
    assert finding.ref == f"{finding.path}#publish#returns:1"


def test_a_success_status_naming_neither_route_nor_title_is_weak(repo: Path):
    write(repo / "docs/features/groom/concepts/publisher.md", _method("http_status(200)"))
    assert "weak-check" in all_codes(_run(repo))


def test_one_discriminating_check_answers_the_claim_it_was_written_under(repo: Path):
    write(repo / "docs/features/groom/concepts/publisher.md",
          "---\ntype: concept\nslug: publisher\ntitle: Publisher\n---\n# Publisher\n\n"
          "## Methods\n\n### Publish\n- returns: the published revision\n"
          '- verify: json_path(path="$.revision", absent=false)\n'
          '- verify: json_path(path="$.state", equals="published")\n')
    assert "weak-check" not in all_codes(_run(repo))


def test_a_pattern_that_admits_any_value_is_weak_not_insensitive(repo: Path):
    write(repo / "docs/features/groom/concepts/publisher.md",
          _method('json_path(path="$.state", matches=".*")'))
    found = all_codes(_run(repo))
    assert "insensitive-check" not in found
    finding = next(f for f in _run(repo).findings if f.code == "weak-check")
    assert finding.severity == "error"
    assert "#publish#returns:1" in finding.ref


def test_a_plus_pattern_that_admits_any_value_is_weak_not_insensitive(repo: Path):
    write(repo / "docs/features/groom/concepts/publisher.md",
          _method('json_path(path="$.state", matches=".+")'))
    found = all_codes(_run(repo))
    assert "insensitive-check" not in found
    finding = next(f for f in _run(repo).findings if f.code == "weak-check")
    assert finding.severity == "error"


def test_a_discriminating_pattern_stays_a_check_not_a_stamp(repo: Path):
    write(repo / "docs/features/groom/concepts/publisher.md",
          _method('json_path(path="$.level", matches="^(INFO|DEBUG|TRACE)$")'))
    found = all_codes(_run(repo))
    assert "weak-check" not in found
    assert "insensitive-check" not in found


def test_an_equals_check_is_unaffected_by_the_matches_predicate(repo: Path):
    write(repo / "docs/features/groom/concepts/publisher.md",
          _method('json_path(path="$.state", equals="published")'))
    found = all_codes(_run(repo))
    assert "weak-check" not in found
    assert "insensitive-check" not in found


def test_a_pattern_no_witness_can_be_invented_for_has_no_result(repo: Path):
    write(repo / "docs/features/groom/concepts/publisher.md",
          _method('json_path(path="$.lang", matches="^(?=.{2}$)[a-z]+$")'))
    found = all_codes(_run(repo))
    assert "insensitive-check" not in found
    finding = next(f for f in _run(repo).findings if f.code == "unwitnessed-check")
    assert finding.severity == "warn"
    assert "#publish:returns:1" in finding.ref
    assert "no witness" in finding.message or "does not satisfy" in finding.message
    assert finding.suggestion is not None and "leave the check as it is" in finding.suggestion


def test_a_creation_verified_only_afterwards_is_reported(repo: Path):
    write(repo / "docs/features/groom/concepts/publisher.md",
          "---\ntype: concept\nslug: publisher\ntitle: Publisher\n---\n# Publisher\n\n"
          "## Methods\n\n### Publish\n"
          "- returns: the revision it creates under the caller's name\n"
          '- verify: http_status(201, path="/revisions")\n')
    finding = next(f for f in _run(repo).findings if f.code == "unstated-precondition")
    assert finding.severity == "warn"
    assert "creates something" in finding.message or "creates" in finding.message
    assert finding.suggestion is not None and "created(subject=" in finding.suggestion


def test_declaring_the_change_as_a_change_clears_it(repo: Path):
    write(repo / "docs/features/groom/concepts/publisher.md",
          "---\ntype: concept\nslug: publisher\ntitle: Publisher\n---\n# Publisher\n\n"
          "## Methods\n\n### Publish\n"
          "- returns: the revision it creates under the caller's name\n"
          '- verify: http_status(201, path="/revisions")\n'
          '- verify: created(subject="the revision")\n')
    assert "unstated-precondition" not in all_codes(_run(repo))


def test_a_claim_that_changes_no_existence_is_not_asked_for_a_before_read(repo: Path):
    write(repo / "docs/features/groom/concepts/publisher.md",
          "---\ntype: concept\nslug: publisher\ntitle: Publisher\n---\n# Publisher\n\n"
          "## Methods\n\n### Publish\n"
          "- returns: the issue the caller filed, and the register it was recorded in\n"
          '- verify: http_status(200, path="/revisions", title="OK")\n')
    assert "unstated-precondition" not in all_codes(_run(repo))


def test_a_lifecycle_claim_nothing_observes_is_not_this_rule_s_finding(repo: Path):
    """The shape no edit could clear, and the bulk of the 183 findings this rule used to raise."""
    write(repo / "docs/features/groom/concepts/publisher.md",
          "---\ntype: concept\nslug: publisher\ntitle: Publisher\n---\n# Publisher\n\n"
          "## Methods\n\n### Publish\n"
          "- returns: the revision it creates under the caller's name\n"
          "- does: the manifest is rewritten in place\n"
          '- verify: http_status(200, path="/revisions", title="OK")\n')
    assert "unstated-precondition" not in all_codes(_run(repo))


def test_a_sibling_claim_declaring_the_change_does_not_answer_this_one(repo: Path):
    """One `created(...)` on the node used to silence every lifecycle claim beside it."""
    write(repo / "docs/features/groom/concepts/publisher.md",
          "---\ntype: concept\nslug: publisher\ntitle: Publisher\n---\n# Publisher\n\n"
          "## Methods\n\n### Publish\n"
          "- returns: the revision it creates under the caller's name\n"
          '- verify: http_status(201, path="/revisions")\n'
          "- does: the manifest row is archived\n"
          '- verify: removed(subject="the manifest row")\n')
    finding = next(f for f in _run(repo).findings if f.code == "unstated-precondition")
    assert "creates" in finding.message
    assert finding.ref == f"{finding.path}#publish#returns:1"


def test_a_verb_its_own_sentence_negates_states_no_lifecycle_change(repo: Path):
    """`created(subject=…)` asserts the very thing the claim says does not happen."""
    write(repo / "docs/features/groom/concepts/publisher.md",
          "---\ntype: concept\nslug: publisher\ntitle: Publisher\n---\n# Publisher\n\n"
          "## Methods\n\n### Publish\n"
          "- does: a cancelled publish creates no revision and writes no manifest row\n"
          '- verify: absent(subject="a revision after a cancelled publish")\n')
    assert "unstated-precondition" not in all_codes(_run(repo))


def test_a_negator_governing_the_verb_from_the_left_also_clears_it(repo: Path):
    write(repo / "docs/features/groom/concepts/publisher.md",
          "---\ntype: concept\nslug: publisher\ntitle: Publisher\n---\n# Publisher\n\n"
          "## Methods\n\n### Publish\n"
          "- does: a replay reuses the existing revision instead of creating a duplicate\n"
          '- verify: unchanged(subject="the revision count after a replay")\n')
    assert "unstated-precondition" not in all_codes(_run(repo))


def test_a_state_dependent_alternative_is_not_an_unstated_precondition(repo: Path):
    """A toggle or upsert has no single lifecycle direction to observe."""
    claims = (
        "adds the mark to the selection, or strips it if every character already carries it",
        "creates the record when absent, or updates the existing record otherwise",
    )
    for claim in claims:
        write(repo / "docs/features/groom/concepts/publisher.md",
              "---\ntype: concept\nslug: publisher\ntitle: Publisher\n---\n# Publisher\n\n"
              "## Methods\n\n### Publish\n"
              f"- does: {claim}\n"
              '- verify: emitted(event="selection changed", count=1)\n')
        assert "unstated-precondition" not in all_codes(_run(repo)), claim


def test_a_verb_alternation_is_state_dependent_without_a_cue_word(repo: Path):
    """`restores or removes` is the prior-state condition, spelled as the alternation itself."""
    claims = (
        "restores or removes `name` when the block exits through an exception",
        "removes the override, or restores the value the caller shadowed",
    )
    for claim in claims:
        write(repo / "docs/features/groom/concepts/publisher.md",
              "---\ntype: concept\nslug: publisher\ntitle: Publisher\n---\n# Publisher\n\n"
              "## Methods\n\n### Publish\n"
              f"- does: {claim}\n"
              '- verify: emitted(event="scope exited", count=1)\n')
        assert "unstated-precondition" not in all_codes(_run(repo)), claim


def test_a_lone_alternative_marker_does_not_excuse_an_unconditional_creation(repo: Path):
    """The near-miss that keeps the alternation test tight rather than sentence-wide."""
    write(repo / "docs/features/groom/concepts/publisher.md",
          "---\ntype: concept\nslug: publisher\ntitle: Publisher\n---\n# Publisher\n\n"
          "## Methods\n\n### Publish\n"
          "- does: creates the revision, then updates the manifest row it points at or the\n"
          "  index that lists it\n"
          '- verify: http_status(201, path="/revisions")\n')
    finding = next(f for f in _run(repo).findings if f.code == "unstated-precondition")
    assert "creates" in finding.message


def test_a_negator_elsewhere_in_the_sentence_does_not_clear_a_real_creation(repo: Path):
    """The near-miss that makes the scoping load-bearing, not a detail of the implementation."""
    write(repo / "docs/features/groom/concepts/publisher.md",
          "---\ntype: concept\nslug: publisher\ntitle: Publisher\n---\n# Publisher\n\n"
          "## Methods\n\n### Publish\n"
          "- does: creates a new manifest and copies every existing row into it, without\n"
          "  mutating the manifest the caller passed in\n"
          '- verify: http_status(201, path="/revisions")\n')
    finding = next(f for f in _run(repo).findings if f.code == "unstated-precondition")
    assert "creates" in finding.message


def test_a_deletion_the_sentence_only_sequences_still_states_a_lifecycle_change(repo: Path):
    write(repo / "docs/features/groom/concepts/publisher.md",
          "---\ntype: concept\nslug: publisher\ntitle: Publisher\n---\n# Publisher\n\n"
          "## Methods\n\n### Publish\n"
          "- returns: an empty `204 No Content` after deleting the revision\n"
          '- verify: http_status(204, path="/revisions")\n')
    finding = next(f for f in _run(repo).findings if f.code == "unstated-precondition")
    assert "deleting" in finding.message


def test_emitting_a_request_is_not_a_change_of_existence(repo: Path):
    """`issues`/`issuing` left `LIFECYCLE_VERBS` on the constant's own stated criterion."""
    write(repo / "docs/features/groom/concepts/publisher.md",
          "---\ntype: concept\nslug: publisher\ntitle: Publisher\n---\n# Publisher\n\n"
          "## Methods\n\n### Publish\n"
          "- does: issues one `GET /manifest` against the api, never two\n"
          '- verify: emitted(event="GET /manifest", count=1)\n')
    assert "unstated-precondition" not in all_codes(_run(repo))


def test_a_key_that_describes_rather_than_acts_is_not_asked_for_a_before_read(repo: Path):
    write(repo / "docs/features/groom/concepts/publisher.md",
          "---\ntype: concept\nslug: publisher\ntitle: Publisher\n---\n# Publisher\n\n"
          "## Fields\n\n### Row Count\n"
          "- semantics: an empty value is read as zero; any other value the generator\n"
          "  inserts verbatim into the manifest\n"
          '- verify: json_path(path="$.rowCount", equals="0")\n')
    assert "unstated-precondition" not in all_codes(_run(repo))


def test_a_node_minting_no_obligation_is_not_asked_to_declare(repo: Path):
    write(repo / "docs/features/groom/gui/screens/s.md",
          "---\ntype: screen\nslug: s\ntitle: S\n---\n# S\n\n"
          "## Interactions\n\n### click\n- on: [S](#s)\n- trigger: click\n")
    assert "undeclared-obligation" not in all_codes(_run(repo))


def test_a_field_inherits_its_observation_from_the_record_that_carries_it(repo: Path):
    write(repo / "docs/features/groom/concepts/publisher.md",
          "---\ntype: concept\nslug: publisher\ntitle: Publisher\n---\n# Publisher\n\n"
          "## Fields\n\n### rowCount\n- type: integer\n- default: zero\n- required: no\n")
    assert "undeclared-obligation" not in all_codes(_run(repo))
    write(repo / "docs/features/groom/concepts/publisher.md",
          "---\ntype: concept\nslug: publisher\ntitle: Publisher\n---\n# Publisher\n\n"
          "## Fields\n\n### rowCount\n- type: integer\n- default: zero\n"
          "- verify: Test_Manifest_RowCount_Defaults\n")
    found = all_codes(_run(repo))
    assert "unparsed-check" in found and "undeclared-obligation" not in found


def test_a_type_that_carries_no_check_key_is_never_reported(repo: Path):
    write(repo / "docs/features/groom/runbooks/deploy.md",
          "---\ntype: runbook\nslug: deploy\ntitle: Deploy\n---\n# Deploy\n\n"
          "## Steps\n\n### Push\n- step: push the image\n"
          "- persistence: the tag is recorded in the registry\n")
    assert "undeclared-obligation" not in all_codes(_run(repo))


def test_a_claim_under_a_non_normative_key_is_reported(repo: Path):
    """A concept that mints nothing, stating a status code under its own `errors:` key: no obligation will ever carry it, so no plan is asked to prove it."""
    write(repo / "docs/features/groom/concepts/lease.md",
          "---\ntype: concept\nslug: lease\ntitle: Lease\n---\n# Lease\n\n"
          "- meaning: a lock over one path\n"
          "- errors: `409` when the lease is held by another worker\n"
          "- rules: the owner must renew before the deadline\n")
    report = _run(repo)
    hits = [f for f in report.findings if f.code == "unminted-claim"]
    assert [f.ref for f in hits] == ["docs/features/groom/concepts/lease.md#errors"]
    assert hits[0].severity == "warn"
    assert "names status 409" in hits[0].message
    assert "concept mints no obligation" in hits[0].message


def test_a_trigger_only_interaction_is_not_reported(repo: Path):
    write(repo / "docs/features/groom/gui/screens/s.md",
          "---\ntype: screen\nslug: s\ntitle: S\n---\n# S\n\n"
          "## Interactions\n\n### click\n- on: [S](#s)\n- trigger: click\n")
    assert "unminted-claim" not in all_codes(_run(repo))


def test_a_minting_node_is_still_asked_about_its_other_bullets(repo: Path):
    """The `persistence:` bullet being in QA's sight says nothing about whether `errors:` is — before this, a node-wide flag let one satisfied bullet vouch for its siblings."""
    write(repo / "docs/features/groom/concepts/lease.md",
          "---\ntype: concept\nslug: lease\ntitle: Lease\n---\n# Lease\n\n"
          "- persistence: the lease row is written once\n"
          "- errors: `409` when the lease is held by another worker\n")
    hits = [f for f in _run(repo).findings if f.code == "unminted-claim"]
    assert [f.ref for f in hits] == ["docs/features/groom/concepts/lease.md#errors"]


def test_a_minting_nodes_declared_keys_are_still_exempt(repo: Path):
    write(repo / "docs/features/groom/concepts/lease.md",
          "---\ntype: concept\nslug: lease\ntitle: Lease\n---\n# Lease\n\n"
          "- persistence: the lease row is written once\n"
          "- rule: prefer the newer lease when both return `409`\n")
    assert "unminted-claim" not in all_codes(_run(repo))


def test_an_untyped_section_with_a_status_bullet_is_reported(repo: Path):
    write(repo / "docs/features/groom/concepts/lease.md",
          "---\ntype: concept\nslug: lease\ntitle: Lease\n---\n# Lease\n\n"
          "## Notes\n\n### Renewal\n- outcome: `409` when the lease is held by another worker\n")
    hits = [f for f in _run(repo).findings if f.code == "unminted-claim"]
    assert [f.ref for f in hits] == ["docs/features/groom/concepts/lease.md#renewal#outcome"]


def test_an_undeclared_bullet_key_is_a_warning(repo: Path):
    """A `route:` on a concept is read by nobody — only a screen declares it — while the author who wrote it believes the concept is addressable."""
    write(repo / "docs/features/groom/concepts/diff.md",
          "---\ntype: concept\nslug: diff\ntitle: Diff\n---\n# Diff\n\n"
          "- code: `groom/diff.py::Diff`\n- verify: absent(subject=\"the row\")\n"
          "- route: /diff\n")
    report = _run(repo)
    hits = [f for f in report.findings if f.code == "unknown-bullet"]
    assert [f.ref for f in hits] == ["docs/features/groom/concepts/diff.md#route"]
    assert hits[0].severity == "warn"
    assert "concept declares" in hits[0].message


def test_an_undeclared_bullet_on_an_untyped_section_is_not_asked(repo: Path):
    write(repo / "docs/features/groom/concepts/diff.md",
          "---\ntype: concept\nslug: diff\ntitle: Diff\n---\n# Diff\n\n"
          "## Notes\n\n- verify: a word in prose, not a check\n")
    assert "unknown-bullet" not in all_codes(_run(repo))


def test_a_status_bullet_on_an_invocation_is_declared_and_formatted(repo: Path):
    """The key was graded for as long as the mapper existed and declared only now: `fmt` orders it between the effect and its grounding, and the `verify:` under it stays with it (`registry.attributed_checks` binds a check to the nearest claim above)."""
    write(repo / "docs/features/groom/cli/wh.md",
          "---\ntype: cli\nslug: wh\ntitle: WH\n---\n# WH\n\n"
          "## Invocations\n\n### run\n- on: [wh](#wh)\n- trigger: `wh run`\n"
          "- does:\n  - state: runs\n- code: `wh/run.py::run`\n"
          "- status: `0` on success\n- verify: exit_status(code=0)\n")
    assert "unknown-bullet" not in all_codes(_run(repo))
    fmt.run_fmt(load(repo), [])
    text = (repo / "docs/features/groom/cli/wh.md").read_text()
    assert text.index("- status:") < text.index("- verify:") < text.index("- code:")
    inv = load(repo).ui_nodes_of_type("invocation")[0]
    _, per_bullet = registry.attributed_checks(inv.type, inv.bullet_order, inv.combiners)
    assert per_bullet == {("status", 1): ["exit_status(code=0)"]}


def test_detail_is_declared_on_every_implementation_bearing_type(repo: Path):
    """`detail:` always resolved on any type — relations are global by key name — but only `command` and `endpoint` declared it, so on every other type it tripped `unknown-bullet` and `fmt` had no slot for it."""
    for node_type in ("screen", "cli", "server", "format", "flow", "component",
                      "interaction", "invocation", "method", "command", "endpoint"):
        assert "detail" in registry.declared_keys(node_type), node_type
    write(repo / "docs/features/groom/concepts/notify.md",
          "---\ntype: concept\nslug: notify\ntitle: Notify\n---\n# Notify\n")
    write(repo / "docs/features/groom/gui/screens/s.md",
          "---\ntype: screen\nslug: s\ntitle: S\n---\n# S\n\n"
          "## Components\n\n### banner\n- role: `status`\n- name: Banner\n"
          "- keyboard: none\n- states: shown\n"
          "- verify: visible(subject=\"the banner\")\n"
          "- detail: [Notify](../../concepts/notify.md)\n"
          "- code: `web/src/Banner.tsx::Banner`\n")
    assert "unknown-bullet" not in all_codes(_run(repo))
    fmt.run_fmt(load(repo), [])
    text = (repo / "docs/features/groom/gui/screens/s.md").read_text()
    assert text.index("- verify:") < text.index("- code:") < text.index("- detail:")


def test_code_is_declared_on_every_type(repo: Path):
    """`code:` grounds on every type (`registry.owning_keys`'s docstring — a flow or a screen cites the code it is grounded in whether or not its profile lists the key, and always has), but only some types' own profiles listed it in `bullet_keys`."""
    for node_type in registry.UI_TYPES_BY_NAME:
        assert "code" in registry.declared_keys(node_type), node_type

    write(repo / "docs/features/groom/gui/screens/s.md",
          "---\ntype: screen\nslug: s\ntitle: S\n---\n# S\n\n"
          "- route: `/s`\n- requires: none\n- params: none\n"
          "- code: `groom/groom/diff.py::Diff`\n")
    write(repo / "docs/features/groom/flows/f.md",
          "---\ntype: flow\nslug: f\ntitle: F\n---\n# F\n\n"
          "- start: begins\n- end: ends\n- code: `groom/groom/diff.py::Diff`\n")
    write(repo / "docs/features/groom/fixtures/fx.md",
          "---\ntype: fixture\nslug: fx\ntitle: FX\n---\n# FX\n\n"
          "- code: `groom/groom/diff.py::Diff`\n\n"
          "## Steps\n\n### boot\n- kind: seed\n- run: `groom/boot.sh`\n")
    write(repo / "docs/features/groom/concepts/notify.md",
          "---\ntype: concept\nslug: notify\ntitle: Notify\n---\n# Notify\n\n"
          "## Steps\n\n### boot\n- kind: prepare\n- code: `groom/groom/diff.py::Diff`\n\n"
          "## Notes\n\n### Detail\n- code: `groom/groom/diff.py::Diff`\n")
    write(repo / "groom/groom/diff.py", "class Diff:\n    pass\n")

    hits = [f for f in _run(repo).findings
            if f.code == "unknown-bullet" and f.ref and f.ref.endswith("#code")]
    assert hits == []


def test_concept_judgment_keys_are_advisory_relations(repo: Path):
    """`rule:`/`prefers:`/`deprecates:` are the concept's judgment vocabulary, and none is normative — a selection rule is not live-provable, so minting an obligation from one would demand evidence no scenario can produce."""
    for key in ("rule", "prefers", "deprecates"):
        assert key in registry.declared_keys("concept"), key
        assert key not in registry.normative_keys("concept"), key
    write(repo / "docs/features/groom/concepts/notify.md",
          "---\ntype: concept\nslug: notify\ntitle: Notify\n---\n# Notify\n\n"
          "- rule: reach for V2 unless the call site needs a synchronous send receipt\n"
          "- prefers: [gone](../gui/screens/gone.md)\n")
    hits = [f for f in _run(repo).findings if f.code == "unresolved-relation"]
    assert hits and "prefers" in hits[0].message
    write(repo / "docs/features/groom/http/api.md",
          "---\ntype: api\nslug: api\ntitle: API\n---\n# API\n\n"
          "## Endpoints\n\n### submit\n- method: POST\n- path: /x\n"
          "- does:\n  - state: submits the form\n- status: `201` on success\n"
          "- verify: http_status(code=201, path=\"/x\")\n"
          "- code: `api/submit.go::Submit`\n"
          "- rule: the author's own word here, not the concept vocabulary\n")
    codes = {f.code for f in _run(repo).findings
             if f.path == "docs/features/groom/http/api.md"}
    assert "unknown-bullet" not in codes


def _endpoint_file(slug: str, symbol: str, extra: str = "") -> str:
    return (f"---\ntype: api\nslug: {slug}\ntitle: {slug}\n---\n# {slug} API\n\n"
            f"## Endpoints\n\n### {slug}\n- method: POST\n- path: /{slug}\n"
            f"- does:\n  - state: sends the notification\n- status: `201` on success\n"
            f"- verify: http_status(code=201, path=\"/{slug}\")\n"
            f"- code: `{symbol}`\n{extra}")


def test_one_way_same_as_fires_when_the_target_does_not_name_it_back(repo: Path):
    write(repo / "docs/features/groom/concepts/notify-a.md",
          "---\ntype: concept\nslug: notify-a\ntitle: Notify A\n---\n# Notify A\n\n"
          "- same-as: [notify-b](../concepts/notify-b.md)\n")
    write(repo / "docs/features/groom/concepts/notify-b.md",
          "---\ntype: concept\nslug: notify-b\ntitle: Notify B\n---\n# Notify B\n\nNothing here.\n")
    hits = [f for f in _run(repo).findings if f.code == "one-way-same-as"]
    assert len(hits) == 1 and hits[0].severity == "error"
    hit = hits[0]
    assert hit.path == "docs/features/groom/concepts/notify-a.md"
    assert "notify-b" in hit.message
    assert hit.suggestion is not None
    assert "notify-b.md" in hit.suggestion
    assert "same-as: [Notify A]" in hit.suggestion
    assert "notify-a.md" in hit.suggestion


def test_one_way_same_as_silent_when_both_sides_name_each_other(repo: Path):
    write(repo / "docs/features/groom/concepts/notify-a.md",
          "---\ntype: concept\nslug: notify-a\ntitle: Notify A\n---\n# Notify A\n\n"
          "- same-as: [notify-b](../concepts/notify-b.md)\n")
    write(repo / "docs/features/groom/concepts/notify-b.md",
          "---\ntype: concept\nslug: notify-b\ntitle: Notify B\n---\n# Notify B\n\n"
          "- same-as: [notify-a](../concepts/notify-a.md)\n")
    assert "one-way-same-as" not in all_codes(_run(repo))


def test_one_way_same_as_silent_when_same_as_is_never_used(repo: Path):
    write(repo / "docs/features/groom/concepts/notify.md",
          "---\ntype: concept\nslug: notify\ntitle: Notify\n---\n# Notify\n\nNothing here.\n")
    assert "one-way-same-as" not in all_codes(_run(repo))


def test_one_way_same_as_does_not_fire_for_a_dangling_target(repo: Path):
    """A `same-as:` value that resolves nowhere is `unresolved-relation`'s finding, raised by the document-wide link pass — this check only judges a claim once it lands on a real node, so the two never double-report the same broken bullet."""
    write(repo / "docs/features/groom/concepts/notify-a.md",
          "---\ntype: concept\nslug: notify-a\ntitle: Notify A\n---\n# Notify A\n\n"
          "- same-as: [gone](../concepts/gone.md)\n")
    codeset = all_codes(_run(repo))
    assert "unresolved-relation" in codeset
    assert "one-way-same-as" not in codeset


def test_one_way_same_as_is_checked_per_edge_not_per_family(repo: Path):
    """The addendum's chain: A<->B, B<->C, C<->D, all reciprocated pairwise."""
    write(repo / "docs/features/groom/concepts/notify-a.md",
          "---\ntype: concept\nslug: notify-a\ntitle: Notify A\n---\n# Notify A\n\n"
          "- code: `internal/notify.go::Notify`\n"
          "- same-as: [notify-b](../concepts/notify-b.md)\n")
    write(repo / "docs/features/groom/concepts/notify-b.md",
          "---\ntype: concept\nslug: notify-b\ntitle: Notify B\n---\n# Notify B\n\n"
          "- code: `internal/notify.go::Notify`\n"
          "- same-as: [notify-a](../concepts/notify-a.md)\n"
          "- same-as: [notify-c](../concepts/notify-c.md)\n")
    write(repo / "docs/features/groom/concepts/notify-c.md",
          "---\ntype: concept\nslug: notify-c\ntitle: Notify C\n---\n# Notify C\n\n"
          "- code: `internal/notify.go::Notify`\n"
          "- same-as: [notify-b](../concepts/notify-b.md)\n"
          "- same-as: [notify-d](../concepts/notify-d.md)\n")
    write(repo / "docs/features/groom/concepts/notify-d.md",
          "---\ntype: concept\nslug: notify-d\ntitle: Notify D\n---\n# Notify D\n\n"
          "- code: `internal/notify.go::Notify`\n"
          "- same-as: [notify-c](../concepts/notify-c.md)\n")
    assert "one-way-same-as" not in all_codes(_run(repo))


def test_deprecation_without_successor(repo: Path):
    """A concept whose `deprecates:` resolves but that names no `prefers:` and no `rule:` reads as "delete this" — usually wrong."""
    write(repo / "docs/features/groom/concepts/legacy.md",
          "---\ntype: concept\nslug: legacy\ntitle: Legacy\n---\n# Legacy\n\nOld path.\n")
    write(repo / "docs/features/groom/concepts/notify.md",
          "---\ntype: concept\nslug: notify\ntitle: Notify\n---\n# Notify\n\n"
          "- deprecates: [legacy](legacy.md)\n")
    hits = [f for f in _run(repo).findings if f.code == "deprecation-without-successor"]
    assert len(hits) == 1 and hits[0].severity == "warn"
    assert "prefers" in hits[0].message
    write(repo / "docs/features/groom/concepts/notify.md",
          "---\ntype: concept\nslug: notify\ntitle: Notify\n---\n# Notify\n\n"
          "- rule: legacy remains only for the dunning sequence's synchronous receipt\n"
          "- deprecates: [legacy](legacy.md)\n")
    assert "deprecation-without-successor" not in all_codes(_run(repo))
    write(repo / "docs/features/groom/concepts/notify.md",
          "---\ntype: concept\nslug: notify\ntitle: Notify\n---\n# Notify\n\n"
          "- deprecates: [gone](gone.md)\n")
    report = _run(repo)
    assert "unresolved-relation" in all_codes(report)
    assert "deprecation-without-successor" not in all_codes(report)


def test_ungrounded_unspecified(repo: Path):
    """An `unspecified:` bullet is resolved-by-design only on the strength of its citation."""
    write(repo / "docs/decisions/0007-export-encoding.md",
          "# 0007 — export encoding\n\nEncoding order is the consumer's concern.\n")
    cited = ("- unspecified: the export's field encoding order — settled in "
             "[0007](../../../decisions/0007-export-encoding.md)\n")
    write(repo / "docs/features/groom/http/v1.md",
          _endpoint_file("v1", "internal/notify.go::Notify", cited))
    assert "ungrounded-unspecified" not in all_codes(_run(repo))
    write(repo / "docs/features/groom/http/v1.md",
          _endpoint_file("v1", "internal/notify.go::Notify",
                         "- unspecified: the export's field encoding order\n"))
    hits = [f for f in _run(repo).findings if f.code == "ungrounded-unspecified"]
    assert len(hits) == 1 and hits[0].severity == "error"
    assert "cites no record" in hits[0].message
    assert "delete the bullet" in (hits[0].suggestion or "")
    write(repo / "docs/features/groom/http/v1.md",
          _endpoint_file("v1", "internal/notify.go::Notify",
                         "- unspecified: the export's field encoding order — settled in "
                         "[gone](../../../decisions/gone.md)\n"))
    hits = [f for f in _run(repo).findings if f.code == "ungrounded-unspecified"]
    assert len(hits) == 1 and hits[0].severity == "error"
    assert "does not resolve" in hits[0].message


def test_all_ui_findings_are_errors(repo: Path):
    write(repo / "docs/features/groom/concepts/diff.md",
          "---\ntype: concept\nslug: diff\ntitle: Diff\n---\n# Diff\n\n"
          "See [gone](../gui/screens/gone.md).\n")
    report = _run(repo)
    ui_codes = {"unknown-type", "missing-required-section", "missing-required-bullet",
                "dangling-link", "missing-anchor", "unresolved-relation", "bad-heading-type"}
    for f in report.findings:
        if f.code in ui_codes:
            assert f.severity == "error"


def test_scaffold_then_fmt_converges(repo: Path):
    write(repo / "docs/features/groom/gui/screens/s.md",
          "---\ntype: screen\nslug: s\ntitle: S\n---\n# S\n\n"
          "## interactions\n\n### click\n- on: [x](#s)\n- trigger: click\n- does:\n  - state: x\n")
    assert "bad-heading-type" in codes(_run(repo))
    fmt.run_fmt(load(repo), [])
    assert "bad-heading-type" not in codes(_run(repo))


def test_missing_section_fixed_by_scaffold(repo: Path):
    scaffold.scaffold(load(repo), "cli", "wh", service="workhorse")
    report = _run(repo)
    assert "missing-required-section" not in codes(report)


def test_code_and_tests_not_grounded_at_author_time(repo: Path):
    write(repo / "docs/features/groom/gui/screens/s.md",
          "---\ntype: screen\nslug: s\ntitle: S\n---\n# S\n\n"
          "## Interactions\n\n### click\n- on: [x](#s)\n- trigger: click\n- does:\n  - state: x\n"
          "- code: `groom/groom/nope.py::ghost`\n- tests: `tests/test_nope.py::ghost`\n")
    report = _run(repo)
    assert "dangling-link" not in codes(report)
    assert "unresolved-relation" not in codes(report)
    assert "unparsed-check" not in codes(report)


LINKED_SCREEN = """\
---
type: screen
slug: changes-view
title: Changes view
---
# Changes view

- route: /
- requires: none
- params: none

Presents the [diff](../../concepts/diff.md) concept and a [gone](./gone.md) one.

## Components

### changes-file-row
- selector: `div.tree-file`
- role: button
- name: Row
- extends: [tree-node](../components/design-system.md#tree-node)
- keyboard: Enter activates
- verify: visible(locator="#changes-file-row")

## Interactions

### click-file
- on: [changes-file-row](#changes-file-row)
- trigger: click
- role: button
- name: Row
- keyboard: Enter
- verify: visible(locator="#changes-file-row", text="marked")
- does:
  - state: mark row
"""

LINKED_DS = """\
---
type: feature
slug: design-system
title: DS
---
# DS

## Components

### tree-node
- selector: `div.tree-file`
- role: button
- name: Node
- keyboard: Enter activates
- verify: visible(locator="#tree-node")
"""

LINKED_DIFF = """\
---
type: concept
slug: diff
title: Diff
---
# Diff

A unified diff. See [ghost](./diff.md#nope).
"""

LINKED_REPORT_JSON = """\
{
  "epics": [],
  "errors": 3,
  "findings": [
    {
      "code": "missing-anchor",
      "epic": "",
      "fixable": true,
      "line": 8,
      "message": "docs/features/groom/concepts/diff.md: link './diff.md#nope' — file exists but `#nope` heading not found",
      "node": "",
      "path": "docs/features/groom/concepts/diff.md",
      "ref": "docs/features/groom/concepts/diff.md:8:./diff.md#nope",
      "related": [],
      "severity": "error",
      "suggestion": ""
    },
    {
      "code": "dangling-link",
      "epic": "",
      "fixable": true,
      "line": 12,
      "message": "docs/features/groom/gui/screens/changes-view.md: link './gone.md' target file does not exist",
      "node": "",
      "path": "docs/features/groom/gui/screens/changes-view.md",
      "ref": "docs/features/groom/gui/screens/changes-view.md:12:./gone.md",
      "related": [],
      "severity": "error",
      "suggestion": ""
    },
    {
      "code": "runbook-missing",
      "epic": "",
      "fixable": false,
      "line": 0,
      "message": "no `runbook` node brings a system up: the book describes a surface that has to be served and never says how it starts, so QA has no stack to run against",
      "node": "",
      "path": "",
      "ref": "",
      "related": [],
      "severity": "error",
      "suggestion": "ostler scaffold runbook qa-stack --service <service>"
    }
  ],
  "profile": "exploration",
  "warnings": 0
}"""


def _linked_book(root: Path) -> Path:
    """A book whose only findings come from link resolution — the machinery being shared."""
    write(root / "docs/features/groom/gui/screens/changes-view.md", LINKED_SCREEN)
    write(root / "docs/features/groom/gui/components/design-system.md", LINKED_DS)
    write(root / "docs/features/groom/concepts/diff.md", LINKED_DIFF)
    return root


def _watch_resolvers(monkeypatch) -> tuple[list, list]:
    """Record every ``LinkResolver`` constructed and every anchor set computed."""
    made: list[links.LinkResolver] = []
    computed: list[Path] = []
    real_init = links.LinkResolver.__init__
    real_compute = links.LinkResolver._compute_anchors

    def spy_init(self, graph, *args, **kwargs) -> None:
        real_init(self, graph, *args, **kwargs)
        made.append(self)

    def spy_compute(self, path: Path) -> set[str]:
        computed.append(path)
        return real_compute(self, path)

    monkeypatch.setattr(links.LinkResolver, "__init__", spy_init)
    monkeypatch.setattr(links.LinkResolver, "_compute_anchors", spy_compute)
    return made, computed


def test_a_doctor_run_constructs_exactly_one_link_resolver(repo: Path, monkeypatch):
    """The graph build and the UI checks share one resolver."""
    _linked_book(repo)
    made, _ = _watch_resolvers(monkeypatch)
    doctor.run(load(repo))
    assert len(made) == 1, f"{len(made)} LinkResolvers built in one doctor run, want 1"


def test_a_doctor_run_computes_a_target_file_anchor_set_once(repo: Path, monkeypatch):
    _linked_book(repo)
    _, computed = _watch_resolvers(monkeypatch)
    doctor.run(load(repo))
    assert computed, "no anchor set computed at all — the fixture stopped exercising links"
    twice = sorted({str(p) for p in computed if computed.count(p) > 1})
    assert not twice, f"anchors recomputed for {twice}"


def test_sharing_the_resolver_leaves_the_report_byte_identical(tmp_path: Path, monkeypatch):
    made, _ = _watch_resolvers(monkeypatch)
    report = doctor.run(load(_linked_book(tmp_path)))
    payload = report.as_dict()
    payload.pop("org")
    assert json.dumps(payload, indent=2, sort_keys=True,
                      ensure_ascii=False) == LINKED_REPORT_JSON
    assert len(made) == 1, f"{len(made)} LinkResolvers built in one doctor run, want 1"


def test_a_sibling_claims_strong_check_no_longer_answers_this_one(repo: Path):
    """The fan-out this rule used to have: one discriminating check anywhere on the node silenced it for every other bullet, so a claim observed only by a rubber stamp read as judged."""
    write(repo / "docs/features/groom/concepts/publisher.md",
          "---\ntype: concept\nslug: publisher\ntitle: Publisher\n---\n# Publisher\n\n"
          "## Methods\n\n### Publish\n"
          "- returns: the published revision\n"
          '- verify: json_path(path="$.state", equals="published")\n'
          "- raises: a conflict when the revision moved under the caller\n"
          '- verify: json_path(path="$.revision", absent=false)\n')
    findings = [f for f in _run(repo).findings if f.code == "weak-check"]
    assert [f.message for f in findings] and all(
        "#publish#raises:1" in f.message for f in findings
    )


def test_the_finding_names_which_claim_when_siblings_share_the_key(repo: Path):
    """Two `does:` bullets, one already answered — the finding has to say which is the other."""
    write(repo / "docs/features/groom/concepts/publisher.md",
          "---\ntype: concept\nslug: publisher\ntitle: Publisher\n---\n# Publisher\n\n"
          "## Methods\n\n### Publish\n"
          "- does: collapses the manifest and removes its surrounding whitespace\n"
          '- verify: json_path(path="$.manifest", equals="tidy")\n'
          "- does: removes the trailing separator from the normalized manifest\n"
          '- verify: removed(subject="the trailing separator")\n')
    finding = next(f for f in _run(repo).findings if f.code == "unstated-precondition")
    assert "does:1" in finding.message, finding.message
    assert "surrounding whitespace" in finding.message, finding.message
    assert "trailing separator" not in finding.message, finding.message


def _node(repo: Path, body: str) -> Path:
    """A concept with two sibling bullets under one key, at a stable path."""
    path = repo / "docs/features/groom/concepts/publisher.md"
    write(path, "---\ntype: concept\nslug: publisher\ntitle: Publisher\n---\n# Publisher\n\n"
                "## Methods\n\n### Publish\n" + body)
    return path


def _refs(repo: Path, code: str) -> list[str]:
    return [f.ref for f in _run(repo).findings if f.code == code]


NODE = "docs/features/groom/concepts/publisher.md#publish"


def test_overlong_normative_bullet_names_which_bullet_is_too_long(repo: Path):
    long = "the manifest is rewritten again " * 22
    _node(repo, f"- does: collapses the manifest\n- does: {long}\n")
    assert _refs(repo, "overlong-normative-bullet") == [f"{NODE}#does:2"]


def test_relation_without_subject_names_which_bullet_lacks_one(repo: Path):
    _node(repo, "- persistence: payout-record — the row is written before the reply\n"
                "- persistence: the row is written before the reply\n")
    findings = [f for f in _run(repo).findings if f.code == "relation-without-subject"]
    assert [f.ref for f in findings] == [f"{NODE}#persistence:2"]
    assert "`persistence:2`" in findings[0].message


def test_compound_normative_bullet_names_which_bullet_states_two(repo: Path):
    _node(repo, "- does: collapses the manifest\n"
                "- does: collapses the manifest and rejects a revision, and logs the reason\n")
    assert _refs(repo, "compound-normative-bullet") == [f"{NODE}#does:2"]


def test_unparsed_check_names_which_verify_failed(repo: Path):
    _node(repo, "- does: collapses the manifest\n"
                '- verify: json_path(path="$.state", equals="published")\n'
                '- verify: json_path(path="$.order", equals=None)\n')
    findings = [f for f in _run(repo).findings if f.code == "unparsed-check"]
    assert [f.ref for f in findings] == [f"{NODE}#verify:2"]
    assert "equals=None" in findings[0].message
    assert "$.state" not in findings[0].message


def test_known_defect_findings_name_which_defect_bullet(repo: Path):
    _node(repo, "- does: collapses the manifest\n"
                "- known-defect: not a defect declaration\n")
    assert _refs(repo, "stale-defect") == [f"{NODE}#known-defect:1"]


def _capture_endpoint(capture: str) -> str:
    return ("---\ntype: api\nslug: api\ntitle: API\n---\n# API\n\n"
            "## Endpoints\n\n### submit\n- method: POST\n- path: /x\n"
            "- does:\n  - state: submits the form\n- status: `201` on success\n"
            "- verify: http_status(code=201, path=\"/x\")\n"
            f"- capture: {capture}\n"
            "- code: `api/submit.go::Submit`\n")


def test_a_capture_bullet_with_no_source_is_refused(repo: Path):
    """Before this checker existed, nobody read this bullet."""
    write(repo / "docs/features/groom/http/api.md", _capture_endpoint("claim_id $.id"))
    finding = next(f for f in _run(repo).findings if f.code == "unparsed-capture")
    assert finding.severity == "error"
    assert "names no source" in finding.message
    assert finding.suggestion and " from " in finding.suggestion


def test_a_capture_name_a_reference_could_never_spell_is_refused(repo: Path):
    """The declaration mints the name and `$name` spells it, so a name `references` would not accept is a fact nothing in the book can ever refer to — a declaration that reads fine and resolves for nobody."""
    write(repo / "docs/features/groom/http/api.md", _capture_endpoint("$claim_id from $.id"))
    finding = next(f for f in _run(repo).findings if f.code == "unparsed-capture")
    assert "`$` a reference spells" in finding.message


def test_a_well_formed_capture_bullet_grounds(repo: Path):
    write(repo / "docs/features/groom/http/api.md", _capture_endpoint("claim_id from $.id"))
    assert "unparsed-capture" not in all_codes(_run(repo))


def test_self_relation_fires_when_a_relation_bullet_points_at_its_own_node(repo: Path):
    write(repo / "docs/features/groom/concepts/render-context.md",
          "---\ntype: concept\nslug: render-context\ntitle: Render Context\n---\n"
          "# Render Context\n\n- detail: [render-context](render-context.md)\n")
    hits = [f for f in _run(repo).findings if f.code == "self-relation"]
    assert len(hits) == 1 and hits[0].severity == "error"
    hit = hits[0]
    assert hit.path == "docs/features/groom/concepts/render-context.md"
    assert "`detail: render-context.md`" in hit.message
    assert hit.ref.endswith("#detail:1")
    assert hit.suggestion is not None


def test_self_relation_fires_on_any_relation_key_not_just_detail(repo: Path):
    """Nothing about the defect is particular to a key: a relation is between two things whichever key names it, so the check is quantified over `RELATION_KEYS` rather than written once per key."""
    write(repo / "docs/features/groom/gui/screens/harness.md",
          "---\ntype: screen\nslug: harness\ntitle: Harness\n---\n# Harness\n\n"
          "- route: `/harness`\n\n## Components\n\n### tab\n- role: tab\n"
          "- exclusive-with: [tab](#tab)\n")
    hits = [f for f in _run(repo).findings if f.code == "self-relation"]
    assert len(hits) == 1
    assert hits[0].ref.endswith("#exclusive-with:1")


def test_self_relation_addresses_the_one_bullet_not_the_whole_key(repo: Path):
    """The remedy is per bullet — repoint this link, or delete it — so a node stating the key twice and self-referencing on the second occurrence is addressed at `:2`."""
    write(repo / "docs/features/groom/concepts/other.md",
          "---\ntype: concept\nslug: other\ntitle: Other\n---\n# Other\n\nNothing here.\n")
    write(repo / "docs/features/groom/concepts/schema.md",
          "---\ntype: concept\nslug: schema\ntitle: Schema\n---\n# Schema\n\n"
          "- detail: [other](other.md)\n- detail: [schema](schema.md)\n")
    hits = [f for f in _run(repo).findings if f.code == "self-relation"]
    assert len(hits) == 1
    assert hits[0].ref.endswith("#detail:2")


def test_self_relation_is_silent_for_a_relation_between_two_nodes(repo: Path):
    write(repo / "docs/features/groom/concepts/other.md",
          "---\ntype: concept\nslug: other\ntitle: Other\n---\n# Other\n\nNothing here.\n")
    write(repo / "docs/features/groom/concepts/schema.md",
          "---\ntype: concept\nslug: schema\ntitle: Schema\n---\n# Schema\n\n"
          "- detail: [other](other.md)\n")
    codeset = all_codes(_run(repo))
    assert "unresolved-relation" not in codeset
    assert "self-relation" not in codeset


def test_self_relation_does_not_fire_for_a_dangling_target(repo: Path):
    """A target that resolves nowhere is `unresolved-relation`'s finding."""
    write(repo / "docs/features/groom/concepts/schema.md",
          "---\ntype: concept\nslug: schema\ntitle: Schema\n---\n# Schema\n\n"
          "- detail: [gone](gone.md)\n")
    codeset = all_codes(_run(repo))
    assert "unresolved-relation" in codeset
    assert "self-relation" not in codeset


def test_self_relation_separates_a_node_from_the_page_it_sits_on(repo: Path):
    """A link with no anchor resolves to the file's root node, so a `### part` citing its own page is a relation between two different nodes and is legal."""
    write(repo / "docs/features/groom/gui/screens/harness.md",
          "---\ntype: screen\nslug: harness\ntitle: Harness\n---\n# Harness\n\n"
          "- route: `/harness`\n- detail: [tab](#tab)\n\n## Components\n\n### tab\n"
          "- role: tab\n")
    codeset = all_codes(_run(repo))
    assert "unresolved-relation" not in codeset
    assert "self-relation" not in codeset
