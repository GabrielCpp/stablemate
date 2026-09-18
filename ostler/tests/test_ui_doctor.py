"""`ostler doctor` as a mandatory UI-profile linter (docs/okf-ui-support §7).

Every rule is an *error* with a deterministic remedy (fmt / scaffold), and every finding carries a
file+line location. The convergence contract: scaffolding then fmt'ing a node clears its findings.
"""

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


def _interaction_with_verifies(repo: Path, verifies: list[str]) -> None:
    lines = "\n".join(f"- verify: {v}" for v in verifies)
    write(repo / "docs/features/groom/gui/screens/s.md",
          "---\ntype: screen\nslug: s\ntitle: S\n---\n# S\n\n"
          "## Components\n\n### btn\n- selector: #btn\n- role: button\n- name: Go\n\n"
          "## Interactions\n\n### act\n- on: [btn](#btn)\n- trigger: click\n- role: button\n"
          "- name: Go\n- keyboard: Enter\n- does:\n  - state: go\n" + lines + "\n")


def test_unspelled_alternation_same_check_different_value(repo: Path):
    # same check, same `path=`, two different `code=` — the mechanical split signal.
    _interaction_with_verifies(repo, [
        'http_status(201, path="/api/widgets")',
        'http_status(400, path="/api/widgets")',
    ])
    report = _run(repo)
    assert "unspelled-alternation" in all_codes(report)
    finding = next(f for f in report.findings if f.code == "unspelled-alternation")
    assert finding.severity == "warn"


def test_unspelled_alternation_needs_a_shared_identifying_argument(repo: Path):
    # different `path=` too — two claims about two different requests, not one contradicting
    # itself.
    _interaction_with_verifies(repo, [
        'http_status(201, path="/api/widgets")',
        'http_status(400, path="/api/reports")',
    ])
    assert "unspelled-alternation" not in all_codes(_run(repo))


def test_unspelled_alternation_ignores_a_single_argument_check(repo: Path):
    # `removed(subject=…)` has one argument, which is both the subject and the only value —
    # two different subjects are two different claims, not a self-contradiction.
    _interaction_with_verifies(repo, [
        'removed(subject="the first widget")',
        'removed(subject="the second widget")',
    ])
    assert "unspelled-alternation" not in all_codes(_run(repo))


def test_two_counts_of_two_collections_are_not_one_count_claimed_twice(repo: Path):
    # `count` has two arguments, so the arity test lets this through, and the two calls differ
    # on exactly one — which under a pure difference count is indistinguishable from the
    # `http_status` case above. It is the opposite claim: `subject` names *which* collection is
    # counted, so two values are two collections. Reporting it tells the author to split a node
    # that was right, or to merge two counts into one, and either way a distinction the book
    # made correctly is gone.
    _interaction_with_verifies(repo, [
        'count(subject="open widgets", equals=1)',
        'count(subject="archived widgets", equals=1)',
    ])
    assert "unspelled-alternation" not in all_codes(_run(repo))


def test_the_role_is_read_from_the_signature_not_from_whether_it_is_required(repo: Path):
    # The negative control for the fix. `http_status` is the one check where the required
    # argument is the expectation and the optional one is the identifier, so any rule deriving
    # roles from `required` silences precisely the case the finding exists for. Two `code=`
    # values on one `path=` must still be a conflict.
    _interaction_with_verifies(repo, [
        'http_status(201, path="/api/widgets")',
        'http_status(409, path="/api/widgets")',
    ])
    assert "unspelled-alternation" in all_codes(_run(repo))


def test_a_differing_identifier_is_not_a_conflict_even_where_a_flag_agrees(repo: Path):
    # `json_path.path` is both an identifier and the only identifier carrying `path=True`,
    # while `http_status.path` is an identifier carrying `path=False`. The flags are about
    # document paths, not roles, so the role had to be stated on its own — this is the case
    # that would pass under either flag being reused as a shortcut, and fail under the other.
    _interaction_with_verifies(repo, [
        'json_path(path="$.state", equals="open")',
        'json_path(path="$.owner", equals="open")',
    ])
    assert "unspelled-alternation" not in all_codes(_run(repo))


def test_unspelled_alternation_not_tripped_by_an_extends_split(repo: Path):
    # the repair: split the contradiction into a base case and an arm that `extends:` it —
    # each interaction's own `verify:` bullets no longer contradict each other.
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
    # An arrangement exists to make *this* arm's `when:` true, so it is not inherited — and an
    # arm whose base arranges and which arranges nothing has no reachable precondition. The
    # compiler already withholds it, but only once a plan is compiled; this says it off the
    # book alone, while the author is still writing the arm.
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


def test_a_scaffolded_empty_arrange_bullet_does_not_count_as_an_arrangement(repo: Path):
    # Every authorable key is scaffolded onto a node as an empty bullet, so reading key
    # *presence* would make this book — which arranges nothing — indistinguishable from one
    # that does. The predicate reads values.
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
    # Same shape as `raises:` on a method: a display-only component's `keyboard: none,
    # because …` states there is no operable role, which `role:`/`verify:` already cover —
    # no keystroke exists for a check to bind to.
    _screen_with(
        repo,
        "- role: generic\n- name: none\n"
        "- states: a policy still open reads `Draft`\n"
        '- verify: visible(locator="#body", text="Draft")\n'
        '- verify: visible(locator="#body", text="VIN")\n'
        "- keyboard: none, because it is read rather than operated.\n")
    assert "uneven-claim-coverage" not in all_codes(_run(repo))


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
    assert finding.ref == f"{finding.path}#click#does:1"


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


def test_a_semicolon_finding_names_the_form_a_reason_takes(repo: Path):
    # The clause after the semicolon is often the *why* of the first, not a second observation,
    # and there is no bullet to split a reason into. Told only to split, repair agents kept the
    # reason and its semicolon and reported the bullet documented, lap after lap; the one form
    # this rule admits for it — an aside — has to be in the finding that is read.
    write(repo / "docs/features/groom/gui/screens/s.md",
          _interaction("does not cast the value; that decision belongs to the caller"))
    finding = next(f for f in _run(repo).findings if f.code == "compound-normative-bullet")
    assert "parentheses" in finding.message


def test_a_semicolon_inside_an_aside_is_not_compound(repo: Path):
    # The aside is not what is being proved, so a semicolon joining two of *its* clauses joins
    # nothing the planner owes a scenario for — and there is no split of this bullet that clears
    # the finding short of deleting the sentence that explains the scope.
    write(repo / "docs/features/groom/gui/screens/s.md",
          _interaction("the fallback menu opens (this journey exercises the fallback; "
                       "the native hand-off is out of scope)"))
    assert "compound-normative-bullet" not in all_codes(_run(repo))


def test_a_semicolon_inside_a_code_span_is_not_compound(repo: Path):
    # A literal written as code says one thing however it is spelled: the `;` in a MIME type
    # parameter list is notation, not a clause boundary, and no split of the bullet clears it.
    write(repo / "docs/features/groom/gui/screens/s.md",
          _interaction("returns `\"application/json; charset=utf-8\"` regardless of the "
                       "ext parameter"))
    assert "compound-normative-bullet" not in all_codes(_run(repo))


