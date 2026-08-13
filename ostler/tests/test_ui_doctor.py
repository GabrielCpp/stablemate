"""`ostler doctor` as a mandatory UI-profile linter (docs/okf-ui-support §7).

Every rule is an *error* with a deterministic remedy (fmt / scaffold), and every finding carries a
file+line location. The convergence contract: scaffolding then fmt'ing a node clears its findings.
"""

from __future__ import annotations

from pathlib import Path

from ostler import doctor, fmt, scaffold
from ostler.model import load

from conftest import write


def codes(report):
    return {f.code for f in report.findings if f.severity == "error"}


def all_codes(report):
    """Every finding, warns included — `codes` reads errors only, and one UI rule is a warn."""
    return {f.code for f in report.findings}


def _run(repo: Path):
    return doctor.run(load(repo))


# ---------------------------------------------------------------------------
# individual rules
# ---------------------------------------------------------------------------
def test_unknown_type(repo: Path):
    write(repo / "docs/features/x.md", "---\ntype: widget\nslug: x\ntitle: X\n---\n# X\n")
    report = _run(repo)
    assert "unknown-type" in codes(report)
    finding = next(f for f in report.findings if f.code == "unknown-type")
    assert finding.path == "docs/features/x.md" and finding.line == 1


def test_link_validation_is_document_wide(repo: Path):
    # a broken link in a PROSE section (owned by no typed node) is still caught — link-correctness
    # is independent of the graph.
    write(repo / "docs/features/x.md",
          "---\ntype: concept\nslug: x\ntitle: X\n---\n# X\n\n## Notes\n\nSee [gone](./nope.md).\n")
    assert "dangling-link" in codes(_run(repo))


def test_link_validation_skips_code(repo: Path):
    # a `](` inside inline code or a fence is not a link — no false dangling-link.
    write(repo / "docs/features/x.md",
          "---\ntype: concept\nslug: x\ntitle: X\n---\n# X\n\n## Notes\n\n"
          "Inline `arr[i](nope.md)` and\n\n```\nf = g[i](also-nope.md)\n```\n")
    assert "dangling-link" not in codes(_run(repo))


def test_known_types_not_flagged(repo: Path):
    write(repo / "docs/features/x.md", "---\ntype: concept\nslug: x\ntitle: X\n---\n# X\n")
    assert "unknown-type" not in codes(_run(repo))


def test_missing_required_section(repo: Path):
    # a cli must have `## Commands`
    write(repo / "docs/features/workhorse/workhorse.md",
          "---\ntype: cli\nslug: wh\ntitle: WH\n---\n# WH\n\n- binary: `wh`\n")
    report = _run(repo)
    assert "missing-required-section" in codes(report)
    finding = next(f for f in report.findings if f.code == "missing-required-section")
    assert finding.fixable and finding.suggestion == "## Commands"


def test_missing_required_bullet(repo: Path):
    # an interaction requires on/trigger/does
    write(repo / "docs/features/groom/gui/screens/s.md",
          "---\ntype: screen\nslug: s\ntitle: S\n---\n# S\n\n"
          "## Interactions\n\n### click\n- trigger: click\n")
    report = _run(repo)
    missing = {f.ref for f in report.findings if f.code == "missing-required-bullet"}
    assert "on" in missing and "does" in missing
    assert "trigger" not in missing   # present


def _screen_with(repo: Path, bullets: str) -> None:
    write(repo / "docs/features/groom/gui/screens/s.md",
          "---\ntype: screen\nslug: s\ntitle: S\n---\n# S\n\n"
          f"## Components\n\n### body\n{bullets}")


def test_a_component_that_carries_the_page_says_where_it_sits(repo: Path):
    """`role:` and `name:` are the accessibility contract, and a scenario asserting on them
    passes on a component crushed into a column against one margin — which is a defect that
    reached a green run. `placement:` is the documented fact that check cannot carry, and it
    is asked only of the roles that carry a page."""
    _screen_with(repo, "- role: article\n- name: none\n")
    report = _run(repo)
    assert "missing-placement" in codes(report)
    finding = next(f for f in report.findings if f.code == "missing-placement")
    assert finding.ref == "docs/features/groom/gui/screens/s.md#body#placement", finding.ref
    assert finding.path == "docs/features/groom/gui/screens/s.md" and finding.line

    _screen_with(repo, "- role: article\n- name: none\n- placement: width 60-100%, x 0-20%\n")
    assert "missing-placement" not in codes(_run(repo))

    # A button's placement is brittle and proves nothing, so it is never demanded.
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
    # One `does:` carrying a paragraph is several obligations wearing one id — the scenario
    # that covers it proves whichever clause the planner happened to read.
    write(repo / "docs/features/groom/gui/screens/s.md", _interaction("the row saves. " * 60))
    report = _run(repo)
    finding = next(f for f in report.findings if f.code == "overlong-normative-bullet")
    assert finding.severity == "error"
    # Per bullet, not per key: a waiver has to name the one bullet, not silence `does:` book-wide.
    assert finding.path == "docs/features/groom/gui/screens/s.md"
    assert finding.ref == f"{finding.path}#click#does"


