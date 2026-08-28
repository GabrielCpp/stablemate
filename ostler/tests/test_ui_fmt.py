"""`ostler fmt` — the canonicalizing formatter (docs/okf-ui-support §8)."""

from __future__ import annotations

from pathlib import Path

from ostler import fmt
from ostler.cli import main
from ostler.model import load

from conftest import write


def test_frontmatter_key_order():
    text = "---\ntitle: T\ntype: screen\nslug: s\n---\n# T\n"
    out = fmt.format_text(text)
    assert out.startswith("---\ntype: screen\nslug: s\ntitle: T\n---\n")


def test_bullet_reorder_and_spacing():
    text = (
        "---\ntype: screen\nslug: s\ntitle: T\n---\n# T\n\n"
        "## Interactions\n\n### click\n"
        "-  trigger:click\n"
        "- on: [x](#x)\n"
        "- does:\n  - state: mark row\n"
        "\nprose after.\n"
    )
    out = fmt.format_text(text)
    body = out.splitlines()
    # canonical order for interaction: on, trigger, when, does, ...
    i_on = body.index("- on: [x](#x)")
    i_trigger = body.index("- trigger: click")
    i_does = body.index("- does:")
    assert i_on < i_trigger < i_does
    assert "prose after." in body   # trailing prose preserved


def test_heading_casing_and_anchor_kebab():
    text = (
        "---\ntype: screen\nslug: s\ntitle: T\n---\n# T\n\n"
        "## components\n\n### Changes File Row\n- selector: `.x`\n"
    )
    out = fmt.format_text(text)
    assert "## Components" in out
    assert "### changes-file-row" in out


def test_one_line_does_normalized_to_nested():
    text = (
        "---\ntype: cli\nslug: c\ntitle: C\n---\n# C\n\n"
        "## Commands\n\n### run\n- usage: `c run`\n- does: run: execute the graph\n"
    )
    out = fmt.format_text(text)
    assert "- does:\n  - run: execute the graph" in out


def test_wikilink_rewritten():
    text = "---\ntype: concept\nslug: d\ntitle: D\n---\n# D\n\nSee [[diff]] and [[a.md|Alias]].\n"
    out = fmt.format_text(text)
    assert "[diff](diff)" in out
    assert "[Alias](a.md)" in out


def test_idempotent():
    text = (
        "---\ntitle: T\ntype: screen\nslug: s\n---\n# T\n\n"
        "## interactions\n\n### Click\n-  trigger:click\n- on: [x](#x)\n"
        "- does: state: toggle\n"
    )
    once = fmt.format_text(text)
    assert fmt.format_text(once) == once


def test_soft_wrapped_bullet_value_is_not_duplicated():
    """A bullet whose value wraps across source lines must survive untouched.

    `_emit_bullet` used to rebuild the first line from `bullet.text`, which holds the whole
    wrapped value newline and all, and then append `raw[1:]` on top — so each run emitted every
    continuation line twice and the next run doubled it again. It is not an exotic input: OKF
    docs wrap prose at a column, so it hit essentially every authored `when:`/`detail:` bullet,
    and an agent that ran `fmt` had to hand-repair the output and then skip the formatter.
    """
    text = (
        "---\ntype: screen\nslug: s\ntitle: T\n---\n# T\n\n"
        "## Interactions\n\n### click\n"
        "- on: [x](#x)\n- trigger: click\n"
        "- when: always — reachable while the process is up, including before any\n"
        "  downstream dependency is ready.\n"
    )
    out = fmt.format_text(text)
    assert out.count("downstream dependency is ready.") == 1, out
    assert "  downstream dependency is ready." in out, "the wrap's indent is the authored shape"
    assert out == text, out
    assert fmt.format_text(out) == out