def test_a_semicolon_outside_an_aside_is_still_compound(repo: Path):
    # The near-miss: a bullet may carry an aside and still join two obligations around it.
    write(repo / "docs/features/groom/gui/screens/s.md",
          _interaction("the row saves (the audit trail is written first); "
                       "the previous value is shown beside it"))
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


def test_a_bare_three_digit_number_is_not_a_status_code(repo: Path):
    # A status is written in backticks in this profile, and the reader now says so: it reads
    # the bullet's code spans rather than scanning its prose for digits. Unnarrowed, this
    # bullet was reported as naming two statuses — a finding whose remedy is to split a claim
    # that was never compound, which is the kind nobody can clear and everybody waives.
    write(repo / "docs/features/groom/gui/screens/s.md",
          _interaction("the label renders at font-weight 500 (vs body's 400)"))
    assert "compound-normative-bullet" not in all_codes(_run(repo))


def test_capitalised_prose_words_are_not_two_failures(repo: Path):
    # `PaymentDenied` is a component and `ConflictResolution` is a value; neither is written
    # as code, because neither is a symbol. Over raw prose both matched the failure pattern
    # and the bullet was told to split into two obligations it does not state.
    write(repo / "docs/features/groom/gui/screens/s.md",
          _interaction("the PaymentDenied banner shows the ConflictResolution the merge chose"))
    assert "compound-normative-bullet" not in all_codes(_run(repo))


def test_a_bare_three_digit_number_under_a_non_normative_key_mints_nothing(repo: Path):
    # The same narrowing, at `unminted-claim`'s reader: a font weight is not a claim hiding
    # under the wrong key.
    write(repo / "docs/features/groom/concepts/lease.md",
          "---\ntype: concept\nslug: lease\ntitle: Lease\n---\n# Lease\n\n"
          "- meaning: a lock over one path\n"
          "- styling: the deadline renders at font-weight 500 (vs body's 400)\n")
    assert "unminted-claim" not in all_codes(_run(repo))


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


def _screen_with_locator(locator: str, *, declare_table: bool = True) -> str:
    table = ("### widget-table\n- selector: table[aria-label=\"Widgets\"]\n- role: table\n"
             "- name: Widgets\n\n" if declare_table else "")
    return ("---\ntype: screen\nslug: s\ntitle: S\n---\n# S\n\n"
            f"## Components\n\n{table}"
            "## Interactions\n\n### click\n- on: [S](#s)\n- trigger: click\n"
            "- does: the table appears\n"
            f"- verify: visible(locator=\"{locator}\")\n")


def test_a_raw_selector_is_not_a_locator(repo: Path):
    # It type-checks, it runs, and it goes green against an element the book has never heard
    # of — so renaming that element breaks the run and leaves the book undisturbed.
    write(repo / "docs/features/groom/gui/screens/s.md",
          _screen_with_locator("table[aria-label='Widgets']"))
    finding = next(f for f in _run(repo).findings if f.code == "undeclared-check-locator")
    assert finding.severity == "error"
    assert "not a reference into the book" in finding.message
    assert finding.ref == "docs/features/groom/gui/screens/s.md#click#verify:1"


def test_a_locator_naming_no_declared_component_is_reported(repo: Path):
    # Anchor-shaped and still unresolvable: the distinction the rule draws is whether the book
    # declares the thing, not whether the string starts with a `#`.
    write(repo / "docs/features/groom/gui/screens/s.md",
          _screen_with_locator("#widget-table", declare_table=False))
    finding = next(f for f in _run(repo).findings if f.code == "undeclared-check-locator")
    assert "names no component this book declares" in finding.message


def test_a_locator_naming_a_declared_component_grounds(repo: Path):
    write(repo / "docs/features/groom/gui/screens/s.md", _screen_with_locator("#widget-table"))
    assert "undeclared-check-locator" not in all_codes(_run(repo))


def test_a_locator_may_name_a_component_in_another_document(repo: Path):
    # The destination of a navigation lives on the screen it lands on, so the common correct
    # locator is cross-document and the rule has to resolve one.
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
    # `fixture:` was the only arrangement key for a long time, and its habit is the likeliest
    # mistake here — the value is not malformed, only the key above it is wrong.
    write(repo / "docs/features/groom/gui/screens/s.md",
          _screen_with_arrangement("widgets-on-hand"))
    finding = next(f for f in _run(repo).findings if f.code == "unparsed-act")
    assert finding.severity == "error"
    assert "belongs on `fixture:`" in finding.message
    assert finding.suggestion == "- fixture: widgets-on-hand"


def test_an_arrange_value_naming_a_check_gets_the_act_vocabulary(repo: Path):
    # The two keys share a call grammar and not a vocabulary: `visible` parses and still names
    # no act, and handing back the check list would send the author to write the wrong bullet.
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
    """The narrowing that made the key possible: the two fixture checkers iterate every
    arrangement key, and an act read as a fixture name is a finding against a correct book."""
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
    # Nothing in the grammar tells a check that observes both children from one that refutes
    # all but one, and the two readings disagree about whether a green run is evidence.
    write(repo / "docs/features/groom/gui/screens/s.md", _branching_interaction())
    finding = next(f for f in _run(repo).findings if f.code == "unstated-claim-combiner")
    assert finding.severity == "error"
    assert finding.ref == "docs/features/groom/gui/screens/s.md#click#does:1"
    assert "branches" in (finding.suggestion or "")


def test_a_nested_claim_list_nobody_observes_needs_no_combiner(repo: Path):
    # The word is required only where it changes an outcome, so a book is not asked to
    # annotate every list it happens to write.
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
    # Over alternatives the check is a refutation of every branch but one, and filing it as a
    # proof is the one way a green run can be evidence for a claim the run disproved.
    write(repo / "docs/features/groom/gui/screens/s.md", _branching_interaction("branches"))
    assert _claim_bindings(repo) == {}
    branches = [f for f in _run(repo).findings if f.code == "unobserved-branch"]
    assert [f.severity for f in branches] == ["warn", "warn"]
    assert "Split the branches into sibling bullets" in branches[0].message


def test_a_stated_combiner_is_not_itself_a_claim(repo: Path):
    # It is written where the parent's own value would go, so the list has to mint exactly the
    # obligations it minted while it said nothing.
    write(repo / "docs/features/groom/gui/screens/s.md", _branching_interaction("all"))
    node = load(repo).ui_nodes_of_type("interaction")[0]
    assert [v for k, v, _ in node.bullet_order if k == "does"] == [
        "success: the table appears", "failure: the page stays put"]
    assert node.combiners == {2: "all"}


