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


def test_code_and_verify_not_grounded_at_author_time(repo: Path):
    # `code:`/`verify:` are code refs, grounded at a later QA gate — never dangling-link here.
    write(repo / "docs/features/groom/gui/screens/s.md",
          "---\ntype: screen\nslug: s\ntitle: S\n---\n# S\n\n"
          "## Interactions\n\n### click\n- on: [x](#s)\n- trigger: click\n- does:\n  - state: x\n"
          "- code: `groom/groom/nope.py::ghost`\n- verify: `tests/test_nope.py::ghost`\n")
    report = _run(repo)
    assert "dangling-link" not in codes(report)
    assert "unresolved-relation" not in codes(report)
