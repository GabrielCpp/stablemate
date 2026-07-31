"""Epic directories carry their creation order — `0001-<slug>` — and the slug still names them.

Two facts are pinned here, and they are in tension by design:

* **The number is minted once, by ostler.** `create_epic` is the only writer of the prefix, so a
  listing of `docs/epics` reads as the order the work was decomposed in rather than as an
  alphabetized set. Nobody else invents one.
* **The number is not an identity.** Identity is the ostler-minted id, which never changes. So
  every entry point that takes an epic *name* accepts the bare slug too: epics created before the
  numbering, hand-written `index.md` lines, and the many prompts that only ever knew the slug all
  keep working. A name that already carries a number is taken literally, so a typo is reported
  rather than silently re-pointed at a neighbour.
"""

from __future__ import annotations

from pathlib import Path

from ostler import crud, doctor, path as path_mod, query, registry, select, todo
from ostler.model import load

from conftest import write


def _create(root: Path, name: str, title: str = "T") -> str:
    return crud.create_epic(load(root), name, title, prefix="x").entity_name


def test_directories_are_numbered_in_creation_order(tmp_path: Path):
    assert _create(tmp_path, "first") == "0001-first"
    assert _create(tmp_path, "second") == "0002-second"
    assert sorted(d.name for d in path_mod.epic_dirs(load(tmp_path))) == \
        ["0001-first", "0002-second"]


def test_a_name_that_already_carries_a_number_is_taken_literally(tmp_path: Path):
    """Re-importing an epic must land on the number it came with, not be renumbered."""
    assert _create(tmp_path, "0007-imported") == "0007-imported"
    # And the next mint continues past it rather than colliding with it.
    assert _create(tmp_path, "next") == "0008-next"


def test_a_gap_in_the_middle_never_renumbers_its_survivors(tmp_path: Path):
    """The sequence is derived from what is on disk, so deleting the *last* epic frees its
    number — harmless, since the number is a rank and not an identity. What must never happen
    is the other repair: shifting `0003-` down to close a gap, which would invalidate every
    path already written into a plan, a branch or a link."""
    _create(tmp_path, "a")
    _create(tmp_path, "b")
    _create(tmp_path, "c")
    assert crud.delete_epic(load(tmp_path), "b").ok
    assert [d.name for d in path_mod.epic_dirs(load(tmp_path))] == ["0001-a", "0003-c"]
    assert _create(tmp_path, "d") == "0004-d"


def test_creating_the_same_slug_twice_is_refused(tmp_path: Path):
    """Not "already exists" by directory name — `checkout` and `0001-checkout` are one epic, and
    creating the slug again would otherwise scaffold a second folder over the same work."""
    _create(tmp_path, "checkout")
    res = crud.create_epic(load(tmp_path), "checkout", "Again", prefix="x")
    assert not res.ok and "already exists" in res.message
    assert len(path_mod.epic_dirs(load(tmp_path))) == 1


def test_every_entry_point_takes_the_bare_slug(tmp_path: Path):
    dir_name = _create(tmp_path, "checkout", "Checkout")

    g = load(tmp_path)
    assert path_mod.epic_dir(g, "checkout").name == dir_name
    assert path_mod.resolve_epic(g, "checkout") == f"docs/epics/{dir_name}"
    assert path_mod.resolve_story(g, "checkout", "01-a") == \
        f"docs/epics/{dir_name}/stories/01-a/story.md"

    assert crud.add_seed(load(tmp_path), "checkout", "s1", summary="a seed").ok
    assert crud.create_story(load(tmp_path), "checkout", "01-a", "A", covers=["s1"]).ok

    g = load(tmp_path)
    found = select.epic_by_name(g, "checkout")
    assert found is not None and found.name == dir_name
    assert [r["id"] for r in query.list_entities(g, "seed", epic="checkout")] == ["s1"]
    assert [r["slug"] for r in query.list_entities(g, "story", epic="checkout")] == ["01-a"]
    assert [f.ref for f in doctor.run(g, epic_filter="checkout").findings
            if f.code == "unwritten-story"] == ["01-a"]

    assert crud.remove_seed(load(tmp_path), "checkout", "s1").ok
    assert crud.delete_epic(load(tmp_path), "checkout").ok


def test_a_wrong_number_is_reported_rather_than_resolved(tmp_path: Path):
    """`0009-checkout` is not `0001-checkout`. Repointing it would turn a typo into a silent
    write against the wrong epic — the one failure mode the slug tolerance must not create."""
    _create(tmp_path, "checkout")
    res = crud.create_story(load(tmp_path), "0009-checkout", "01-a", "A")
    assert not res.ok and "0009-checkout" in res.message


def test_an_unnumbered_epic_on_disk_still_resolves(tmp_path: Path):
    """Epics that predate the numbering are left where they are — nothing renames them, and a
    caller naming one gets its real directory back."""
    write(tmp_path / "docs/epics/legacy/epic.md",
          "---\ntype: epic\nid: x-1\ntitle: Legacy\n---\n# Epic: Legacy\n\n## Stories\n")
    g = load(tmp_path)
    assert path_mod.epic_dir(g, "legacy").name == "legacy"
    found = select.epic_by_name(g, "legacy")
    assert found is not None and found.name == "legacy"
    # And the next created epic starts the sequence, unaffected by the unnumbered neighbour.
    assert _create(tmp_path, "modern") == "0001-modern"


def test_the_queue_tolerates_either_name(tmp_path: Path):
    _create(tmp_path, "one")
    _create(tmp_path, "two")
    # A hand-written queue line may carry the bare slug; it names the same epic.
    write(tmp_path / "docs/epics/index.md", "# Epics\n\n- [one](one/epic.md) — One\n")
    assert todo.list_epics(load(tmp_path)) == ["one"]
    assert not todo.add(load(tmp_path), "0001-one").ok, "already queued, under its other name"
    assert todo.add(load(tmp_path), "two").ok
    assert todo.reorder(load(tmp_path), ["0002-two", "one"]).ok
    assert todo.list_epics(load(tmp_path)) == ["0002-two", "one"]
    assert todo.prune(load(tmp_path), "one").ok
    assert todo.list_epics(load(tmp_path)) == ["0002-two"]


def test_registry_helpers_do_not_read_a_short_number_as_a_prefix(tmp_path: Path):
    """`3d-preview` is a slug, not epic number three: the prefix is four digits minimum."""
    assert registry.epic_seq("3d-preview") is None
    assert registry.epic_slug("3d-preview") == "3d-preview"
    assert registry.epic_seq("0012-billing") == 12
    assert registry.epic_slug("0012-billing") == "billing"
    assert registry.epic_dir_name(12, "billing") == "0012-billing"
    assert registry.next_epic_seq(["0001-a", "legacy", "0004-b"]) == 5
    assert registry.next_epic_seq([]) == 1