def test_a_combiner_word_on_a_childless_bullet_stays_prose(repo: Path):
    # A list of one thing has nothing to combine, so `- does: all` there is somebody's prose.
    write(repo / "docs/features/groom/gui/screens/s.md",
          ("---\ntype: screen\nslug: s\ntitle: S\n---\n# S\n\n"
           "## Interactions\n\n### click\n- on: [S](#s)\n- trigger: click\n"
           "- does: all\n"))
    node = load(repo).ui_nodes_of_type("interaction")[0]
    assert node.combiners == {}
    assert [v for k, v, _ in node.bullet_order if k == "does"] == ["all"]


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


def test_a_claim_with_two_checks_and_a_bare_sibling_is_reported(repo: Path):
    # `attributed_checks` binds each check to the nearest normative bullet above it — a check
    # written against the wrong claim still binds, silently, to whichever one sits above it.
    # Two checks piled on `returns` while `raises` carries none is what that looks like from
    # outside: not `undeclared-obligation`'s node-wide zero, but an imbalance between siblings.
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
    # A claim with fewer checks than its neighbor is making a smaller promise, not a wrong one
    # — the bar is the conjunction (some claim over-covered *and* another uncovered), not "some
    # claim is uncovered" on its own.
    write(repo / "docs/features/groom/concepts/publisher.md",
          "---\ntype: concept\nslug: publisher\ntitle: Publisher\n---\n# Publisher\n\n"
          "## Methods\n\n### Publish\n"
          "- returns: the published revision\n"
          '- verify: http_status(200, title="OK")\n'
          "- raises: `ManifestConflict` when the revision moved\n")
    assert "uneven-claim-coverage" not in all_codes(_run(repo))


def test_a_self_declared_empty_raises_is_not_the_light_sibling(repo: Path):
    # `raises: nothing at all, because …` is a complete claim with no behavior left for a
    # check to bind to — no exception to provoke. Left counted, this node reads as broken
    # (the two checks on `returns` prove the actual behavior) when it is complete.
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
    # `none` alone, with no `because`, is a blank left blank — still an open claim a check
    # could bind to once written, not the same shape as a value that states the reason.
    write(repo / "docs/features/groom/concepts/publisher.md",
          "---\ntype: concept\nslug: publisher\ntitle: Publisher\n---\n# Publisher\n\n"
          "## Methods\n\n### Publish\n"
          "- returns: the published revision\n"
          '- verify: http_status(200, title="OK")\n'
          '- verify: http_status(201, title="Created")\n'
          "- raises: none\n")
    finding = next(f for f in _run(repo).findings if f.code == "uneven-claim-coverage")
    assert "raises:1" in finding.message


def test_a_check_that_cannot_go_red_is_reported(repo: Path):
    # Declared, parsed, bound — and green against the defect too. Presence without a value is
    # `json_path`'s own `excludes:` sentence, so the rule is that sentence made computable.
    write(repo / "docs/features/groom/concepts/publisher.md",
          _method('json_path(path="$.revision", absent=false)'))
    finding = next(f for f in _run(repo).findings if f.code == "weak-check")
    # An `error`, unlike the prose heuristics beside it: the remedy is mechanical — the check
    # names the value the claim turns on, or it does not.
    assert finding.severity == "error"
    assert "passes on the default" in finding.message
    # The message and the ref are one string: naming the claim one way and addressing it
    # another is how a repair turn ends up reading a sibling bullet.
    assert "#publish#returns:1" in finding.message
    assert finding.ref == f"{finding.path}#publish#returns:1"


def test_a_success_status_naming_neither_route_nor_title_is_weak(repo: Path):
    write(repo / "docs/features/groom/concepts/publisher.md", _method("http_status(200)"))
    assert "weak-check" in all_codes(_run(repo))


def test_one_discriminating_check_answers_the_claim_it_was_written_under(repo: Path):
    # All-or-nothing within one claim: an author who observes `returns:` two ways has made
    # the judgment, and only the weakest of them is not the finding.
    write(repo / "docs/features/groom/concepts/publisher.md",
          "---\ntype: concept\nslug: publisher\ntitle: Publisher\n---\n# Publisher\n\n"
          "## Methods\n\n### Publish\n- returns: the published revision\n"
          '- verify: json_path(path="$.revision", absent=false)\n'
          '- verify: json_path(path="$.state", equals="published")\n')
    assert "weak-check" not in all_codes(_run(repo))


def test_a_pattern_that_admits_any_value_is_insensitive_not_weak(repo: Path):
    # `matches=".*"` names a real field and is not one of `weak-check`'s two static
    # shapes (a bare 2xx status, a presence-only path) — it only fails experimentally,
    # by surviving the mutation it should have caught.
    write(repo / "docs/features/groom/concepts/publisher.md",
          _method('json_path(path="$.state", matches=".*")'))
    found = all_codes(_run(repo))
    assert "weak-check" not in found
    finding = next(f for f in _run(repo).findings if f.code == "insensitive-check")
    assert finding.severity == "error"
    assert "#publish:returns:1" in finding.ref


def test_a_pattern_no_witness_can_be_invented_for_has_no_result(repo: Path):
    # `insensitive-check` is a result: a perturbation ran and the check survived it. Here
    # nothing ran — the synthesizer cannot invent a member of a closed alternation, so the
    # experiment was never performed, and "not measured" is not "measured and failed".
    # The finding falls on the *more* discriminating pattern, which is why it is a warn
    # about the harness and not an error about the book: the one edit that would silence
    # it is the edit that would make `insensitive-check` genuinely true.
    write(repo / "docs/features/groom/concepts/publisher.md",
          _method('json_path(path="$.lang", matches="^(fr|en)$")'))
    found = all_codes(_run(repo))
    assert "insensitive-check" not in found
    finding = next(f for f in _run(repo).findings if f.code == "unwitnessed-check")
    assert finding.severity == "warn"
    assert "#publish:returns:1" in finding.ref
    # The harness's own note travels with the finding: the reader needs to know which call
    # could not be witnessed and why, or the only available reading is "the check is bad".
    assert "no witness" in finding.message or "does not satisfy" in finding.message
    assert finding.suggestion is not None and "leave the check as it is" in finding.suggestion


def test_a_creation_verified_only_afterwards_is_reported(repo: Path):
    # The pass this exists to withhold: `201` and a present id say the same thing whether the
    # revision was created or was already there.
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
    # A bare stem is half the time a noun — "the issue was filed", "the register" — so only
    # the inflections a bullet uses to say what the node does are matched.
    write(repo / "docs/features/groom/concepts/publisher.md",
          "---\ntype: concept\nslug: publisher\ntitle: Publisher\n---\n# Publisher\n\n"
          "## Methods\n\n### Publish\n"
          "- returns: the issue the caller filed, and the register it was recorded in\n"
          '- verify: http_status(200, path="/revisions", title="OK")\n')
    assert "unstated-precondition" not in all_codes(_run(repo))


