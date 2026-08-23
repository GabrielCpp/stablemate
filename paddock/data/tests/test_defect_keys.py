"""The answer keys, checked the way the harness checks them.

`_frozenapp.validate_defects` is what `plan_round` runs before a trial costs anything; this
file runs it over every frozen app in the tree so a key that rots fails here first, and pins
the negative cases the fixtures themselves cannot pose.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from _fixtures import APPS, DATA, load_task

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
