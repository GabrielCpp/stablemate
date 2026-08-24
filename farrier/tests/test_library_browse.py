"""`farrier library list|show` — reading the stack you are actually going to install from.

The library is two layers deep and the winner is decided by precedence, so the file you
open in an editor is not reliably the file that gets rendered. Everything here is about
making that visible: `list` names the layer each item resolves from and says out loud
when the winner is hiding somebody else's copy of the same name, and `show` prints the
one that would actually be used.

The second theme is naming. An item is addressed by its library id
(`architecture/hexagonal-architecture`), installs under its group name
(`architecture-hexagonal-architecture`), and is remembered by neither — so `show` takes
any of the three, and refuses rather than guesses when a bare basename means two things.

    uv run --all-packages pytest farrier/tests/test_library_browse.py
"""

from __future__ import annotations

from pathlib import Path

import pytest

from farrier.cli import main
from farrier.layers import BASE_DIR_ENV

SKILL = "---\nname: {name}\ndescription: {desc}\n---\n\n# {name}\n\n{body}\n"


def write(root: Path, rel: str, text: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def skill(root: Path, rel: str, *, desc: str = "A thing", body: str = "Rules.") -> Path:
    """A skill at ``library/skills/<rel>/SKILL.md`` under *root*."""
    name = rel.rsplit("/", 1)[-1]
    return write(
        root,
        f"library/skills/{rel}/SKILL.md",
        SKILL.format(name=name, desc=desc, body=body),
    )


@pytest.fixture
def stack(tmp_path, monkeypatch):
    """A two-layer stack: an overlay shadowing `stacks/api`, and a base with three skills.

    `stacks/api` exists in both layers on purpose — it is the case every assertion about
    shadowing needs, and the case an operator hits without noticing.
    """
    base, overlay = tmp_path / "base", tmp_path / "overlay"
    skill(base, "stacks/api", desc="Base copy")
    skill(base, "web/api", desc="A different api")
    skill(base, "web/forms")
    write(base, "packs/web.yml", "skills:\n  - web/*\n")
    write(base, "library/prompts/team/review.md", SKILL.format(
        name="review", desc="Review it", body="Steps."))
    skill(overlay, "stacks/api", desc="Overlay copy")
    monkeypatch.setenv(BASE_DIR_ENV, str(base))
    return overlay


def run(args: list[str], overlay: Path) -> int:
    return main(["library", *args, "--library", str(overlay)])


def test_list_names_the_layer_each_item_resolves_from(stack, capsys):
    assert run(["list", "--skills"], stack) == 0
    out = capsys.readouterr().out
    assert "## skills (3)" in out
    assert "web/forms" in out
    # Every row carries a layer, because "which copy is this" is the whole question.
    rows = [line for line in out.splitlines() if line.startswith("  ") and "/" in line]
    assert rows and all("base" in row or str(stack) in row for row in rows)


def test_a_shadowed_item_is_reported_as_shadowed(stack, capsys):
    """The overlay winning is fine. The overlay winning *silently* is the bug."""
    assert run(["list", "--skills"], stack) == 0
    row = next(
        line for line in capsys.readouterr().out.splitlines()
        if line.strip().startswith("stacks/api")
    )
    assert str(stack) in row
    assert "shadows" in row


def test_an_item_only_one_layer_has_is_not_reported_as_shadowed(stack, capsys):
    assert run(["list", "--skills"], stack) == 0
    row = next(
        line for line in capsys.readouterr().out.splitlines()
        if line.strip().startswith("web/forms")
    )
    assert "shadows" not in row


def test_list_prints_the_installed_name_beside_the_library_id(stack, capsys):
    """Two names for one thing, and which one you have depends on where you came from."""
    assert run(["list", "--skills"], stack) == 0
    row = next(
        line for line in capsys.readouterr().out.splitlines()
        if line.strip().startswith("web/forms")
    )
    assert "web-forms" in row


def test_layer_base_reports_what_the_base_holds_even_where_it_loses(stack, capsys):
    """`--layer base` is asked by someone editing the base. Hiding the shadowed copy
    would answer a question they did not ask."""
    assert run(["list", "--skills", "--layer", "base"], stack) == 0
    out = capsys.readouterr().out
    assert "## skills (3)" in out
    assert "stacks/api" in out


def test_layer_overlay_reports_the_overlay_alone(stack, capsys):
    assert run(["list", "--skills", "--layer", "overlay"], stack) == 0
    out = capsys.readouterr().out
    assert "## skills (1)" in out
    assert "stacks/api" in out
    assert "web/forms" not in out


def test_no_kind_flag_reports_every_kind(stack, capsys):
    assert run(["list"], stack) == 0
    out = capsys.readouterr().out
    for heading in ("## skills", "## prompts", "## policies", "## packs",
                    "## scaffolds", "## roots"):
        assert heading in out


def test_a_kind_the_stack_has_none_of_is_reported_as_empty_not_omitted(stack, capsys):
    """A missing block reads as a broken command; `(none)` reads as an answer."""
    assert run(["list", "--scaffolds"], stack) == 0
    out = capsys.readouterr().out
    assert "## scaffolds (0)" in out
    assert "(none)" in out


def test_show_prints_the_winning_layers_source(stack, capsys):
    assert run(["show", "--skill", "stacks/api"], stack) == 0
    assert "Overlay copy" in capsys.readouterr().out


def test_show_can_be_pinned_to_a_layer(stack, capsys):
    assert run(["show", "--skill", "stacks/api", "--layer", "base"], stack) == 0
    assert "Base copy" in capsys.readouterr().out


def test_show_prints_the_source_verbatim_so_it_pipes(stack, capsys):
    """No header, no banner: the output is the file, byte for byte."""
    assert run(["show", "--skill", "web/forms"], stack) == 0
    expected = (stack.parent / "base" / "library/skills/web/forms/SKILL.md").read_text()
    assert capsys.readouterr().out == expected


def test_show_accepts_the_installed_name(stack, capsys):
    assert run(["show", "--skill", "web-forms"], stack) == 0
    assert "# forms" in capsys.readouterr().out


def test_show_accepts_a_bare_basename(stack, capsys):
    assert run(["show", "--skill", "forms"], stack) == 0
    assert "# forms" in capsys.readouterr().out


def test_an_ambiguous_basename_is_refused_with_both_spellings(stack):
    """`api` is two skills. Picking one would be a coin flip nobody sees land."""
    with pytest.raises(SystemExit) as error:
        run(["show", "--skill", "api"], stack)
    message = str(error.value)
    assert "stacks/api" in message
    assert "web/api" in message


def test_an_unknown_name_lists_what_does_exist(stack):
    with pytest.raises(SystemExit) as error:
        run(["show", "--skill", "nope"], stack)
    assert "web/forms" in str(error.value)


def test_show_needs_exactly_one_selector(stack):
    with pytest.raises(SystemExit) as error:
        run(["show"], stack)
    assert "--skill NAME" in str(error.value)


def test_show_refuses_a_layer_that_does_not_have_the_item(stack):
    with pytest.raises(SystemExit) as error:
        run(["show", "--skill", "web/forms", "--layer", "overlay"], stack)
    assert "does not provide" in str(error.value)


def test_packs_and_prompts_are_listed_too(stack, capsys):
    assert run(["list", "--packs", "--prompts"], stack) == 0
    out = capsys.readouterr().out
    assert "## packs (1)" in out
    assert "web" in out
    assert "## prompts (1)" in out
    assert "team/review" in out


def test_show_reads_a_pack(stack, capsys):
    assert run(["show", "--pack", "web"], stack) == 0
    assert "web/*" in capsys.readouterr().out


def test_the_older_dash_dash_check_spelling_still_runs_the_check(stack, capsys):
    """A Makefile in a repo somewhere says `farrier library --check`. It keeps working."""
    assert run(["--check"], stack) == 0
    assert "error(s)" in capsys.readouterr().out


def test_check_is_a_mode_of_its_own(stack, capsys):
    assert run(["check"], stack) == 0
    assert "error(s)" in capsys.readouterr().out


def test_library_with_no_mode_says_what_the_modes_are(stack):
    with pytest.raises(SystemExit) as error:
        run([], stack)
    assert "list, show or check" in str(error.value)