def test_a_lifecycle_claim_nothing_observes_is_not_this_rule_s_finding(repo: Path):
    """The shape no edit could clear, and the bulk of the 183 findings this rule used to raise.

    `returns:` states a creation and declares nothing; the node's one check answers a
    *different* claim. Node-wide, the rule read every verb against every check and reported the
    unobserved bullet against the observed one's checks — and there is no after-read on it to
    turn into a before-and-after, so the only way out was a waiver. The unobserved claim is
    `undeclared-obligation`'s business at the node level and `qa validate`'s per bullet.
    """
    write(repo / "docs/features/groom/concepts/publisher.md",
          "---\ntype: concept\nslug: publisher\ntitle: Publisher\n---\n# Publisher\n\n"
          "## Methods\n\n### Publish\n"
          "- returns: the revision it creates under the caller's name\n"
          "- does: the manifest is rewritten in place\n"
          '- verify: http_status(200, path="/revisions", title="OK")\n')
    assert "unstated-precondition" not in all_codes(_run(repo))


def test_a_sibling_claim_declaring_the_change_does_not_answer_this_one(repo: Path):
    """One `created(...)` on the node used to silence every lifecycle claim beside it.

    Attribution is written down (`registry.attributed_checks`), so the before-read credited to
    `does:` is not also credited to `returns:` — which observes the creation it states with a
    status code and nothing else.
    """
    write(repo / "docs/features/groom/concepts/publisher.md",
          "---\ntype: concept\nslug: publisher\ntitle: Publisher\n---\n# Publisher\n\n"
          "## Methods\n\n### Publish\n"
          "- returns: the revision it creates under the caller's name\n"
          '- verify: http_status(201, path="/revisions")\n'
          "- does: the manifest row is archived\n"
          '- verify: removed(subject="the manifest row")\n')
    finding = next(f for f in _run(repo).findings if f.code == "unstated-precondition")
    assert "creates" in finding.message
    # `:1` because the ref is the *claim*, not the key: a node states `returns:`/`does:` more
    # than once, and a ref naming only the key points a repair turn at every one of them.
    assert finding.ref == f"{finding.path}#publish#returns:1"


def test_a_verb_its_own_sentence_negates_states_no_lifecycle_change(repo: Path):
    """`created(subject=…)` asserts the very thing the claim says does not happen.

    The remedy the finding prints cannot be written for a claim of non-occurrence, and the
    `absent(...)` the author already wrote *is* the complete observation — so the finding had
    no edit that cleared it, which is the one thing this file's own bar forbids.
    """
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
    """`restores or removes` is the prior-state condition, spelled as the alternation itself.

    The first version of the exemption scanned only the tokens *after* the lifecycle verb and
    demanded a separate cue word. Both halves miss this shape: the alternative mutation and
    the marker sit to the *left* of `removes`, and the condition is never named — the branch
    is the condition. A context manager that puts back the prior value, or unsets the name
    when there was no prior value, has no single lifecycle direction to observe, so
    `removed(subject=...)` asserts a branch that does not always run.
    """
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
    """The near-miss that keeps the alternation test tight rather than sentence-wide.

    `or` appears here, and so does a second verb — but the two are not arms of one choice,
    and the creation is unconditional. Accepting any marker anywhere beside any mutation
    anywhere would drop this claim, which is exactly the finding's job.
    """
    write(repo / "docs/features/groom/concepts/publisher.md",
          "---\ntype: concept\nslug: publisher\ntitle: Publisher\n---\n# Publisher\n\n"
          "## Methods\n\n### Publish\n"
          "- does: creates the revision, then updates the manifest row it points at or the\n"
          "  index that lists it\n"
          '- verify: http_status(201, path="/revisions")\n')
    finding = next(f for f in _run(repo).findings if f.code == "unstated-precondition")
    assert "creates" in finding.message


def test_a_negator_elsewhere_in_the_sentence_does_not_clear_a_real_creation(repo: Path):
    """The near-miss that makes the scoping load-bearing, not a detail of the implementation.

    "any negator anywhere in the sentence" reads this claim as non-occurrence and drops a
    genuine creation. In a real book 23 claims carried a negator somewhere and 10 carried one
    governing the verb — so the sentence-wide test would have been wrong on 13 of them.
    """
    write(repo / "docs/features/groom/concepts/publisher.md",
          "---\ntype: concept\nslug: publisher\ntitle: Publisher\n---\n# Publisher\n\n"
          "## Methods\n\n### Publish\n"
          "- does: creates a new manifest and copies every existing row into it, without\n"
          "  mutating the manifest the caller passed in\n"
          '- verify: http_status(201, path="/revisions")\n')
    finding = next(f for f in _run(repo).findings if f.code == "unstated-precondition")
    assert "creates" in finding.message


def test_a_deletion_the_sentence_only_sequences_still_states_a_lifecycle_change(repo: Path):
    # "after deleting" is when the response is emitted, not a denial that it was deleted.
    write(repo / "docs/features/groom/concepts/publisher.md",
          "---\ntype: concept\nslug: publisher\ntitle: Publisher\n---\n# Publisher\n\n"
          "## Methods\n\n### Publish\n"
          "- returns: an empty `204 No Content` after deleting the revision\n"
          '- verify: http_status(204, path="/revisions")\n')
    finding = next(f for f in _run(repo).findings if f.code == "unstated-precondition")
    assert "deleting" in finding.message


def test_emitting_a_request_is_not_a_change_of_existence(repo: Path):
    """`issues`/`issuing` left `LIFECYCLE_VERBS` on the constant's own stated criterion.

    Their object is an *event*, and an event is not a subject a harness can read either side
    of — there is no `created(subject=…)` to write. Emission already has its question,
    `emits:` and `emitted(...)`.
    """
    write(repo / "docs/features/groom/concepts/publisher.md",
          "---\ntype: concept\nslug: publisher\ntitle: Publisher\n---\n# Publisher\n\n"
          "## Methods\n\n### Publish\n"
          "- does: issues one `GET /manifest` against the api, never two\n"
          '- verify: emitted(event="GET /manifest", count=1)\n')
    assert "unstated-precondition" not in all_codes(_run(repo))


def test_a_key_that_describes_rather_than_acts_is_not_asked_for_a_before_read(repo: Path):
    # `semantics:` says what a *value* means. There is no action here to observe either side
    # of, so the finding named a remedy the author had nowhere to put.
    write(repo / "docs/features/groom/concepts/publisher.md",
          "---\ntype: concept\nslug: publisher\ntitle: Publisher\n---\n# Publisher\n\n"
          "## Fields\n\n### Row Count\n"
          "- semantics: an empty value is read as zero; any other value the generator\n"
          "  inserts verbatim into the manifest\n"
          '- verify: json_path(path="$.rowCount", equals="0")\n')
    assert "unstated-precondition" not in all_codes(_run(repo))


def test_a_node_minting_no_obligation_is_not_asked_to_declare(repo: Path):
    # Nothing to observe: an interaction recorded only by its trigger owes no check, and a rule
    # that asked anyway would be noise on the descriptive half of the book.
    write(repo / "docs/features/groom/gui/screens/s.md",
          "---\ntype: screen\nslug: s\ntitle: S\n---\n# S\n\n"
          "## Interactions\n\n### click\n- on: [S](#s)\n- trigger: click\n")
    assert "undeclared-obligation" not in all_codes(_run(repo))


