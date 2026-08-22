"""`doctor` holds a story's `## Fixtures` to the repo's declarations and to its own plan.

A QA fixture is held to the bar a test is held to, and that bar is *named, declared, used*.
The three ways a name here can be a lie are all static, and each has its own finding: the
repo's declarations do not stand up; a story names something the repo never declared; the
story and its `qa_plan.py` disagree about what the story arranges with.

The disagreement is checked in both directions on purpose. An *undeclared* use hides an
arrangement from the reader deciding whether the story is safe to change; an *unused*
declaration is a story claiming an arrangement it stopped making. They are not the same
repair, so they are not the same finding — and only the first is an error.
"""

from __future__ import annotations

from pathlib import Path

from ostler import doctor
from ostler.model import load

from conftest import story_md, write

FOO_STORY = "docs/epics/epic-a/stories/01-foo/story.md"
FOO_PLAN = "docs/specs/01-foo/qa_plan.py"

AGENTS = """\
qa:
  tools: [node]
  fixtures:
    seeded-accounts:
      tool: node
      args: ["auth/seed.mjs"]
      provides: "an adjuster and two holders exist in the auth emulator"
  fixture_modules: [identity]
"""


def _findings(repo: Path, code: str) -> list[doctor.Finding]:
    return [f for f in doctor.run(load(repo)).findings if f.code == code]


def _declare(repo: Path, body: str = AGENTS) -> None:
    write(repo / "agents.yml", body)
    write(repo / "docs/specs/_fixtures/identity.py", "TOKEN = 'x'\n")


def test_a_story_that_arranges_nothing_is_clean(repo: Path) -> None:
    _declare(repo)
    assert doctor.run(load(repo)).errors == 0


def test_a_story_naming_a_fixture_the_repo_never_declared_is_an_error(repo: Path) -> None:
    _declare(repo)
    write(repo / FOO_STORY, story_md("01-foo", "Foo", "Not started", fixtures=["no-such"]))
    found = _findings(repo, "unknown-story-fixture")
    assert [(f.severity, f.ref) for f in found] == [("error", "no-such")]
    # The message names what *is* declared, so the repair is a spelling away rather than a hunt.
    assert "seeded-accounts" in found[0].message


def test_a_plan_asking_for_a_fixture_the_story_does_not_state_is_an_error(repo: Path) -> None:
    _declare(repo)
    write(repo / FOO_PLAN, 'qa.fixture("seeded-accounts")\n')
    found = _findings(repo, "undeclared-story-fixture")
    assert [(f.severity, f.ref) for f in found] == [("error", "seeded-accounts")]


def test_an_imported_fixture_module_counts_as_arranged_with(repo: Path) -> None:
    _declare(repo)
    write(repo / FOO_PLAN, "from _fixtures.identity import bearer\n")
    assert [f.ref for f in _findings(repo, "undeclared-story-fixture")] == ["identity"]

    write(repo / FOO_STORY, story_md("01-foo", "Foo", "Not started", fixtures=["identity"]))
    assert _findings(repo, "undeclared-story-fixture") == []
    assert doctor.run(load(repo)).errors == 0


def test_a_stated_fixture_no_plan_asks_for_is_a_warning(repo: Path) -> None:
    _declare(repo)
    write(repo / FOO_STORY, story_md("01-foo", "Foo", "Not started", fixtures=["identity"]))
    write(repo / FOO_PLAN, "PLAN = 1\n")
    found = _findings(repo, "unused-story-fixture")
    assert [(f.severity, f.ref) for f in found] == [("warn", "identity")]
    assert doctor.run(load(repo)).errors == 0


def test_a_story_with_no_plan_yet_is_not_in_disagreement(repo: Path) -> None:
    """The plan phase has not run. Only the repo-level half of the rule applies."""
    _declare(repo)
    write(repo / FOO_STORY, story_md("01-foo", "Foo", "Not started", fixtures=["identity"]))
    assert _findings(repo, "unused-story-fixture") == []
    assert doctor.run(load(repo)).errors == 0


def test_a_bullet_under_fixtures_that_names_nothing_is_an_error(repo: Path) -> None:
    _declare(repo)
    body = (repo / FOO_STORY).read_text(encoding="utf-8")
    write(repo / FOO_STORY, body.replace("## Fixtures\n\n(none)", "## Fixtures\n\n- whatever"))
    found = _findings(repo, "story-fixture-stray")
    assert [f.severity for f in found] == ["error"]
    assert "whatever" in found[0].message


def test_a_declaration_that_does_not_stand_up_is_an_error(repo: Path) -> None:
    """The containment check: a fixture may only invoke a tool the repo opted into."""
    _declare(repo, AGENTS.replace("tools: [node]", "tools: [docker]"))
    found = _findings(repo, "qa-fixture-declaration")
    assert [f.severity for f in found] == ["error"]
    assert "opted into" in found[0].message


def test_a_declared_module_with_no_file_behind_it_is_an_error(repo: Path) -> None:
    write(repo / "agents.yml", AGENTS)
    found = _findings(repo, "qa-fixture-declaration")
    assert [f.severity for f in found] == ["error"]
    assert "identity" in found[0].message


def test_a_story_missing_the_section_entirely_reads_as_unwritten(repo: Path) -> None:
    """A story.md predating the contract. `Fixtures (missing)` is a different repair from
    `Fixtures (empty)` — no amount of writing under the headings that are there fixes it."""
    _declare(repo)
    body = (repo / FOO_STORY).read_text(encoding="utf-8")
    write(repo / FOO_STORY, body.replace("## Fixtures\n\n(none)\n\n", ""))
    found = _findings(repo, "unwritten-story")
    assert [f.severity for f in found] == ["error"]
    assert "Fixtures (missing)" in found[0].message