def test_a_short_normative_bullet_is_not_flagged(repo: Path):
    write(repo / "docs/features/groom/gui/screens/s.md", _interaction("the row saves."))
    assert "overlong-normative-bullet" not in codes(_run(repo))


def test_code_spans_and_link_hrefs_do_not_count_as_prose(repo: Path):
    # A cited symbol says one thing however many characters it spells, and an href is
    # addressing rather than prose. A bullet long only because of them is not overlong.
    padding = "`" + "x" * 900 + "` [see](" + "y" * 100 + ".md)"
    write(repo / "docs/features/groom/gui/screens/s.md",
          _interaction(f"the row saves, per {padding}."))
    assert "overlong-normative-bullet" not in codes(_run(repo))


def test_a_parenthetical_counts_as_prose(repo: Path):
    # An aside is exactly where a second requirement hides, so discounting parentheticals
    # would exempt the shape this rule exists to find.
    write(repo / "docs/features/groom/gui/screens/s.md",
          _interaction("the row saves (" + "and the audit row records it. " * 30 + ")"))
    assert "overlong-normative-bullet" in codes(_run(repo))


def test_only_normative_bullets_are_measured(repo: Path):
    # `trigger:` mints no obligation, so its length buys nobody a scenario and is not this
    # rule's business.
    write(repo / "docs/features/groom/gui/screens/s.md",
          "---\ntype: screen\nslug: s\ntitle: S\n---\n# S\n\n"
          "## Interactions\n\n### click\n- on: [S](#s)\n"
          f"- trigger: {'click the row. ' * 60}\n- does: the row saves.\n")
    assert "overlong-normative-bullet" not in codes(_run(repo))


def test_a_bullet_enumerating_status_branches_is_compound(repo: Path):
    # The shape this rule exists for: one `does:` restating an endpoint's whole branch table.
    # It is well under the length limit and it is five obligations.
    write(repo / "docs/features/groom/gui/screens/s.md",
          _interaction("returns `400` on a malformed body, `409` on a stale manifest, "
                       "and `200` with the published page otherwise"))
    finding = next(f for f in _run(repo).findings if f.code == "compound-normative-bullet")
    assert finding.severity == "warn"   # splitting is authoring judgment, not a `fmt` fix
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


def test_listing_two_nouns_is_not_compound(repo: Path):
    # A rule that fires on every `and` is a rule people learn to ignore, and an ignored rule
    # leaves the fat bullets exactly where they were.
    write(repo / "docs/features/groom/gui/screens/s.md",
          _interaction("the page and its slug are written to the manifest"))
    assert "compound-normative-bullet" not in all_codes(_run(repo))


def test_one_status_code_is_not_compound(repo: Path):
    write(repo / "docs/features/groom/gui/screens/s.md",
          _interaction("returns `409` when the manifest revision moved under the write"))
    assert "compound-normative-bullet" not in all_codes(_run(repo))


def test_an_overlong_bullet_is_reported_once(repo: Path):
    # Both rules say "this is several obligations"; saying it twice about one bullet buys the
    # author nothing and costs a second thing to waive.
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
    # The direction the whole vocabulary reverses: a test id says which code ran, so an
    # assertion filed under it can be arbitrarily weaker than the claim and still cite it.
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


def test_a_node_that_declares_nothing_is_reported(repo: Path):
    # The gap `unparsed-check` cannot see: no value to reject. `verify:` is required on no
    # type, so this node is otherwise green while every obligation it mints reaches QA with
    # nothing to bind — `qa validate` has no declaration to enforce and the evidence map has
    # no deficit to report.
    write(repo / "docs/features/groom/concepts/publisher.md",
          "---\ntype: concept\nslug: publisher\ntitle: Publisher\n---\n# Publisher\n\n"
          "## Methods\n\n### Publish\n- returns: the published revision\n"
          "- raises: `ManifestConflict` when the revision moved\n")
    finding = next(f for f in _run(repo).findings if f.code == "undeclared-obligation")
    assert finding.severity == "warn"   # declaring is authoring judgment, not a `fmt` fix
    assert "2 normative bullets" in finding.message
    # Reported once per node across a whole book, so the vocabulary rides in the suggestion
    # rather than in every line of it.
    assert finding.suggestion is not None and "http_status" in finding.suggestion
    assert finding.ref == f"{finding.path}#publish#verify"