def test_a_field_inherits_its_observation_from_the_record_that_carries_it(repo: Path):
    # A typed attribute's `default:`/`required:` are proven by the check on whatever reads
    # or writes the record, so the field itself owes no declaration — asking would cost a
    # repair per attribute for a check nobody binds. Declaring stays allowed, and a
    # declaration that does not parse is still reported.
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
    # A `step:` under a runbook mints obligations too, but its `verify:` keeps its own older
    # meaning — how to tell the step ran — and is not a check. There is no declaration for it
    # to be missing, so asking would be a finding no remedy answers.
    write(repo / "docs/features/groom/runbooks/deploy.md",
          "---\ntype: runbook\nslug: deploy\ntitle: Deploy\n---\n# Deploy\n\n"
          "## Steps\n\n### Push\n- step: push the image\n"
          "- persistence: the tag is recorded in the registry\n")
    assert "undeclared-obligation" not in all_codes(_run(repo))


def test_a_claim_under_a_non_normative_key_is_reported(repo: Path):
    """A concept that mints nothing, stating a status code under its own `errors:` key: no
    obligation will ever carry it, so no plan is asked to prove it. A warn — the remedy is
    authoring judgment — and reported once per node, at the first such bullet."""
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
    # The descriptive half of the book: an interaction recorded by its trigger states nothing.
    write(repo / "docs/features/groom/gui/screens/s.md",
          "---\ntype: screen\nslug: s\ntitle: S\n---\n# S\n\n"
          "## Interactions\n\n### click\n- on: [S](#s)\n- trigger: click\n")
    assert "unminted-claim" not in all_codes(_run(repo))


def test_a_node_that_mints_is_not_asked_about_its_prose(repo: Path):
    # Once a node mints one obligation it is in QA's sight; its other bullets are context.
    write(repo / "docs/features/groom/concepts/lease.md",
          "---\ntype: concept\nslug: lease\ntitle: Lease\n---\n# Lease\n\n"
          "- persistence: the lease row is written once\n"
          "- errors: `409` when the lease is held by another worker\n")
    assert "unminted-claim" not in all_codes(_run(repo))


def test_an_untyped_section_with_a_status_bullet_is_reported(repo: Path):
    write(repo / "docs/features/groom/concepts/lease.md",
          "---\ntype: concept\nslug: lease\ntitle: Lease\n---\n# Lease\n\n"
          "## Notes\n\n### Renewal\n- outcome: `409` when the lease is held by another worker\n")
    hits = [f for f in _run(repo).findings if f.code == "unminted-claim"]
    assert [f.ref for f in hits] == ["docs/features/groom/concepts/lease.md#renewal#outcome"]


def test_an_undeclared_bullet_key_is_a_warning(repo: Path):
    """A `verify:` on a concept is read by nobody — `check_keys("concept")` is empty — while
    the author who wrote it believes the claim above is observed. A warn, not an error: where
    the observation belongs is the author's call."""
    write(repo / "docs/features/groom/concepts/diff.md",
          "---\ntype: concept\nslug: diff\ntitle: Diff\n---\n# Diff\n\n"
          "- code: `groom/diff.py::Diff`\n- verify: absent(subject=\"the row\")\n"
          "- meaning: the author's own word, which no type declares and nothing polices\n")
    report = _run(repo)
    hits = [f for f in report.findings if f.code == "unknown-bullet"]
    assert [f.ref for f in hits] == ["docs/features/groom/concepts/diff.md#verify"]
    assert hits[0].severity == "warn"
    assert "concept declares" in hits[0].message


def test_an_undeclared_bullet_on_an_untyped_section_is_not_asked(repo: Path):
    write(repo / "docs/features/groom/concepts/diff.md",
          "---\ntype: concept\nslug: diff\ntitle: Diff\n---\n# Diff\n\n"
          "## Notes\n\n- verify: a word in prose, not a check\n")
    assert "unknown-bullet" not in all_codes(_run(repo))


def test_a_status_bullet_on_an_invocation_is_declared_and_formatted(repo: Path):
    """The key was graded for as long as the mapper existed and declared only now: `fmt`
    orders it between the effect and its grounding, and the `verify:` under it stays with
    it (`registry.attributed_checks` binds a check to the nearest claim above)."""
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
    """`detail:` always resolved on any type — relations are global by key name — but only
    `command` and `endpoint` declared it, so on every other type it tripped `unknown-bullet`
    and `fmt` had no slot for it. Declaring it is what lets a book point a competing
    implementation at the concept that says when it is the right one."""
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
    """`code:` grounds on every type (`registry.owning_keys`'s docstring — a flow or a screen
    cites the code it is grounded in whether or not its profile lists the key, and always
    has), but only some types' own profiles listed it in `bullet_keys`. On the rest —
    `screen`, `flow`, `step`, `fixture`, `untyped` — `unknown-bullet` called that citation
    inert even though `_check_code_grounding` (which reads `node.meta.get('code')` directly,
    with no type gate) has always graded it. `declared_keys` folding `code` in unconditionally,
    the same way it already folds in the shared normative/advisory keys, is what stops
    `unknown-bullet` from flagging a bullet the linter itself checks."""
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
    """`rule:`/`prefers:`/`deprecates:` are the concept's judgment vocabulary, and none is
    normative — a selection rule is not live-provable, so minting an obligation from one
    would demand evidence no scenario can produce. `prefers:`/`deprecates:` are relations:
    a dangling side is `unresolved-relation`, never silence. `rule:` is plain prose, so on
    a type that never declared it the key stays the author's own word — inert, not policed
    by `unknown-bullet` the way a load-bearing key would be."""
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
    # The H1 is a heading GitHub anchors too, so a document whose H1 and section share a title
    # renders the section at `#slug-1`. Keep them distinct here: the subject is co-citation,
    # not anchor uniquifying, and `test_a_repeated_heading_gets_the_anchor_github_renders`
    # in `test_ui_graph.py` is where that behaviour is pinned.
    return (f"---\ntype: api\nslug: {slug}\ntitle: {slug}\n---\n# {slug} API\n\n"
            f"## Endpoints\n\n### {slug}\n- method: POST\n- path: /{slug}\n"
            f"- does:\n  - state: sends the notification\n- status: `201` on success\n"
            f"- verify: http_status(code=201, path=\"/{slug}\")\n"
            f"- code: `{symbol}`\n{extra}")


def _endpoint_section(slug: str, symbol: str, extra: str = "") -> str:
    """One `### slug` endpoint, for stacking two siblings under one `## Endpoints` file."""
    return (f"### {slug}\n- method: POST\n- path: /{slug}\n"
            f"- does:\n  - state: sends the notification\n- status: `201` on success\n"
            f"- verify: http_status(code=201, path=\"/{slug}\")\n"
            f"- code: `{symbol}`\n{extra}\n")


