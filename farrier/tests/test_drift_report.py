"""What `--check` says when a generated file has been hand-edited."""

from __future__ import annotations

from pathlib import Path

import pytest

from farrier.drift import Drifted, attribute, report, sources_for
from farrier.frontmatter import read_yaml
from farrier.install import check_outputs, install_outputs, render_expected, set_layers

SKILL_BODY = "House rules.\n\nThe repo is linted with ruff."
PROMPT_BODY = "Stage by explicit path.\n\nPush as you go."


def _library(tmp_path: Path) -> Path:
    root = tmp_path / "agents"
    skill = root / "library" / "skills" / "stablemate" / "ostler" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text(
        f"---\nname: ostler\ndescription: x\n---\n\n# Ostler\n\n{SKILL_BODY}\n",
        encoding="utf-8",
    )
    prompt = root / "library" / "prompts" / "stablemate" / "commit.md"
    prompt.parent.mkdir(parents=True)
    prompt.write_text(
        f"---\ndescription: Commit\n---\n\n# Commit\n\n{PROMPT_BODY}\n", encoding="utf-8"
    )
    (root / "packs").mkdir()
    return root


@pytest.fixture
def rendered(tmp_path: Path) -> tuple[Path, dict[Path, str]]:
    """An installed repo whose AGENTS.md aggregates one skill and one prompt."""
    set_layers(_library(tmp_path))
    repo = tmp_path / "demo"
    repo.mkdir()
    (repo / "agents.yml").write_text(
        "agents:\n  claude: true\n"
        "skills:\n  - stablemate/ostler\n"
        "prompts:\n  - stablemate/commit\n"
        "localInstructions:\n"
        "  - skills: [demo-stablemate-ostler]\n"
        "    prompts: [demo-stablemate-commit]\n"
        '    paths: ["."]\n'
        "    includeReadme: false\n",
        encoding="utf-8",
    )
    outputs = render_expected(read_yaml(repo / "agents.yml"), repo)
    install_outputs(repo, outputs)
    return repo, outputs




def test_a_hand_edit_names_the_file_the_edit_belongs_in(rendered, capsys):
    """The whole point."""
    repo, outputs = rendered
    agents = repo / "AGENTS.md"
    agents.write_text(agents.read_text(encoding="utf-8") + "\nInvented rule.\n", encoding="utf-8")

    assert check_outputs(repo, outputs) == 1

    out = capsys.readouterr().out
    assert "AGENTS.md has drifted from the generated source" in out
    assert "library/skills/stablemate/ostler/SKILL.md" in out
    assert "library/prompts/stablemate/commit.md" in out
    assert "Put the update in the upstream files" in out
    assert "make agent-install" in out


def test_the_report_says_the_comparison_is_against_the_working_tree(rendered, capsys):
    """Otherwise a partially-staged edit produces a block whose diff the agent cannot find, and `git diff --cached` says the repo is clean."""
    repo, outputs = rendered
    (repo / "AGENTS.md").write_text("gone\n", encoding="utf-8")

    check_outputs(repo, outputs)

    assert "against the working tree, not the index" in capsys.readouterr().out


def test_the_prefix_lines_survive_for_the_other_two_verdicts(rendered, capsys):
    """`missing:` and `extra:` stay greppable — they are what an operator scans for — and each still gets the sentence saying which way to resolve it."""
    repo, outputs = rendered
    (repo / "AGENTS.md").unlink()
    stale = repo / ".claude" / "skills" / "demo-stablemate-ostler" / "references" / "old.md"
    stale.parent.mkdir(parents=True)
    stale.write_text("stale\n", encoding="utf-8")

    assert check_outputs(repo, outputs) == 1

    out = capsys.readouterr().out
    assert "missing: AGENTS.md" in out
    assert "extra: .claude/skills/demo-stablemate-ostler/references/old.md" in out
    assert "removed or renamed and left this copy behind" in out


def test_a_current_repo_reports_nothing(rendered, capsys):
    repo, outputs = rendered
    assert check_outputs(repo, outputs) == 0
    assert capsys.readouterr().out == ""




def test_an_edit_inside_one_half_of_an_aggregate_names_that_half(rendered):
    """AGENTS.md joins two library files whose rendered halves can sit hundreds of lines apart."""
    repo, outputs = rendered
    content = outputs[repo / "AGENTS.md"]
    edited = content.replace("linted with ruff", "linted with nothing")

    assert attribute(content, edited) == {"library/skills/stablemate/ostler/SKILL.md"}


def test_an_append_past_the_last_source_attributes_to_neither(rendered):
    """New text at the end of the file belongs to no source, and guessing at the last one would send the agent to a file that never contained it."""
    repo, outputs = rendered
    content = outputs[repo / "AGENTS.md"]

    assert attribute(content, f"{content}\n\nInvented rule.\n") == set()


def test_an_edit_perturbing_every_part_falls_back_to_listing_all(rendered):
    """A reflow or a re-indent moves every part at once."""
    repo, outputs = rendered
    content = outputs[repo / "AGENTS.md"]

    assert attribute(content, content.replace("\n", "\r\n")) == set()


def test_the_report_marks_the_attributed_source_and_only_it(rendered):
    repo, outputs = rendered
    content = outputs[repo / "AGENTS.md"]
    edited = content.replace("Push as you go", "Push whenever")

    text = report([], [Drifted("AGENTS.md", content, content, edited)], [])

    marked = [line for line in text.splitlines() if "<- the drift is in this one" in line]
    assert len(marked) == 1
    assert "library/prompts/stablemate/commit.md" in marked[0]




def test_a_generated_skill_resolves_through_its_own_front_matter(rendered):
    """A skill copy stamps `metadata.source`; nothing extra is needed to report it."""
    repo, outputs = rendered
    skill = repo / ".claude" / "skills" / "demo-stablemate-ostler" / "SKILL.md"
    content = outputs[skill]

    assert sources_for(content, str(content)) == [
        "library/skills/stablemate/ostler/SKILL.md"
    ]


def test_the_aggregate_resolves_even_though_it_carries_no_banner(rendered):
    """AGENTS.md deliberately has no provenance in the file — a "generated, do not edit" line in an always-loaded rules file reads as a rule about the repo."""
    repo, outputs = rendered
    content = outputs[repo / "AGENTS.md"]

    assert "generated by farrier" not in str(content)
    assert sources_for(content, str(content)) == [
        "library/skills/stablemate/ostler/SKILL.md",
        "library/prompts/stablemate/commit.md",
    ]


def test_provenance_is_read_off_the_expected_text_not_the_edited_copy(rendered):
    """A drifted file is one somebody edited, and its front matter is exactly as editable as its body."""
    repo, outputs = rendered
    skill = repo / ".claude" / "skills" / "demo-stablemate-ostler" / "SKILL.md"
    expected = str(outputs[skill])
    forged = expected.replace(
        "library/skills/stablemate/ostler/SKILL.md", "library/skills/made/up/SKILL.md"
    )

    text = report([], [Drifted("s.md", outputs[skill], expected, forged)], [])

    assert "library/skills/stablemate/ostler/SKILL.md" in text
    assert "made/up" not in text


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