def test_reorder_does_not_strand_blank_between_bullets():
    # A trailing blank line before the next heading must not migrate between reordered bullets.
    text = (
        "---\ntype: screen\nslug: s\ntitle: T\n---\n# T\n\n"
        "## Components\n\n### row\n- extends: [t](d.md#t)\n- selector: `.x`\n\n"
        "## Interactions\n"
    )
    out = fmt.format_text(text)
    body = out.splitlines()
    i_sel = body.index("- selector: `.x`")
    i_ext = body.index("- extends: [t](d.md#t)")
    assert i_sel + 1 == i_ext                       # adjacent, no blank between
    assert body[i_ext + 1] == ""                    # single blank before next heading
    assert body[i_ext + 2] == "## Interactions"


def test_unknown_bullet_preserved():
    text = (
        "---\ntype: screen\nslug: s\ntitle: T\n---\n# T\n\n"
        "## Components\n\n### row\n- selector: `.x`\n- customkey: keep me\n"
    )
    out = fmt.format_text(text)
    assert "- customkey: keep me" in out


def test_fmt_check_exit_code(repo: Path, capsys):
    write(repo / "docs/features/s.md",
          "---\ntitle: T\ntype: screen\nslug: s\n---\n# T\n")
    assert main(["-C", str(repo), "fmt", "--check"]) == 1
    # after formatting, --check is clean
    assert main(["-C", str(repo), "fmt"]) == 0
    assert main(["-C", str(repo), "fmt", "--check"]) == 0


def test_fmt_writes_canonical(repo: Path):
    p = repo / "docs/features/s.md"
    write(p, "---\ntitle: T\ntype: screen\nslug: s\n---\n# T\n")
    main(["-C", str(repo), "fmt"])
    assert p.read_text().startswith("---\ntype: screen\nslug: s\ntitle: T\n")
    # loads clean afterwards
    assert load(repo).ui_nodes_of_type("screen")


def test_a_check_is_reordered_with_the_claim_it_observes():
    """Sorting `verify:` by key alone would re-file every observation onto one claim."""
    text = (
        "---\ntype: api\nslug: s\ntitle: T\n---\n# T\n\n"
        "## Endpoints\n\n### submit\n"
        "- route: `POST /x`\n"
        '- errors: `409` when it is already on file.\n'
        '- verify: http_status(409, title="Duplicate")\n'
        "- does:\n  - files it.\n"
        '- verify: http_status(201, path="/x")\n'
    )
    body = fmt.format_text(text).splitlines()
    order = {line.split(":", 1)[0]: i for i, line in enumerate(body) if line.startswith("- ")}
    assert body.index('- verify: http_status(201, path="/x")') < order["- errors"]
    assert body.index('- verify: http_status(409, title="Duplicate")') > order["- errors"]


def test_a_check_written_above_every_claim_stays_above_them():
    """It belongs to the node's own contract, and only its position says so."""
    text = (
        "---\ntype: concept\nslug: s\ntitle: T\n---\n# T\n\n"
        "## Methods\n\n### hold\n"
        "- sig: `hold(seat: str) -> dict`\n"
        '- verify: json_path("hold.version", equals="1")\n'
        "- raises: `Seat Unavailable` when it is taken.\n"
        '- verify: http_status(409)\n'
        "- code: app/hold.py::hold\n"
    )
    body = fmt.format_text(text).splitlines()
    i_contract = body.index('- verify: json_path("hold.version", equals="1")')
    i_raises = body.index("- raises: `Seat Unavailable` when it is taken.")
    assert i_contract < i_raises < body.index("- verify: http_status(409)")


def test_repeat_bullets_have_a_canonical_slot():
    """`one-per`/`variants` sit between role and name; `unique-by` right after the name."""
    text = (
        "---\ntype: screen\nslug: s\ntitle: T\n---\n# T\n\n"
        "## Components\n\n### stage-row-button\n"
        "- unique-by: `stage.id`\n"
        "- name: `{stage.name}`\n"
        "- one-per: `stage`\n"
        "- role: button\n"
    )
    body = fmt.format_text(text).splitlines()
    order = [body.index(f"- {b}") for b in (
        "role: button", "one-per: `stage`", "name: `{stage.name}`", "unique-by: `stage.id`")]
    assert order == sorted(order)