def test_one_declaration_answers_the_node(repo: Path):
    # Node-level and not a count: `verify:` sits on the node, and pairing one check to one
    # bullet is a judgement nobody has written down yet. Asking for parity would invent it.
    write(repo / "docs/features/groom/concepts/publisher.md",
          "---\ntype: concept\nslug: publisher\ntitle: Publisher\n---\n# Publisher\n\n"
          "## Methods\n\n### Publish\n- returns: the published revision\n"
          "- raises: `ManifestConflict` when the revision moved\n"
          '- verify: http_status(409, title="Manifest Conflict")\n')
    assert "undeclared-obligation" not in all_codes(_run(repo))


def test_a_declaration_that_does_not_parse_is_reported_once(repo: Path):
    # Both rules would say "this node declares no observation"; the author who wrote a test id
    # is already being told the one thing there is to do about it.
    write(repo / "docs/features/groom/concepts/publisher.md",
          _method("Test_Service_Publish_ShouldConflict"))
    found = all_codes(_run(repo))
    assert "unparsed-check" in found
    assert "undeclared-obligation" not in found


def test_a_node_minting_no_obligation_is_not_asked_to_declare(repo: Path):
    # Nothing to observe: an interaction recorded only by its trigger owes no check, and a rule
    # that asked anyway would be noise on the descriptive half of the book.
    write(repo / "docs/features/groom/gui/screens/s.md",
          "---\ntype: screen\nslug: s\ntitle: S\n---\n# S\n\n"
          "## Interactions\n\n### click\n- on: [S](#s)\n- trigger: click\n")
    assert "undeclared-obligation" not in all_codes(_run(repo))


def test_a_type_that_carries_no_check_key_is_never_reported(repo: Path):
    # A `step:` under a runbook mints obligations too, but its `verify:` keeps its own older
    # meaning — how to tell the step ran — and is not a check. There is no declaration for it
    # to be missing, so asking would be a finding no remedy answers.
    write(repo / "docs/features/groom/runbooks/deploy.md",
          "---\ntype: runbook\nslug: deploy\ntitle: Deploy\n---\n# Deploy\n\n"
          "## Steps\n\n### Push\n- step: push the image\n"
          "- persistence: the tag is recorded in the registry\n")
    assert "undeclared-obligation" not in all_codes(_run(repo))


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


# ---------------------------------------------------------------------------
# convergence contract (§7.1): scaffold + fmt clears the errors
# ---------------------------------------------------------------------------
def test_scaffold_then_fmt_converges(repo: Path):
    # a bad-cased heading with a complete interaction underneath
    write(repo / "docs/features/groom/gui/screens/s.md",
          "---\ntype: screen\nslug: s\ntitle: S\n---\n# S\n\n"
          "## interactions\n\n### click\n- on: [x](#s)\n- trigger: click\n- does:\n  - state: x\n")
    assert "bad-heading-type" in codes(_run(repo))
    fmt.run_fmt(load(repo), [])          # fmt canonicalizes the heading casing
    assert "bad-heading-type" not in codes(_run(repo))


def test_missing_section_fixed_by_scaffold(repo: Path):
    scaffold.scaffold(load(repo), "cli", "wh", service="workhorse")
    # scaffolded cli already includes its required `## Commands`
    report = _run(repo)
    assert "missing-required-section" not in codes(report)


def test_code_and_tests_not_grounded_at_author_time(repo: Path):
    # `code:`/`tests:` are code refs, grounded at a later QA gate — never dangling-link here.
    write(repo / "docs/features/groom/gui/screens/s.md",
          "---\ntype: screen\nslug: s\ntitle: S\n---\n# S\n\n"
          "## Interactions\n\n### click\n- on: [x](#s)\n- trigger: click\n- does:\n  - state: x\n"
          "- code: `groom/groom/nope.py::ghost`\n- tests: `tests/test_nope.py::ghost`\n")
    report = _run(repo)
    assert "dangling-link" not in codes(report)
    assert "unresolved-relation" not in codes(report)
    assert "unparsed-check" not in codes(report)
