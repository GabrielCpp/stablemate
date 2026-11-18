from __future__ import annotations

from pathlib import Path

import pytest
from ostler import crud, doctor, markdown, registry
from ostler.model import load

from conftest import present

pytestmark = pytest.mark.usefixtures("minting_root")

EPIC_LIST_CODES = {"milestone-epic-by-name", "milestone-epics-section"}


def _two_epics_and_a_milestone(root: Path) -> tuple[str, str, Path]:
    accounts = crud.create_epic(load(root), "accounts", "Accounts")
    profiles = crud.create_epic(load(root), "profiles", "Profiles")
    assert accounts.ok and profiles.ok
    assert crud.create_milestone(load(root), "mvp", "MVP").ok
    return accounts.entity_id, profiles.entity_id, root / "docs/milestones/0001-mvp/milestone.md"


def _epic_list_findings(root: Path) -> list[str]:
    return sorted(f.code for f in doctor.run(load(root)).findings if f.code in EPIC_LIST_CODES)


def test_milestone_epics_are_stored_by_id_and_shown_in_coding_order(tmp_path: Path):
    accounts_id, profiles_id, path = _two_epics_and_a_milestone(tmp_path)

    result = crud.set_milestone_epics(load(tmp_path), "mvp", ["profiles", accounts_id])

    assert result.ok, result.message
    doc = markdown.split(path.read_text(encoding="utf-8"))
    assert (doc.frontmatter or {})["epics"] == [profiles_id, accounts_id]
    section = present(doc.find_section(registry.MILESTONE_EPICS_HEADING))
    assert [line for line in section.body.splitlines() if line.strip()] == [
        f"1. Profiles (`{profiles_id}`)",
        f"2. Accounts (`{accounts_id}`)",
    ]
    milestone = present(load(tmp_path).milestone_by_name("mvp"))
    assert milestone.epics == [profiles_id, accounts_id]
    assert _epic_list_findings(tmp_path) == []


def test_a_list_written_by_name_is_a_finding_until_ostler_moves_it_onto_ids(tmp_path: Path):
    accounts_id, profiles_id, path = _two_epics_and_a_milestone(tmp_path)
    path.write_text(path.read_text(encoding="utf-8").replace(
        "epics: []", "epics:\n- accounts\n- profiles"), encoding="utf-8")

    assert _epic_list_findings(tmp_path) == [
        "milestone-epic-by-name", "milestone-epic-by-name", "milestone-epics-section"]
    assert present(load(tmp_path).milestone_by_name("mvp")).epics == [
        accounts_id, profiles_id]

    assert crud.set_milestone_epics(load(tmp_path), "mvp").ok

    assert (markdown.split(path.read_text(encoding="utf-8")).frontmatter or {})["epics"] == [
        accounts_id, profiles_id]
    assert _epic_list_findings(tmp_path) == []


def test_a_hand_edited_epics_section_is_a_finding(tmp_path: Path):
    _accounts_id, _profiles_id, path = _two_epics_and_a_milestone(tmp_path)
    assert crud.set_milestone_epics(load(tmp_path), "mvp", ["accounts"]).ok
    path.write_text(path.read_text(encoding="utf-8").replace("1. Accounts", "1. Acounts"),
                    encoding="utf-8")

    assert _epic_list_findings(tmp_path) == ["milestone-epics-section"]


def test_an_unknown_epic_leaves_the_milestone_untouched(tmp_path: Path):
    _accounts_id, _profiles_id, path = _two_epics_and_a_milestone(tmp_path)
    before = path.read_text(encoding="utf-8")

    result = crud.set_milestone_epics(load(tmp_path), "mvp", ["accounts", "billing"])

    assert not result.ok
    assert "'billing' names no epic" in result.message
    assert path.read_text(encoding="utf-8") == before


def _epic_with_one_story(root: Path, *, prose: bool, covers: list[str]) -> str:
    created = crud.create_epic(load(root), "accounts", "Accounts")
    assert created.ok
    if covers:
        assert crud.add_seed(load(root), "accounts", covers[0], status="researched").ok
    assert crud.create_story(load(root), "accounts", "sign-in", "Sign in", covers=covers).ok
    if prose:
        epic_md = present(load(root).epic_by_ref(created.entity_id)).epic_md
        assert epic_md is not None
        text = epic_md.read_text(encoding="utf-8")
        sections = "".join(f"## {spec.heading}\n\nThe accounts {spec.heading.lower()}.\n\n"
                           for spec in registry.EPIC_SECTIONS)
        epic_md.write_text(text.replace("## Seeds", sections + "## Seeds", 1), encoding="utf-8")
    return created.entity_name


def _codes(root: Path, epic: str) -> set[str]:
    return {f.code for f in doctor.run(load(root)).findings
            if f.epic == epic and f.severity == "error"}


def test_an_epic_with_stories_needs_every_section_of_the_contract(tmp_path: Path):
    epic = _epic_with_one_story(tmp_path, prose=False, covers=["sign-in"])

    finding = next(f for f in doctor.run(load(tmp_path)).findings if f.code == "unwritten-epic")

    assert finding.epic == epic
    for spec in registry.EPIC_SECTIONS:
        assert f"{spec.heading} (missing)" in finding.message


