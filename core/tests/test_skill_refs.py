"""A template names a skill by its library name, and each harness reads the same file."""

from __future__ import annotations

from pathlib import Path

import pytest

from stablemate_core.skill_refs import (
    MissingSkill,
    RetiredHelper,
    SkillCatalog,
    SkillEntry,
    SkillRefs,
    display_path,
    retired_hint,
    scan_catalog,
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


def _skill(folder: Path, installed: str, front: str) -> Path:
    path = folder / installed / "SKILL.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\n{front}\n---\n\nBody.\n", encoding="utf-8")
    return path


GENERATED = """name: acme-review
description: "Review: the checklist"
metadata:
  name: review
  generated_by: farrier
  tags: [qa, Web]"""


def test_a_generated_skill_is_found_by_its_library_name(tmp_path: Path) -> None:
    repo = tmp_path / "acme"
    (repo / ".git").mkdir(parents=True)
    path = _skill(repo / ".claude/skills", "acme-review", GENERATED)

    catalog = scan_catalog("claude", repo, home=tmp_path / "home")

    assert catalog.get("review") == SkillEntry("review", "acme-review", path, ("qa", "web"))


def test_a_hand_written_skill_answers_to_its_own_name_and_tags(tmp_path: Path) -> None:
    home = tmp_path / "home"
    path = _skill(home / ".claude/skills", "notes", "name: notes\ntags:\n  - docs\n  - planning")

    catalog = scan_catalog("claude", tmp_path / "work", home=home)

    assert catalog.get("notes") == SkillEntry("notes", "notes", path, ("docs", "planning"))


def test_the_cwd_wins_over_the_repo_root_and_the_root_over_home(tmp_path: Path) -> None:
    repo = tmp_path / "acme"
    (repo / ".git").mkdir(parents=True)
    home = tmp_path / "home"
    nested = _skill(repo / "web/.claude/skills", "web-review", "name: web-review\nmetadata:\n  name: review")
    _skill(repo / ".claude/skills", "acme-review", GENERATED)
    _skill(home / ".claude/skills", "review", "name: review")
    _skill(home / ".claude/skills", "deploy", "name: deploy")

    catalog = scan_catalog("claude", repo / "web", home=home)

    review = catalog.get("review")
    assert review is not None
    assert review.path == nested
    assert catalog.get("deploy") is not None


def test_the_walk_stops_at_the_repo_root(tmp_path: Path) -> None:
    _skill(tmp_path / ".claude/skills", "outside", "name: outside")
    repo = tmp_path / "acme"
    (repo / ".git").mkdir(parents=True)

    assert scan_catalog("claude", repo, home=tmp_path / "home").get("outside") is None


def test_only_claude_reads_skills_from_the_added_dirs(tmp_path: Path) -> None:
    added = tmp_path / "docs-repo"
    _skill(added / ".claude/skills", "style", "name: style")
    _skill(added / ".agents/skills", "style", "name: style")
    cwd = tmp_path / "acme"

    claude = scan_catalog("claude", cwd, home=tmp_path / "home", added_dirs=[added])
    codex = scan_catalog("codex", cwd, home=tmp_path / "home", added_dirs=[added])

    assert claude.get("style") is not None
    assert codex.get("style") is None


@pytest.mark.parametrize(
    ("harness", "folder"),
    [("claude", ".claude/skills"), ("codex", ".agents/skills"), ("copilot", ".agents/skills")],
)
def test_each_harness_reads_its_own_home_folder(tmp_path: Path, harness: str, folder: str) -> None:
    home = tmp_path / "home"
    _skill(home / folder, "deploy", "name: deploy")

    assert scan_catalog(harness, tmp_path / "work", home=home).get("deploy") is not None


def test_a_prompt_joins_the_catalog_under_its_library_name(tmp_path: Path) -> None:
    repo = tmp_path / "acme"
    commands = repo / ".claude/commands"
    commands.mkdir(parents=True)
    prompt = commands / "acme-retro.md"
    prompt.write_text("---\ndescription: x\nmetadata:\n  name: retro\n---\n", encoding="utf-8")

    entry = scan_catalog("claude", repo, home=tmp_path / "home").get("retro")

    assert entry == SkillEntry("retro", "acme-retro", prompt, ())


def test_a_retired_helper_names_its_replacement() -> None:
    assert "skill_command" in str(RetiredHelper("skill_load_ref"))
    assert "has_skill" in retired_hint("'isUsingInstruction' is undefined")
