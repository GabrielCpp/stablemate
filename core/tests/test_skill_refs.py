"""A template names a skill by its library name, and each harness reads the same file."""

from __future__ import annotations

from pathlib import Path

import pytest

from stablemate_core.skill_refs import (
    MissingSkill,
    SkillCatalog,
    SkillEntry,
    SkillRefs,
    display_path,
)

ROOT = Path("/work/acme")
HOME = Path("/home/dev")
BASE = ROOT / ".claude/skills/acme-api"

REPO_REVIEW = SkillEntry(
    "review", "acme-review", ROOT / ".claude/skills/acme-review/SKILL.md", ("qa",)
)
HOME_REVIEW = SkillEntry("review", "review", HOME / ".claude/skills/review/SKILL.md", ("qa",))
HOME_DEPLOY = SkillEntry(
    "deploy", "deploy", HOME / ".claude/skills/deploy/SKILL.md", ("infra", "qa")
)


def refs(harness: str = "claude", on_missing=None) -> SkillRefs:
    catalog = SkillCatalog.of([REPO_REVIEW, HOME_REVIEW, HOME_DEPLOY])
    return SkillRefs(catalog, harness, BASE, ROOT, HOME, on_missing)


def test_the_most_local_entry_wins() -> None:
    assert refs().skill_link("review") == "[acme-review](../acme-review/SKILL.md)"


def test_a_home_skill_links_from_the_home_folder() -> None:
    assert refs().skill_link("deploy") == "[deploy](~/.claude/skills/deploy/SKILL.md)"


def test_a_path_may_point_inside_the_skill_folder() -> None:
    assert refs().skill_path("review", "references/x.md") == "../acme-review/references/x.md"


@pytest.mark.parametrize(
    ("harness", "command"),
    [
        ("claude", "/acme-review"),
        ("copilot", "/acme-review"),
        ("codex", "$acme-review"),
        ("opencode", "Read `../acme-review/SKILL.md` and follow its instructions"),
    ],
)
def test_each_harness_invokes_a_skill_its_own_way(harness: str, command: str) -> None:
    assert refs(harness).skill_command("review") == command


def test_a_named_miss_raises() -> None:
    with pytest.raises(MissingSkill) as exc:
        refs().skill_link("absent")
    assert exc.value.name == "absent"


def test_a_named_miss_defers_to_the_caller_when_asked() -> None:
    misses: list[str] = []

    def on_missing(name: str) -> str:
        misses.append(name)
        return f"<{name}>"

    assert refs(on_missing=on_missing).skill_command("absent") == "<absent>"
    assert misses == ["absent"]


def test_a_tag_query_is_an_and_listed_once_per_name() -> None:
    helpers = refs()
    assert helpers.find_by_tags("QA") == (
        "[deploy](~/.claude/skills/deploy/SKILL.md), [acme-review](../acme-review/SKILL.md)"
    )
    assert helpers.find_by_tags("qa", "infra") == "[deploy](~/.claude/skills/deploy/SKILL.md)"


def test_a_tag_query_with_no_match_is_empty() -> None:
    assert refs().find_by_tags("mobile") == ""
    assert refs().find_by_tags() == ""


def test_has_skill_never_raises() -> None:
    assert refs().has_skill("review")
    assert not refs().has_skill("absent")


def test_a_path_outside_the_repo_and_home_stays_absolute() -> None:
    assert display_path(Path("/opt/x/SKILL.md"), base=BASE, root=ROOT, home=HOME) == (
        "/opt/x/SKILL.md"
    )
