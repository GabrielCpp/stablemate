"""A story's id is an opaque string: a tracker key written by hand works wherever a ULID does."""

from __future__ import annotations

from pathlib import Path

from ostler import doctor, ids, path as path_mod
from ostler.model import load

from conftest import epic_md, present, story_md, write, epics_root

KEY = "CASE-574"
EPIC = "CASE-457"


def _tracker_repo(root: Path) -> Path:
    write(epics_root() / f"{EPIC}/epic.md", epic_md(
        EPIC, "Case epic", seeds=[], stories=[(KEY, "Case story", [])],
    ))
    write(epics_root() / f"{EPIC}/stories/{KEY}/story.md",
          story_md(KEY, "Case story", "Not started", eid=KEY))
    return root


def test_a_tracker_key_id_is_found_as_the_story_it_names(tmp_path: Path):
    graph = load(_tracker_repo(tmp_path))
    found = present(graph.find_story(KEY))
    assert found[1].eid == KEY


def test_a_tracker_key_id_resolves_to_its_own_spec_directory(tmp_path: Path):
    graph = load(_tracker_repo(tmp_path))
    assert path_mod.resolve_spec(graph, KEY).endswith(f"/specs/{KEY}")


def test_an_epic_named_by_a_tracker_key_resolves_without_a_numeric_prefix(tmp_path: Path):
    graph = load(_tracker_repo(tmp_path))
    assert path_mod.resolve_epic(graph, EPIC) == str(epics_root() / EPIC)


def test_a_tracker_key_id_is_never_rewritten_by_the_handle_table(tmp_path: Path):
    graph = load(_tracker_repo(tmp_path))
    handles = ids.table(ids.known(graph))
    assert handles[KEY] == KEY


def test_shortening_text_leaves_a_tracker_key_id_unchanged(tmp_path: Path):
    graph = load(_tracker_repo(tmp_path))
    handles = ids.table(ids.known(graph))
    assert ids.shorten(f"Story: {KEY}", handles) == f"Story: {KEY}"


def test_a_tracker_key_id_names_its_own_branch(tmp_path: Path):
    assert path_mod.resolve_branch(load(_tracker_repo(tmp_path)), KEY) == KEY


def test_doctor_raises_no_finding_about_a_tracker_key_id_slug_or_epic(tmp_path: Path):
    report = doctor.run(load(_tracker_repo(tmp_path)))
    mentioning = [f for f in report.findings
                  if any(name in f.message for name in (KEY, EPIC))]
    assert mentioning == []
