"""`doctor` holds a story's `## Fixtures` to the repo's declarations and to its own plan."""

from __future__ import annotations

from pathlib import Path

from ostler import doctor
from ostler.model import load

from conftest import FOO_ID, FOO_STORY, specs_root, story_md, write, epics_root

FOO_PLAN = f"{FOO_ID}/qa_plan.py"

AGENTS = """\
qa:
  tools: [node]
  fixtures:
    seeded-accounts:
      tool: node
      args: ["auth/seed.mjs"]
      provides: "an adjuster and two holders exist in the auth emulator"
"""


def _findings(repo: Path, code: str) -> list[doctor.Finding]:
    return [f for f in doctor.run(load(repo)).findings if f.code == code]


def _declare(repo: Path, body: str = AGENTS) -> None:
    write(repo / "agents.yml", body)


def test_a_story_that_arranges_nothing_is_clean(repo: Path) -> None:
    _declare(repo)
    assert doctor.run(load(repo)).errors == 0


def test_a_story_naming_a_fixture_the_repo_never_declared_is_an_error(repo: Path) -> None:
    _declare(repo)
    write(epics_root() / FOO_STORY, story_md("01-foo", "Foo", "Not started", eid=FOO_ID, fixtures=["no-such"]))
    found = _findings(repo, "unknown-story-fixture")
    assert [(f.severity, f.ref) for f in found] == [("error", "no-such")]
    assert "seeded-accounts" in found[0].message


def test_an_undeclared_name_the_plan_asks_for_is_told_to_declare_it(repo: Path) -> None:
    """The plan reaches for the name, so it is an arrangement nobody declared."""
    _declare(repo)
    write(epics_root() / FOO_STORY, story_md("01-foo", "Foo", "Not started", eid=FOO_ID, fixtures=["no-such"]))
    write(specs_root() / FOO_PLAN, 'qa.fixture("no-such")\n')

    [found] = _findings(repo, "unknown-story-fixture")

    assert "agents.yml" in (found.suggestion or "")
    assert _findings(repo, "unused-story-fixture") == []


def test_an_undeclared_name_no_plan_asks_for_is_told_to_delete_the_bullet(repo: Path) -> None:
    """Nothing declares it and nothing reaches for it, so it was never an arrangement."""
    _declare(repo)
    write(epics_root() / FOO_STORY, story_md("01-foo", "Foo", "Not started", eid=FOO_ID, fixtures=["no-such"]))
    write(specs_root() / FOO_PLAN, "PLAN = 1\n")

    [found] = _findings(repo, "unknown-story-fixture")

    assert "delete the bullet" in (found.suggestion or "")
    assert _findings(repo, "unused-story-fixture") == []


def test_an_undeclared_name_with_no_plan_yet_prescribes_neither_repair(repo: Path) -> None:
    """No plan means nothing has reached for the name, so which repair is right is unknown."""
    _declare(repo)
    write(epics_root() / FOO_STORY, story_md("01-foo", "Foo", "Not started", eid=FOO_ID, fixtures=["no-such"]))

    [found] = _findings(repo, "unknown-story-fixture")

    assert "add a fixture node" not in (found.suggestion or "")
    assert "delete the bullet" not in (found.suggestion or "")
    assert "The plan decides" in (found.suggestion or "")


def test_a_plan_asking_for_a_fixture_the_story_does_not_state_is_an_error(repo: Path) -> None:
    _declare(repo)
    write(specs_root() / FOO_PLAN, 'qa.fixture("seeded-accounts")\n')
    found = _findings(repo, "undeclared-story-fixture")
    assert [(f.severity, f.ref) for f in found] == [("error", "seeded-accounts")]


def test_a_stated_fixture_no_plan_asks_for_is_a_warning(repo: Path) -> None:
    _declare(repo)
    write(epics_root() / FOO_STORY, story_md("01-foo", "Foo", "Not started", eid=FOO_ID, fixtures=["seeded-accounts"]))
    write(specs_root() / FOO_PLAN, "PLAN = 1\n")
    found = _findings(repo, "unused-story-fixture")
    assert [(f.severity, f.ref) for f in found] == [("warn", "seeded-accounts")]
    assert doctor.run(load(repo)).errors == 0


def test_a_story_with_no_plan_yet_is_not_in_disagreement(repo: Path) -> None:
    """The plan phase has not run."""
    _declare(repo)
    write(epics_root() / FOO_STORY, story_md("01-foo", "Foo", "Not started", eid=FOO_ID, fixtures=["seeded-accounts"]))
    assert _findings(repo, "unused-story-fixture") == []
    assert doctor.run(load(repo)).errors == 0


def test_a_bullet_under_fixtures_that_names_nothing_is_an_error(repo: Path) -> None:
    _declare(repo)
    body = (epics_root() / FOO_STORY).read_text(encoding="utf-8")
    write(epics_root() / FOO_STORY, body.replace("## Fixtures\n\n(none)", "## Fixtures\n\n- whatever"))
    found = _findings(repo, "story-fixture-stray")
    assert [f.severity for f in found] == ["error"]
    assert "whatever" in found[0].message


def test_a_declaration_that_does_not_stand_up_is_an_error(repo: Path) -> None:
    """The containment check: a fixture may only invoke a tool the repo opted into."""
    _declare(repo, AGENTS.replace("tools: [node]", "tools: [docker]"))
    found = _findings(repo, "qa-fixture-declaration")
    assert [f.severity for f in found] == ["error"]
    assert "opted into" in found[0].message


def test_a_story_missing_the_section_entirely_reads_as_unwritten(repo: Path) -> None:
    """A story.md predating the contract."""
    _declare(repo)
    body = (epics_root() / FOO_STORY).read_text(encoding="utf-8")
    write(epics_root() / FOO_STORY, body.replace("## Fixtures\n\n(none)\n\n", ""))
    found = _findings(repo, "unwritten-story")
    assert [f.severity for f in found] == ["error"]
    assert "Fixtures (missing)" in found[0].message

