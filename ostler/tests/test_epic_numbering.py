"""Epic directories are named by their ids, and the slug still names them."""

from __future__ import annotations

from pathlib import Path

import pytest
from ostler import crud, doctor, path as path_mod, query, registry, select
from ostler.model import load

from conftest import present, write, epics_root

pytestmark = pytest.mark.usefixtures("minting_root")


def _create(root: Path, name: str, title: str = "T") -> str:
    return crud.create_epic(load(root), name, title).entity_name


def test_creating_the_same_slug_twice_is_refused(tmp_path: Path):
    """Not "already exists" by directory name — the folder is the id, so the slug alone says the work exists, and creating it again would otherwise scaffold a second folder over the same work."""
    _create(tmp_path, "checkout")
    res = crud.create_epic(load(tmp_path), "checkout", "Again")
    assert not res.ok and "already exists" in res.message
    assert len(path_mod.epic_dirs(load(tmp_path))) == 1


def test_every_entry_point_takes_the_bare_slug(tmp_path: Path):
    dir_name = _create(tmp_path, "checkout", "Checkout")

    g = load(tmp_path)
    assert path_mod.epic_dir(g, "checkout").name == dir_name
    assert path_mod.resolve_epic(g, "checkout") == str(epics_root() / dir_name)
    assert crud.add_seed(load(tmp_path), "checkout", "s1", summary="a seed").ok
    story_id = crud.create_story(load(tmp_path), "checkout", "01-a", "A", covers=["s1"]).entity_id
    assert path_mod.resolve_story(load(tmp_path), story_id) == \
        str(epics_root() / dir_name / "stories" / story_id / "story.md")

    g = load(tmp_path)
    found = select.epic_by_name(g, "checkout")
    assert found is not None and found.name == dir_name
    assert [r["id"] for r in query.list_entities(g, "seed", epic="checkout")] == ["s1"]
    assert [r["slug"] for r in query.list_entities(g, "story", epic="checkout")] == ["01-a"]
    assert [f.ref for f in doctor.run(g, epic_filter="checkout").findings
            if f.code == "unwritten-story"] == ["01-a"]

    assert crud.remove_seed(load(tmp_path), "checkout", "s1").ok
    assert crud.delete_epic(load(tmp_path), "checkout").ok


def test_an_epic_whose_folder_is_its_id_resolves_by_slug(tmp_path: Path):
    write(epics_root() / "x-1/epic.md",
          "---\ntype: epic\nid: x-1\nslug: legacy\ntitle: Legacy\n---\n# Epic: Legacy\n\n## Stories\n")
    g = load(tmp_path)
    assert path_mod.epic_dir(g, "legacy").name == "x-1"
    found = select.epic_by_name(g, "legacy")
    assert found is not None and found.name == "x-1"
    modern = _create(tmp_path, "modern")
    assert modern == present(load(tmp_path).epic_by_ref("modern")).eid


def test_registry_helpers_do_not_read_a_short_number_as_a_prefix(tmp_path: Path):
    """`3d-preview` is a slug, not epic number three: the prefix is four digits minimum."""
    assert registry.epic_seq("3d-preview") is None
    assert registry.epic_slug("3d-preview") == "3d-preview"
    assert registry.epic_seq("0012-billing") == 12
    assert registry.epic_slug("0012-billing") == "billing"
    assert registry.epic_dir_name(12, "billing") == "0012-billing"
    assert registry.next_epic_seq(["0001-a", "legacy", "0004-b"]) == 5
    assert registry.next_epic_seq([]) == 1
