"""The answer keys, checked the way the harness checks them.

`_frozenapp.validate_defects` is what `plan_round` runs before a trial costs anything; this
file runs it over every frozen app in the tree so a key that rots fails here first, and pins
the negative cases the fixtures themselves cannot pose.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from _fixtures import APPS, APPS_DIR, DATA, load_task

frozen = load_task("_frozenapp_keys", DATA / "tasks" / "_frozenapp.py")


@pytest.mark.parametrize("app", APPS, ids=[app.name for app in APPS])
def test_every_answer_key_validates(app: Path) -> None:
    """Every row's path is in its story's diff, every variant exists, every route is known —
    the check the harness makes at plan time, made here so a key cannot rot between rounds."""
    assert frozen.validate_defects(app) == []


def _write_app(root: Path, *, path: str, story_diff: dict[str, list[str]]) -> Path:
    app = root / "app"
    (app / "stories" / "s1").mkdir(parents=True)
    (app / "stories" / "s1" / "diff.yml").write_text(yaml.safe_dump(story_diff), encoding="utf-8")
    (app / "defects" / "X1").mkdir(parents=True)
    (app / "defects" / "X1" / "a.py").write_text("broken\n", encoding="utf-8")
    (app / "defects.yml").write_text(
        yaml.safe_dump({"defects": [{
            "id": "X1", "story": "s1", "path": path, "obligation": "okf:a#b:c",
            "expect": "contradicted", "caught_by": "run", "why": "x",
        }]}),
        encoding="utf-8",
    )
    return app


def test_a_defect_outside_its_story_diff_is_refused_before_any_trial(tmp_path: Path) -> None:
    """Outside the diff the path is committed in the before tree: the defect is real, present
    and out of scope, and the row scores a miss against QA for a fixture bug."""
    app = _write_app(tmp_path, path="a.py", story_diff={"changed": ["b.py"], "added": []})
    problems = frozen.validate_defects(app)
    assert len(problems) == 1 and "X1: a.py is not in s1's diff" in problems[0]
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "a.py").write_text("fine\n", encoding="utf-8")
    with pytest.raises(frozen.TrialError, match="not in s1's diff"):
        frozen.seed_defect(app, frozen.load_defects(app)[0], repo)
    assert (repo / "a.py").read_text(encoding="utf-8") == "fine\n"


def test_an_unknown_story_and_a_missing_variant_are_named(tmp_path: Path) -> None:
    app = _write_app(tmp_path, path="a.py", story_diff={"changed": ["a.py"], "added": []})
    assert frozen.validate_defects(app) == []
    (app / "defects" / "X1" / "a.py").unlink()
    assert any("no variant at" in p for p in frozen.validate_defects(app))
    key = yaml.safe_load((app / "defects.yml").read_text(encoding="utf-8"))
    key["defects"][0]["story"] = "s9"
    (app / "defects.yml").write_text(yaml.safe_dump(key), encoding="utf-8")
    assert frozen.validate_defects(app) == ["X1: story 's9' is not one of s1"]


# ── story manifests ───────────────────────────────────────────────────────────────────

ALL_STORIES = [
    pytest.param(app, story.name, id=f"{app.name}/{story.name}")
    for app in sorted(APPS_DIR.iterdir())
    if (app / "stories").is_dir()
    for story in sorted((app / "stories").iterdir())
    if (story / "diff.yml").is_file()
]


@pytest.mark.parametrize(("app", "story"), ALL_STORIES)
def test_every_story_manifest_is_well_formed(app: Path, story: str) -> None:
    """Each path in exactly one of `changed:`/`added:`/`pinned:`, every image the lists
    promise present, every path the app tree holds (a pinned path too — it is the finished
    image the pin overrides, and materialize copies the tree first)."""
    diff = frozen.story_diff(app, story)
    listed = [rel for kind in frozen.DIFF_KINDS for rel in diff[kind]]
    assert len(listed) == len(set(listed)), f"{app.name}/{story}: a path is listed twice"
    for rel in listed:
        assert (app / rel).is_file(), f"{app.name}/{story}: {rel} is not in the app tree"
    for rel in diff["changed"]:
        frozen.story_image(app, story, rel, phase="pre")
    for rel in diff["pinned"]:
        frozen.story_image(app, story, rel, phase="pinned")


def test_a_path_in_two_lists_is_refused(tmp_path: Path) -> None:
    app = _write_app(
        tmp_path / "two-lists",
        path="a.py",
        story_diff={"changed": ["a.py"], "added": [], "pinned": ["a.py"]},
    )
    with pytest.raises(frozen.TrialError, match="listed under both changed: and pinned:"):
        frozen.story_diff(app, "s1")


def test_a_pinned_path_without_an_image_is_refused(tmp_path: Path) -> None:
    app = _write_app(
        tmp_path / "no-pin",
        path="a.py",
        story_diff={"changed": ["a.py"], "added": [], "pinned": ["b.py"]},
    )
    with pytest.raises(frozen.TrialError, match="pins b.py but has no pinned/ image"):
        frozen.story_image(app, "s1", "b.py", phase="pinned")