def test_a_bare_epic_skeleton_with_no_story_is_not_yet_unwritten(tmp_path: Path):
    created = crud.create_epic(load(tmp_path), "accounts", "Accounts")

    assert "unwritten-epic" not in _codes(tmp_path, created.entity_name)


def test_a_story_that_covers_no_seed_is_an_error(tmp_path: Path):
    epic = _epic_with_one_story(tmp_path, prose=True, covers=[])

    assert _codes(tmp_path, epic) - {"unwritten-story"} == {"story-covers-no-seed"}


def test_a_written_epic_whose_stories_cover_seeds_is_clean(tmp_path: Path):
    epic = _epic_with_one_story(tmp_path, prose=True, covers=["sign-in"])

    assert _codes(tmp_path, epic) - {"unwritten-story"} == set()


def test_an_epic_or_story_with_no_id_is_an_error(tmp_path: Path):
    epic = _epic_with_one_story(tmp_path, prose=True, covers=["sign-in"])
    graph = load(tmp_path)
    epic_md = present(graph.epics[0].epic_md)
    story_md = present(graph.epics[0].stories[0].story_md)
    epic_md.write_text("\n".join(line for line in epic_md.read_text(encoding="utf-8").splitlines()
                                 if not line.startswith(("id:", "- id:"))) + "\n", encoding="utf-8")
    story_md.write_text("\n".join(line for line in story_md.read_text(encoding="utf-8").splitlines()
                                  if not line.startswith("id:")) + "\n", encoding="utf-8")

    assert {"epic-without-id", "story-without-id"} <= _codes(tmp_path, epic)


def test_an_epic_folder_with_no_epic_md_is_an_error(tmp_path: Path):
    created = crud.create_epic(load(tmp_path), "accounts", "Accounts")
    present(load(tmp_path).epics[0].epic_md).unlink()

    findings = [f for f in doctor.run(load(tmp_path)).findings if f.code == "epic-without-epic-md"]

    assert [f.epic for f in findings] == [created.entity_name]


def test_doctor_milestone_reports_only_that_milestone_and_its_epics(tmp_path: Path):
    accounts_id, _profiles_id, _path = _two_epics_and_a_milestone(tmp_path)
    assert crud.set_milestone_epics(load(tmp_path), "mvp", [accounts_id]).ok
    assert crud.create_story(load(tmp_path), "profiles", "edit", "Edit a profile").ok
    assert crud.create_story(load(tmp_path), "accounts", "sign-in", "Sign in").ok

    report = doctor.run(load(tmp_path), milestone_filter="mvp")

    assert {f.epic for f in report.findings if f.epic} == {accounts_id}
    assert {f.path for f in report.findings if not f.epic} == {"docs/milestones/0001-mvp/milestone.md"}
    assert {"unwritten-epic", "story-covers-no-seed"} <= {f.code for f in report.findings}
    assert report.errors


def test_doctor_milestone_names_an_unknown_milestone(tmp_path: Path):
    report = doctor.run(load(tmp_path), milestone_filter="nope")

    assert [f.code for f in report.findings] == ["unknown-milestone"]


def test_a_new_milestone_folder_is_numbered_and_its_slug_still_names_it(tmp_path: Path):
    assert crud.create_milestone(load(tmp_path), "mvp", "MVP").ok

    second = crud.create_milestone(load(tmp_path), "beta", "Beta")

    assert second.entity_name == "0002-beta"
    assert present(load(tmp_path).milestone_by_name("beta")).name == "0002-beta"
    assert not crud.create_milestone(load(tmp_path), "beta", "Beta again").ok


def test_an_unnumbered_milestone_folder_is_warned_with_the_move_that_numbers_it(tmp_path: Path):
    assert crud.create_milestone(load(tmp_path), "mvp", "MVP").ok
    for slug in ("beta", "gamma"):
        folder = tmp_path / "docs/milestones" / slug
        folder.mkdir(parents=True)
        (folder / "milestone.md").write_text(
            f"---\ntype: milestone\ntitle: {slug}\nstatus: proposed\n---\n# {slug}\n", encoding="utf-8")

    found = [f for f in doctor.run(load(tmp_path)).findings if f.code == "milestone-folder-unnumbered"]

    assert [(f.severity, f.suggestion) for f in found] == [
        ("warn", "git mv docs/milestones/beta docs/milestones/0002-beta"),
        ("warn", "git mv docs/milestones/gamma docs/milestones/0003-gamma"),
    ]


def test_setting_the_epics_again_leaves_one_blank_line_before_the_next_heading(tmp_path: Path):
    accounts_id, profiles_id, path = _two_epics_and_a_milestone(tmp_path)

    assert crud.set_milestone_epics(load(tmp_path), "mvp", [accounts_id, profiles_id]).ok
    first = path.read_text(encoding="utf-8")
    assert crud.set_milestone_epics(load(tmp_path), "mvp").ok

    assert path.read_text(encoding="utf-8") == first
    assert f"2. Profiles (`{profiles_id}`)\n\n## " in first