def test_competing_implementations_fires_on_unranked_same_type_co_citation(repo: Path):
    """Two endpoints ground themselves in one symbol with no shared `detail:` concept — each
    can be entirely true and a reader reaching either still cannot learn which to use."""
    write(repo / "docs/features/groom/http/api.md",
          "---\ntype: api\nslug: api\ntitle: API\n---\n# API\n\n## Endpoints\n\n"
          + _endpoint_section("v1", "internal/notify.go::Notify")
          + _endpoint_section("v2", "internal/notify.go::Notify"))
    hits = [f for f in _run(repo).findings if f.code == "competing-implementations"]
    assert len(hits) == 1 and hits[0].severity == "warn"
    assert "v1" in hits[0].message and "v2" in hits[0].message
    assert "internal/notify.go::Notify" in hits[0].message
    assert "detail:" in (hits[0].suggestion or "")


def test_competing_implementations_carries_every_competitor_as_data(repo: Path):
    """The membership is a field, not a sentence — `path` names one member and the remedy needs
    all of them, so a consumer that had to recover the group from the message would be matching
    prose written for a person. `ref` names the group (type *and* symbol), because one symbol
    competed over by two types is two competitions with two remedies.
    """
    write(repo / "docs/features/groom/http/api.md",
          "---\ntype: api\nslug: api\ntitle: API\n---\n# API\n\n## Endpoints\n\n"
          + _endpoint_section("v1", "internal/notify.go::Notify")
          + _endpoint_section("v2", "internal/notify.go::Notify"))
    hit = next(f for f in _run(repo).findings if f.code == "competing-implementations")
    assert hit.related == ["docs/features/groom/http/api.md#v1",
                           "docs/features/groom/http/api.md#v2"]
    # `path` is still one arbitrary member; `related` is what makes the other reachable.
    assert hit.path in {member.split("#")[0] for member in hit.related}
    assert hit.ref == "endpoint:internal/notify.go::Notify"


def test_competing_implementations_groups_across_different_stamped_digests(repo: Path):
    """Two citations of the identical symbol, stamped at different points in its history, are
    still one competition — a reader choosing between v1 and v2 does not care which commit
    each bullet's `@digest` was captured against, so grouping must key on the symbol alone."""
    write(repo / "docs/features/groom/http/api.md",
          "---\ntype: api\nslug: api\ntitle: API\n---\n# API\n\n## Endpoints\n\n"
          + _endpoint_section("v1", "internal/notify.go::Notify@aaaaaaaaaaaa")
          + _endpoint_section("v2", "internal/notify.go::Notify@bbbbbbbbbbbb"))
    hits = [f for f in _run(repo).findings if f.code == "competing-implementations"]
    assert len(hits) == 1 and hits[0].severity == "warn"
    assert "v1" in hits[0].message and "v2" in hits[0].message


def test_competing_implementations_ignores_cross_type_co_citation(repo: Path):
    """An endpoint and a concept citing one symbol is a well-written book — the concept
    explains the unit the endpoint serves. Only same-type groups compete."""
    write(repo / "docs/features/groom/http/v1.md",
          _endpoint_file("v1", "internal/notify.go::Notify"))
    write(repo / "docs/features/groom/concepts/notify.md",
          "---\ntype: concept\nslug: notify\ntitle: Notify\n---\n# Notify\n\n"
          "- code: `internal/notify.go::Notify`\n")
    assert "competing-implementations" not in all_codes(_run(repo))


def test_competing_implementations_silent_under_a_shared_detail_concept(repo: Path):
    """Both competitors pointing `detail:` at one concept IS the adjudicated state — the
    selection rule is reachable from either side, so there is nothing left to warn about."""
    write(repo / "docs/features/groom/concepts/notify.md",
          "---\ntype: concept\nslug: notify\ntitle: Notify\n---\n# Notify\n\n"
          "- rule: reach for v2 unless the call site needs a synchronous send receipt\n")
    detail = "- detail: [notify](../concepts/notify.md)\n"
    write(repo / "docs/features/groom/http/api.md",
          "---\ntype: api\nslug: api\ntitle: API\n---\n# API\n\n## Endpoints\n\n"
          + _endpoint_section("v1", "internal/notify.go::Notify", detail)
          + _endpoint_section("v2", "internal/notify.go::Notify", detail))
    assert "competing-implementations" not in all_codes(_run(repo))


def test_competing_implementations_silent_across_files_with_no_writable_remedy(repo: Path):
    """Two endpoints in different files that co-cite one symbol are not reported: `exclusive-
    with:` is a *sibling* relation and a DOM co-render assertion (component.md / interaction.md
    / concept.md) — members in different files are not siblings and genuinely do co-render, each
    on its own screen, so the finding would ask the author to write a false claim. The central
    remedy is no better: a shared `detail:` concept would state a selection rule where nothing
    actually selects. Same-type co-citation of one symbol across files is not evidence of
    rivalry to begin with — `code:` is many-to-one by construction (one file, many documenting
    nodes), which is exactly what `qa context` relies on to fan a diff out to every citing node.
    """
    write(repo / "docs/features/groom/http/v1.md",
          _endpoint_file("v1", "internal/notify.go::Notify"))
    write(repo / "docs/features/groom/http/v2.md",
          _endpoint_file("v2", "internal/notify.go::Notify"))
    assert "competing-implementations" not in all_codes(_run(repo))


def test_competing_implementations_fires_for_same_file_siblings_despite_narrowing(repo: Path):
    """The narrowing to same-file groups does not silence the check where a remedy is still
    writable: two endpoint sections declared as siblings in one file can name each other under
    `exclusive-with:` or share a `detail:` concept, so the finding still fires when neither is
    written."""
    write(repo / "docs/features/groom/http/api.md",
          "---\ntype: api\nslug: api\ntitle: API\n---\n# API\n\n## Endpoints\n\n"
          + _endpoint_section("v1", "internal/notify.go::Notify")
          + _endpoint_section("v2", "internal/notify.go::Notify"))
    assert "competing-implementations" in all_codes(_run(repo))


def _rival_component(slug: str, name: str, other: str, states: str) -> str:
    """One of two components citing a single renderer and ruling the other one out."""
    return (f"### {slug}\n- selector: `p.{slug}`\n- role: status\n- name: {name}\n"
            f"- exclusive-with: [{other}](#{other})\n"
            f"{states}"
            f"- verify: visible(locator=\"status:{name}\")\n"
            f"- code: `app/page.js::render`\n\n")


def test_competing_implementations_silent_for_declared_mutual_alternatives(repo: Path):
    """The selection rule written distributively. Two states of one screen are drawn by one
    renderer, so both cite it; each rules the other out under `exclusive-with:` and each says
    the condition it holds under. That answers "which do I use, and when?" exactly as a shared
    `detail:` concept does — and the concept the suggestion asks for would restate an exclusion
    the book already declared, in a second place, with nothing relating the two.
    """
    write(repo / "docs/features/groom/gui/screens/s.md",
          "---\ntype: screen\nslug: s\ntitle: S\n---\n# S\n\n## Components\n\n"
          + _rival_component("rows", "Rows", "empty",
                             "- states: shown — whenever the read returns at least one row\n")
          + _rival_component("empty", "Empty", "rows",
                             "- states: shown — whenever the read returns no rows at all\n"))
    assert "competing-implementations" not in all_codes(_run(repo))


