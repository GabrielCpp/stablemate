from __future__ import annotations

import os
from pathlib import Path

import pytest
from ostler import crud, doctor, layout, markdown, todo
from ostler.model import load

from conftest import present

pytestmark = pytest.mark.usefixtures("minting_root")


def _shelf() -> Path:
    return Path(os.environ["STABLEMATE_ARTIFACTS_DIR"]).resolve()


def test_an_epic_and_its_story_live_in_folders_named_by_their_ids(tmp_path: Path):
    epic = crud.create_epic(load(tmp_path), "accounts", "Accounts")
    story = crud.create_story(load(tmp_path), "accounts", "sign-in", "Sign in")

    assert epic.ok and story.ok
    epic_md = _shelf() / "epics" / epic.entity_id / "epic.md"
    assert (markdown.split(epic_md.read_text(encoding="utf-8")).frontmatter or {})["slug"] == "accounts"
    assert (epic_md.parent / "stories" / story.entity_id / "story.md").is_file()
    found = present(load(tmp_path).epic_by_ref("accounts"))
    assert (found.name, found.slug) == (epic.entity_id, "accounts")
    assert present(found.stories[0].story_md).parent.name == story.entity_id


def test_a_second_epic_with_the_same_slug_is_refused(tmp_path: Path):
    assert crud.create_epic(load(tmp_path), "accounts", "Accounts").ok

    again = crud.create_epic(load(tmp_path), "accounts", "Accounts again")

    assert not again.ok and "already exists" in again.message


def _numbered_shelf(root: Path) -> tuple[str, str]:
    """A shelf in the old layout: the epic in `0001-accounts`, its story in `stories/sign-in`."""
    epic = crud.create_epic(load(root), "accounts", "Accounts")
    story = crud.create_story(load(root), "accounts", "sign-in", "Sign in")
    assert todo.add(load(root), "accounts").ok
    epics = _shelf() / "epics"
    (epics / epic.entity_id / "stories" / story.entity_id).rename(
        epics / epic.entity_id / "stories" / "sign-in")
    epic_md = epics / epic.entity_id / "epic.md"
    epic_md.write_text(epic_md.read_text(encoding="utf-8").replace("slug: accounts\n", ""),
                       encoding="utf-8")
    (epics / epic.entity_id).rename(epics / "0001-accounts")
    (epics / "index.md").write_text(
        "# Epics\n\n- [accounts](accounts/epic.md) — Accounts\n", encoding="utf-8")
    return epic.entity_id, story.entity_id


def test_a_numbered_shelf_refuses_until_layout_apply_names_every_folder_by_its_id(tmp_path: Path):
    epic_id, story_id = _numbered_shelf(tmp_path)

    with pytest.raises(layout.LayoutMoveRequired, match="ostler layout apply"):
        load(tmp_path)

    done, refused = layout.apply(_shelf())

    assert refused == []
    assert "0001-accounts -> " + epic_id in done
    epics = _shelf() / "epics"
    assert (epics / epic_id / "stories" / story_id / "story.md").is_file()
    assert "[" + epic_id + "](" + epic_id + "/epic.md)" in (epics / "index.md").read_text(encoding="utf-8")
    graph = load(tmp_path)
    assert present(graph.epic_by_ref("accounts")).name == epic_id
    codes = {f.code for f in doctor.run(graph).findings}
    assert not codes & {"epic-folder-not-id", "story-folder-not-id"}
    assert layout.apply(_shelf()) == ([], [])


def test_a_story_folder_named_by_its_slug_is_a_finding(tmp_path: Path):
    epic = crud.create_epic(load(tmp_path), "accounts", "Accounts")
    story = crud.create_story(load(tmp_path), "accounts", "sign-in", "Sign in")
    stories = _shelf() / "epics" / epic.entity_id / "stories"
    (stories / story.entity_id).rename(stories / "sign-in")

    codes = {f.code for f in doctor.run(load(tmp_path)).findings}

    assert "story-folder-not-id" in codes
