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
    write(repo / FOO_STORY, story_md("01-foo", "Foo", "Not started", fixtures=["no-such"]))
    found = _findings(repo, "unknown-story-fixture")
    assert [(f.severity, f.ref) for f in found] == [("error", "no-such")]
    # The message names what *is* declared, so the repair is a spelling away rather than a hunt.
    assert "seeded-accounts" in found[0].message


def test_an_undeclared_name_the_plan_asks_for_is_told_to_declare_it(repo: Path) -> None:
    """The plan reaches for the name, so it is an arrangement nobody declared."""
    _declare(repo)
    write(repo / FOO_STORY, story_md("01-foo", "Foo", "Not started", fixtures=["no-such"]))
    write(repo / FOO_PLAN, 'qa.fixture("no-such")\n')

    [found] = _findings(repo, "unknown-story-fixture")

    assert "add a fixture node" in (found.suggestion or "")
    # One fact, one finding. The same evidence decided the suggestion above; spending it a
    # second time on a warning would pair an error and a warning prescribing opposite repairs.
    assert _findings(repo, "unused-story-fixture") == []


def test_an_undeclared_name_no_plan_asks_for_is_told_to_delete_the_bullet(repo: Path) -> None:
    """Nothing declares it and nothing reaches for it, so it was never an arrangement.

    This is the case every undeclared name in the corpus was in when the branch was written —
    eleven names across three apps, none of them used by a plan — which is why the single
    "declare it" suggestion this replaced was wrong in 100% of real occurrences.
    """
    _declare(repo)
    write(repo / FOO_STORY, story_md("01-foo", "Foo", "Not started", fixtures=["no-such"]))
    write(repo / FOO_PLAN, "PLAN = 1\n")

    [found] = _findings(repo, "unknown-story-fixture")

    assert "delete the bullet" in (found.suggestion or "")
    assert _findings(repo, "unused-story-fixture") == []


def test_an_undeclared_name_with_no_plan_yet_prescribes_neither_repair(repo: Path) -> None:
    """No plan means nothing has reached for the name, so which repair is right is unknown.

    *Undetermined ⇒ do not emit executable code*, one level up: an unsupported suggestion is
    advice a repair agent will follow, and following the wrong one makes the book worse.
    """
    _declare(repo)
    write(repo / FOO_STORY, story_md("01-foo", "Foo", "Not started", fixtures=["no-such"]))

    [found] = _findings(repo, "unknown-story-fixture")

    assert "add a fixture node" not in (found.suggestion or "")
    assert "delete the bullet" not in (found.suggestion or "")
    assert "The plan decides" in (found.suggestion or "")


def test_a_plan_asking_for_a_fixture_the_story_does_not_state_is_an_error(repo: Path) -> None:
    _declare(repo)
    write(repo / FOO_PLAN, 'qa.fixture("seeded-accounts")\n')
    found = _findings(repo, "undeclared-story-fixture")
    assert [(f.severity, f.ref) for f in found] == [("error", "seeded-accounts")]


def test_a_stated_fixture_no_plan_asks_for_is_a_warning(repo: Path) -> None:
    _declare(repo)
    write(repo / FOO_STORY, story_md("01-foo", "Foo", "Not started", fixtures=["seeded-accounts"]))
    write(repo / FOO_PLAN, "PLAN = 1\n")
    found = _findings(repo, "unused-story-fixture")
    assert [(f.severity, f.ref) for f in found] == [("warn", "seeded-accounts")]
    assert doctor.run(load(repo)).errors == 0


def test_a_story_with_no_plan_yet_is_not_in_disagreement(repo: Path) -> None:
    """The plan phase has not run. Only the repo-level half of the rule applies."""
    _declare(repo)
    write(repo / FOO_STORY, story_md("01-foo", "Foo", "Not started", fixtures=["seeded-accounts"]))
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


def test_a_story_missing_the_section_entirely_reads_as_unwritten(repo: Path) -> None:
    """A story.md predating the contract. `Fixtures (missing)` is a different repair from
    `Fixtures (empty)` — no amount of writing under the headings that are there fixes it."""
    _declare(repo)
    body = (repo / FOO_STORY).read_text(encoding="utf-8")
    write(repo / FOO_STORY, body.replace("## Fixtures\n\n(none)\n\n", ""))
    found = _findings(repo, "unwritten-story")
    assert [f.severity for f in found] == ["error"]
    assert "Fixtures (missing)" in found[0].message


BOOK = """\
---
type: server
title: Claims
---
# Claims

## Endpoints

### list-claims
- method: GET
- path: /api/claims
- fixture: {bullet}
- authorization: an adjuster reads every claim on file.
"""

BOOK_PATH = "docs/features/area/claims.md"


def test_a_book_fixture_the_repo_never_declared_is_an_error(repo: Path) -> None:
    """The same bar a story's `## Fixtures` is held to, applied where the arrangement now lives.

    A book bullet naming nothing is worse than a story one: it compiles straight into a
    `qa.fixture(...)` call, so the miss surfaces as a scenario that cannot arrange rather than as
    a declaration a reader could have checked.
    """
    _declare(repo)
    write(repo / BOOK_PATH, BOOK.format(bullet="no-such — a state nobody declared"))
    found = _findings(repo, "unknown-book-fixture")
    assert [(f.severity, f.ref) for f in found] == [("error", "no-such")]
    assert "seeded-accounts" in found[0].message


def test_a_declared_book_fixture_is_clean(repo: Path) -> None:
    _declare(repo)
    write(repo / BOOK_PATH, BOOK.format(bullet="seeded-accounts 2 — two claims on file"))
    assert _findings(repo, "unknown-book-fixture") == []
    assert _findings(repo, "qa-fixture-bullet") == []


def test_a_hand_written_fixture_with_no_book_node_behind_it_is_a_warning(repo: Path) -> None:
    """The retirement nudge: a `qa: {fixtures:}` entry is still the permanent fallback tier,
    but one with no book fixture node behind it is a candidate `ostler qa fixtures migrate`
    has not yet been run on."""
    _declare(repo)
    found = _findings(repo, "unmigrated-fixture-declaration")
    assert [(f.severity, f.ref) for f in found] == [("warn", "seeded-accounts")]


def test_a_hand_written_fixture_with_a_book_node_behind_it_is_clean(repo: Path) -> None:
    _declare(repo)
    write(repo / BOOK_PATH, BOOK.format(bullet="seeded-accounts 2 — two claims on file"))
    write(
        repo / "docs/features/area/fixtures/seeded-accounts.md",
        "---\ntype: fixture\ntitle: Seeded accounts\n---\n"
        "# Seeded accounts\n\n"
        "- provides:\n"
        "  - id — the adjuster's id\n\n"
        "## Steps\n\n"
        "### seed-it\n\n"
        "- kind: seed\n"
        "- run: ./scripts/seed-accounts.sh\n",
    )
    assert _findings(repo, "unmigrated-fixture-declaration") == []


def test_a_book_fixture_that_is_not_a_reference_is_an_error(repo: Path) -> None:
    """`Seeded Accounts` could not be a key under `qa: {fixtures:}`, so it names no arrangement.
    Reported as a grammar problem rather than a missing declaration, because the repair is in
    the bullet and not in `agents.yml`."""
    _declare(repo)
    write(repo / BOOK_PATH, BOOK.format(bullet="Seeded Accounts"))
    found = _findings(repo, "qa-fixture-bullet")
    assert [f.severity for f in found] == ["error"]
    assert "is not a fixture name" in found[0].message