def test_competing_implementations_fires_on_exclusivity_with_no_conditions(repo: Path):
    """`exclusive-with:` alone is not a selection rule. It says *not both*; it does not say
    *which*, so a reader landing on either one still cannot tell whether this is the case they
    are in. The finding is owed, and the two-part reading is what keeps the exemption from
    laundering a bare exclusion into an answer."""
    write(repo / "docs/features/groom/gui/screens/s.md",
          "---\ntype: screen\nslug: s\ntitle: S\n---\n# S\n\n## Components\n\n"
          + _rival_component("rows", "Rows", "empty", "- states:\n")
          + _rival_component("empty", "Empty", "rows", "- states:\n"))
    assert "competing-implementations" in all_codes(_run(repo))


def test_competing_implementations_silent_for_parts_of_one_declared_whole(repo: Path):
    """Two components of a server-rendered screen both cite the screen's one renderer
    because each is a region of its output — a shared `parent:` says they are parts of
    one whole, and nobody is choosing between the parts of a whole."""
    write(repo / "docs/features/groom/gui/screens/s.md",
          "---\ntype: screen\nslug: s\ntitle: S\n---\n# S\n\n"
          "## Components\n\n"
          "### grid\n- selector: `div.grid`\n- role: grid\n- name: Grid\n"
          "- verify: visible(locator=\"grid:Grid\")\n"
          "- parent: [S](#s)\n- code: `app/page.py::render`\n\n"
          "### summary\n- selector: `p.summary`\n- role: status\n- name: summary\n"
          "- verify: visible(locator=\"status\")\n"
          "- parent: [S](#s)\n- code: `app/page.py::render`\n")
    assert "competing-implementations" not in all_codes(_run(repo))


def _bar_component(slug: str, name: str, parent: str) -> str:
    return (f"### {slug}\n- selector: `div.{slug}`\n- role: group\n- name: {name}\n"
            f"- verify: visible(locator=\"group:{name}\")\n"
            f"- parent: [{parent}](#{parent})\n- code: `app/page.py::render`\n\n")


def test_competing_implementations_silent_for_a_whole_and_its_own_parts(repo: Path):
    """The other half of the shared-`parent:` reading: the whole is *in* the group. An app bar
    and its brand link and its action slot all cite the component that renders the bar, and the
    bar's own parent is the screen — outside the group — so the members' parents intersect to
    nothing and a whole plus its parts read as rivals. There is no selection rule to write
    between a thing and a region of it, so this fired where no edit clears it.
    """
    write(repo / "docs/features/groom/gui/screens/s.md",
          "---\ntype: screen\nslug: s\ntitle: S\n---\n# S\n\n## Components\n\n"
          + _bar_component("bar", "App bar", "s")
          + _bar_component("bar-brand", "Brand", "bar")
          + _bar_component("bar-actions", "Actions", "bar"))
    assert "competing-implementations" not in all_codes(_run(repo))


def test_competing_implementations_silent_down_a_two_level_part_chain(repo: Path):
    """A menu inside the bar and the channels inside the menu are still one decomposition —
    the escape walks up to the root rather than looking one hop."""
    write(repo / "docs/features/groom/gui/screens/s.md",
          "---\ntype: screen\nslug: s\ntitle: S\n---\n# S\n\n## Components\n\n"
          + _bar_component("bar", "App bar", "s")
          + _bar_component("bar-menu", "Share", "bar")
          + _bar_component("bar-menu-mail", "Email", "bar-menu")
          + _bar_component("bar-menu-sms", "SMS", "bar-menu"))
    assert "competing-implementations" not in all_codes(_run(repo))


def test_competing_implementations_fires_for_two_parts_of_no_declared_whole(repo: Path):
    """The near-miss that keeps the escape honest: same type, same symbol, and neither member
    is the other's parent. Two nodes hanging off the screen alone are the shared-`parent:`
    test's business (which silences them); two nodes hanging off nothing are a competition."""
    write(repo / "docs/features/groom/gui/screens/s.md",
          "---\ntype: screen\nslug: s\ntitle: S\n---\n# S\n\n## Components\n\n"
          "### grid\n- selector: `div.grid`\n- role: grid\n- name: Grid\n"
          "- verify: visible(locator=\"grid:Grid\")\n- code: `app/page.py::render`\n\n"
          "### summary\n- selector: `p.summary`\n- role: status\n- name: Summary\n"
          "- verify: visible(locator=\"status\")\n- code: `app/page.py::render`\n")
    assert "competing-implementations" in all_codes(_run(repo))


def test_competing_implementations_fires_for_two_wholes_each_with_parts(repo: Path):
    """Two roots is a competition between two wholes, however each is decomposed — the escape
    asks for one tree, not for any parent edge to exist."""
    write(repo / "docs/features/groom/gui/screens/s.md",
          "---\ntype: screen\nslug: s\ntitle: S\n---\n# S\n\n## Components\n\n"
          + _bar_component("bar", "App bar", "s")
          + _bar_component("bar-brand", "Brand", "bar")
          + _bar_component("rail", "App rail", "s")
          + _bar_component("rail-brand", "Rail brand", "rail"))
    assert "competing-implementations" in all_codes(_run(repo))


def test_competing_implementations_ignores_whole_file_citations(repo: Path):
    """A form's submit and its refusal both live in the form's component file, so both
    interactions cite it whole — cohabiting a file is not competing over a symbol. Only
    a shared `path::symbol` says two nodes claim the same unit."""
    write(repo / "docs/features/groom/gui/screens/s.md",
          "---\ntype: screen\nslug: s\ntitle: S\n---\n# S\n\n"
          "## Interactions\n\n"
          "### submit\n- when: the form is submitted with every field valid\n"
          "- then: the record is created\n"
          "- verify: visible(locator=\"status\")\n"
          "- code: app/web/src/Form.tsx\n\n"
          "### refuse\n- when: the form is submitted with a field the service refuses\n"
          "- then: the refusal is shown beside the field\n"
          "- verify: visible(locator=\"alert\")\n"
          "- code: app/web/src/Form.tsx\n")
    assert "competing-implementations" not in all_codes(_run(repo))


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
    """A `same-as:` value that resolves nowhere is `unresolved-relation`'s finding, raised by
    the document-wide link pass — this check only judges a claim once it lands on a real
    node, so the two never double-report the same broken bullet."""
    write(repo / "docs/features/groom/concepts/notify-a.md",
          "---\ntype: concept\nslug: notify-a\ntitle: Notify A\n---\n# Notify A\n\n"
          "- same-as: [gone](../concepts/gone.md)\n")
    codeset = all_codes(_run(repo))
    assert "unresolved-relation" in codeset
    assert "one-way-same-as" not in codeset


def test_one_way_same_as_is_checked_per_edge_not_per_family(repo: Path):
    """The addendum's chain: A<->B, B<->C, C<->D, all reciprocated pairwise. No member names
    every other member — B and C each name only their two immediate neighbors — and that is
    legal: `same-as:` is a multi-valued, per-edge claim, not a family-wide broadcast, so a
    reciprocated chain collapses to one family without raising anything here."""
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
    """A concept whose `deprecates:` resolves but that names no `prefers:` and no `rule:`
    reads as "delete this" — usually wrong. A dangling `deprecates:` is `unresolved-relation`'s
    finding alone: stacking this warn on the same broken link would have the repair chase two
    codes for one defect."""
    write(repo / "docs/features/groom/concepts/legacy.md",
          "---\ntype: concept\nslug: legacy\ntitle: Legacy\n---\n# Legacy\n\nOld path.\n")
    write(repo / "docs/features/groom/concepts/notify.md",
          "---\ntype: concept\nslug: notify\ntitle: Notify\n---\n# Notify\n\n"
          "- deprecates: [legacy](legacy.md)\n")
    hits = [f for f in _run(repo).findings if f.code == "deprecation-without-successor"]
    assert len(hits) == 1 and hits[0].severity == "warn"
    assert "prefers" in hits[0].message
    # naming the successor — either key — clears it
    write(repo / "docs/features/groom/concepts/notify.md",
          "---\ntype: concept\nslug: notify\ntitle: Notify\n---\n# Notify\n\n"
          "- rule: legacy remains only for the dunning sequence's synchronous receipt\n"
          "- deprecates: [legacy](legacy.md)\n")
    assert "deprecation-without-successor" not in all_codes(_run(repo))
    # dangling side: unresolved-relation fires, this warn stays out of the way
    write(repo / "docs/features/groom/concepts/notify.md",
          "---\ntype: concept\nslug: notify\ntitle: Notify\n---\n# Notify\n\n"
          "- deprecates: [gone](gone.md)\n")
    report = _run(repo)
    assert "unresolved-relation" in all_codes(report)
    assert "deprecation-without-successor" not in all_codes(report)


def test_ungrounded_unspecified(repo: Path):
    """An `unspecified:` bullet is resolved-by-design only on the strength of its citation.
    With a live one it is silent on any node type; uncited, or cited against a record that
    is not there, it is an error — the remedy is mechanical: cite what settled it, or
    delete the bullet."""
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


# ---------------------------------------------------------------------------
# one LinkResolver per doctor run (plan: increment 0 — "share one link resolver")
# ---------------------------------------------------------------------------
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

# The whole report this book produces, serialized. `org` is dropped because it is the
# tmp directory's name; everything else is fixed. Sharing one resolver changes what is
# *computed* and nothing about what is *reported*, so this equality is the complete
# correctness gate for that change — both findings below come from link resolution,
# which is exactly the machinery being shared.
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
    """Record every ``LinkResolver`` constructed and every anchor set computed.

    Patched onto the class itself rather than onto one module's name for it, so the
    count is of real constructions wherever they happen — which is the assertion.
    """
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
    """The graph build and the UI checks share one resolver.

    Each resolver memoizes a target file's heading anchors per instance, so a second
    instance re-reads and re-parses every link target — on a large book the single most
    expensive thing doctor does, paid twice for one run's worth of answers.
    """
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
    """The fan-out this rule used to have: one discriminating check anywhere on the node
    silenced it for every other bullet, so a claim observed only by a rubber stamp read as
    judged. Each claim now answers for the checks written under it."""
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
    """Two `does:` bullets, one already answered — the finding has to say which is the other.

    This is the shape that blocked two `okf-builder` runs for eight hours. The node states a
    lifecycle verb twice: the second claim declares `removed(...)` and is answered, the first
    is not. Reported as `node#does` with only the verb quoted, both claims match the sentence
    the finding prints, and a repair turn reads it against the *answered* bullet, concludes
    the book is already correct, and returns `documented` with the finding still standing.
    Three attempts and an adjudication later the run gives up on a defect whose remedy was
    one bullet away — so the claim's own index and its text are part of the finding, not
    something the reader has to guess from a shared key.
    """
    write(repo / "docs/features/groom/concepts/publisher.md",
          "---\ntype: concept\nslug: publisher\ntitle: Publisher\n---\n# Publisher\n\n"
          "## Methods\n\n### Publish\n"
          "- does: collapses the manifest and removes its surrounding whitespace\n"
          '- verify: json_path(path="$.manifest", equals="tidy")\n'
          "- does: removes the trailing separator from the normalized manifest\n"
          '- verify: removed(subject="the trailing separator")\n')
    finding = next(f for f in _run(repo).findings if f.code == "unstated-precondition")
    # The unanswered claim is the FIRST `does:`, and the answered one is the second. A reader
    # given only "`does:` states a lifecycle change ('removes')" cannot tell them apart.
    assert "does:1" in finding.message, finding.message
    assert "surrounding whitespace" in finding.message, finding.message
    assert "trailing separator" not in finding.message, finding.message


# ---------------------------------------------------------------------------
# one finding, one remedy, one ref — the per-bullet index (`refs.bullet_ref`)
#
# Every code below fires per *bullet*, on a key a node may state many times. Without the
# occurrence index the siblings arrive under one identical address, the okf-builder drain
# collapses them into one worklist row with one three-attempt budget, and the repair turn
# answers whichever sibling it happens to read. `scripts/check_finding_refs.py` enforces the
# property over the real corpus; these pin the spelling and the message per code, so a reader
# can tell which bullet a finding is about without opening the file.
# ---------------------------------------------------------------------------
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
    # The subjectless bullet is the SECOND; a ref naming only `#persistence` would send the
    # repair turn to the one that is already correct.
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
    # The value is quoted, so the message and the ref agree on which call is malformed.
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
    """Before this checker existed, nobody read this bullet. The packet builder dropped it and
    said in its docstring that `ostler doctor` would report it; doctor had one comment about
    captures and no finding at all, so the rule lived only in a docstring nothing enforced. The
    author's first news was an `unresolved-precondition` on a later bullet they wrote correctly.
    """
    write(repo / "docs/features/groom/http/api.md", _capture_endpoint("claim_id $.id"))
    finding = next(f for f in _run(repo).findings if f.code == "unparsed-capture")
    assert finding.severity == "error"
    assert "names no source" in finding.message
    assert finding.suggestion and " from " in finding.suggestion


def test_a_capture_name_a_reference_could_never_spell_is_refused(repo: Path):
    """The declaration mints the name and `$name` spells it, so a name `references` would not
    accept is a fact nothing in the book can ever refer to — a declaration that reads fine and
    resolves for nobody. Held to that grammar here rather than to a second copy of it."""
    write(repo / "docs/features/groom/http/api.md", _capture_endpoint("$claim_id from $.id"))
    finding = next(f for f in _run(repo).findings if f.code == "unparsed-capture")
    assert "`$` a reference spells" in finding.message


def test_a_well_formed_capture_bullet_grounds(repo: Path):
    write(repo / "docs/features/groom/http/api.md", _capture_endpoint("claim_id from $.id"))
    assert "unparsed-capture" not in all_codes(_run(repo))
