"""Integrity tests for the frozen `policy-desk` app.

Same job as `test_seat_booking_app.py`, and for the same reason: the fixture is what QA is
*scored against*, so rot in it moves the number instead of failing. The three rot classes
covered there are covered here — a book that stops being clean, a manifest that stops
matching the tree, a materialization that stops producing a worktree diff.

Two more matter for this app in particular, and both come from how the obligation packet is
built rather than from how the app is written:

* **Every answer-key row has to name an obligation the trial is *required* to evidence.**
  `build_evidence_map` reports only owed obligations, so a row pointed at a context-only id
  can never score anything but `inconclusive`. Owedness is not a property of the book alone:
  a `file-owner` citation is demoted the moment a second node cites the same file, which
  means an ordinary refactor in the app — extracting a component, merging two handlers —
  silently unscores a defect. Nothing else in the suite would notice.
* **Every variant has to differ from the file the story would otherwise ship**, and to
  differ in a way that still builds. A variant that does not compile is caught by any check
  at all; a variant identical to the app is caught by none, and both look like a score.

The build half is toolchain-gated: `go` for the API variants, `npm` for the client ones.
Where the toolchain is absent the check skips *naming what is missing*, because the
enforcing gate is the compose image the trial builds — this test is the early warning, not
the authority.
"""

from __future__ import annotations

import contextlib
import importlib.util
import os
import shutil
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType

import pytest
from paddock.registry import REGISTRY
import yaml

DATA = Path(__file__).parents[1]
APP = DATA / "apps" / "policy-desk"

@contextlib.contextmanager
def _tasks_dir_on_path() -> Iterator[None]:
    """Stand in for the interpreter, exactly as `paddock.loader` does when it loads a task."""
    saved = sys.path[:]
    sys.path.insert(0, str(DATA / "tasks"))
    try:
        yield
    finally:
        sys.path[:] = saved


def _load(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None  # noqa: S101 - a real file on disk
    module = importlib.util.module_from_spec(spec)
    # The registry is module-global and a task module declares into it at import: reset it
    # around the load, exactly as `paddock.loader` does, or the second task loaded in this
    # process refuses on a name the first one claimed.
    REGISTRY.reset()
    with _tasks_dir_on_path():
        sys.modules[name] = module
        spec.loader.exec_module(module)
    REGISTRY.reset()
    return module


frozen = _load("_frozenapp", DATA / "tasks" / "_frozenapp.py")
TASK = _load("_task_under_test", DATA / "tasks" / "policy_desk_qa.py")

#: Replay order, which is also dependency order: nothing can be listed or amended until a
#: policy can be put on file. The pre/post chain below is asserted in this order.
STORIES = ("create-policy", "policy-list", "edit-policy")


def manifest(story: str) -> dict[str, list[str]]:
    data = yaml.safe_load((APP / "stories" / story / "diff.yml").read_text(encoding="utf-8"))
    return {"changed": list(data.get("changed") or []), "added": list(data.get("added") or [])}


def defects() -> list[dict[str, str]]:
    data = yaml.safe_load((APP / "defects.yml").read_text(encoding="utf-8"))
    return list(data["defects"])


def defect_ids() -> list[str]:
    return [row["id"] for row in defects()]


# ── the book ──────────────────────────────────────────────────────────────────────────


def test_doctor_is_clean() -> None:
    """0 errors and 0 warnings — `undeclared-obligation` and `compound-normative-bullet`
    are warnings, and both describe a book that cannot be used as an answer key."""
    from ostler.api import Ostler  # noqa: PLC0415 - a heavy import only this test needs

    report = Ostler(APP).doctor().data
    assert report["errors"] == 0, report["findings"]
    assert report["warnings"] == 0, report["findings"]


def test_the_book_is_already_canonical() -> None:
    """A non-canonical fixture buries the book diff a scored round is read from: the trial
    converges on the canonical shape on its way past, and the real change arrives inside a
    hundred lines of bullet reordering."""
    from ostler.api import Ostler  # noqa: PLC0415 - a heavy import only this test needs

    unformatted = Ostler(APP).fmt(check=True)
    assert not unformatted, f"run `ostler fmt` in {APP}: {unformatted}"


def test_the_fixture_ships_the_stories_it_claims() -> None:
    from ostler.api import Ostler  # noqa: PLC0415

    okf = Ostler(APP)
    slugs = {node.get("slug") or node.get("name") for node in okf.list("story")}
    assert set(STORIES) <= slugs


def test_the_task_points_at_the_app_and_names_the_trial_dir() -> None:
    """The declaration is now the task module's `FIXTURE`, not a `fixtures/*.yml` entry.

    Story order is no longer part of it: a round enumerates its stories from the answer key
    rather than from a hand-written list, so the fixture has no order to get wrong. What it
    still has to get right is the two paths.
    """
    assert DATA / TASK.FIXTURE.app == APP
    # farrier derives generated skill names from the basename; anything else dangles.
    assert TASK.FIXTURE.repo_dir == "policy-desk"
    assert {row["story"] for row in defects()} <= set(STORIES)


# ── the manifests ─────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("story", STORIES)
def test_every_manifest_path_exists_in_the_app(story: str) -> None:
    diff = manifest(story)
    for rel in [*diff["changed"], *diff["added"]]:
        assert (APP / rel).is_file(), f"{story}: {rel} is in diff.yml but not in the app tree"


@pytest.mark.parametrize("story", STORIES)
def test_changed_paths_have_a_pre_image_and_added_paths_do_not(story: str) -> None:
    """A `changed:` path with no `pre/` is committed at its finished content and vanishes
    from the story's diff; an `added:` path with one is committed at all."""
    diff = manifest(story)
    for rel in diff["changed"]:
        assert (APP / "stories" / story / "pre" / rel).is_file(), f"{story}: no pre/ for {rel}"
    for rel in diff["added"]:
        assert not (APP / "stories" / story / "pre" / rel).exists(), (
            f"{story}: {rel} is added but has a pre/ image"
        )


@pytest.mark.parametrize("story", STORIES)
def test_no_image_names_a_path_the_manifest_does_not(story: str) -> None:
    """A stale `pre/` or `post/` file is dead weight that reads as coverage."""
    diff = manifest(story)
    declared = {*diff["changed"], *diff["added"]}
    for phase in ("pre", "post"):
        root = APP / "stories" / story / phase
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if path.is_file():
                rel = path.relative_to(root).as_posix()
                assert rel in declared, f"{story}: {phase}/{rel} is not in diff.yml"


def test_each_story_starts_where_the_previous_one_ended() -> None:
    """A story's `pre/` image is the post-image of the last story that touched that file.

    Not story N-1's, which is the same rule only in an app where every file moves every
    story: `PolicyDetail.tsx` is written in story 1, untouched in story 2 and amended in
    story 3, so story 3 starts from story 1's content. Without this the three stories are
    unrelated snapshots rather than one history, and a trial on the last story can present
    code the earlier trials never contained — so the same defect scores differently
    depending on which story it was seeded in.

    The earlier story is required to carry an explicit `post/` image here. Its fallback is
    the app tree, and the app tree is the *last* story's content: for a file a later story
    changes, that fallback would compare a story against its own future and pass.
    """
    for index, later in enumerate(STORIES[1:], start=1):
        for rel in manifest(later)["changed"]:
            declaring = [
                story
                for story in STORIES[:index]
                if rel in {*manifest(story)["changed"], *manifest(story)["added"]}
            ]
            assert declaring, f"{later} changes {rel}, which no earlier story ships"
            earlier = declaring[-1]
            after = APP / "stories" / earlier / "post" / rel
            assert after.is_file(), f"{earlier} ships {rel} and {later} changes it: no post/"
            before = APP / "stories" / later / "pre" / rel
            assert before.read_bytes() == after.read_bytes(), (
                f"{later}/pre/{rel} is not {earlier}'s post-image"
            )


# ── materialization ───────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("story", STORIES)
def test_materialize_leaves_exactly_this_story_uncommitted(story: str, tmp_path: Path) -> None:
    dest = frozen.materialize(APP, story, tmp_path / "policy-desk")
    diff = manifest(story)

    porcelain = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=dest, capture_output=True, text=True, check=True,
    ).stdout.splitlines()
    dirty = {line[3:]: line[:2].strip() for line in porcelain}

    assert set(dirty) == {*diff["changed"], *diff["added"]}
    for rel in diff["changed"]:
        assert dirty[rel] == "M"
    for rel in diff["added"]:
        assert dirty[rel] == "??"


@pytest.mark.parametrize("story", STORIES)
def test_materialize_puts_this_story_content_in_the_worktree(story: str, tmp_path: Path) -> None:
    """The worktree holds the story's *post* image — the app tree only for the last story."""
    dest = frozen.materialize(APP, story, tmp_path / "policy-desk")
    for rel in [*manifest(story)["changed"], *manifest(story)["added"]]:
        expected = frozen.story_image(APP, story, rel, phase="post").read_bytes()
        assert (dest / rel).read_bytes() == expected


def test_materialize_does_not_ship_the_answer_key(tmp_path: Path) -> None:
    """An agent that can read `defects.yml` is not being measured on detection, and nothing
    in its output would say so."""
    dest = frozen.materialize(APP, "policy-list", tmp_path / "policy-desk")
    for name in frozen.NOT_THE_APP:
        assert not (dest / name).exists(), f"{name} was copied into the trial tree"


@pytest.mark.parametrize("story", STORIES)
def test_materialize_keeps_every_authored_story(story: str, tmp_path: Path) -> None:
    """`stories` is excluded at the app root only — it is also what an epic calls its story
    folders, and excluding it at any depth deletes every `story.md`."""
    dest = frozen.materialize(APP, "policy-list", tmp_path / "policy-desk")
    epic = dest / "docs" / "epics" / "0001-policy-management"
    assert (epic / "epic.md").is_file()
    assert (epic / "stories" / story / "story.md").is_file()


@pytest.mark.parametrize("story", STORIES)
def test_the_obligation_packet_builds_clean_on_a_trial(story: str, tmp_path: Path) -> None:
    """Every story's QA context builds with no error-severity health finding.

    This is what a trial does first, and an `unmapped-change` there is not a warning the run
    walks past: the QA lane sends the packet to a repair agent, which edits the frozen book
    before a scenario runs. The control then measures a fixture nobody authored, and the
    minutes and tokens the repair spent land in the score as QA's. It only reproduces on a
    materialized worktree — `doctor` is clean either way, because the finding is about the
    story's diff and not about the book on its own — which is why it is checked here rather
    than left to the round to discover.
    """
    from ostler.api import Ostler  # noqa: PLC0415 - a heavy import only this test needs

    dest = frozen.materialize(APP, story, tmp_path / "policy-desk")
    outcome = Ostler(dest).qa_context(base="HEAD", spec=dest / "docs" / "specs" / story)
    errors = [
        finding for finding in outcome.data.get("healthFindings", [])
        if finding.get("severity") == "error"
    ]
    assert not errors, errors
    assert outcome.ok, outcome.data.get("status")


def test_materialized_book_is_unchanged(tmp_path: Path) -> None:
    """The book sits at its authored state on both sides of HEAD, so QA cannot read the
    obligations as part of the work under review."""
    dest = frozen.materialize(APP, "edit-policy", tmp_path / "policy-desk")
    changed_docs = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all", "--", "docs"],
        cwd=dest, capture_output=True, text=True, check=True,
    ).stdout
    assert changed_docs == ""


# ── the answer key ────────────────────────────────────────────────────────────────────


def test_the_answer_key_names_its_defects_once() -> None:
    ids = defect_ids()
    assert len(ids) == len(set(ids)), ids
    assert set(ids) == {path.name for path in (APP / "defects").iterdir() if path.is_dir()}


@pytest.mark.parametrize("row", defects(), ids=defect_ids())
def test_every_defect_variant_exists_on_both_sides(row: dict[str, str]) -> None:
    """A variant with no counterpart in the app overwrites nothing the story implements; an
    app path with no variant is a row that applies nothing at all."""
    assert (APP / "defects" / row["id"] / row["path"]).is_file()
    assert (APP / row["path"]).is_file()


@pytest.mark.parametrize("row", defects(), ids=defect_ids())
def test_every_defect_lands_in_its_story(row: dict[str, str]) -> None:
    """A defect in a file outside `diff.yml` is committed as part of the *before* tree:
    real, present, and out of scope, which scores as a miss against QA for a fixture bug."""
    diff = manifest(row["story"])
    assert row["path"] in {*diff["changed"], *diff["added"]}, (
        f"{row['id']}: {row['path']} is not in {row['story']}'s diff"
    )


@pytest.mark.parametrize("row", defects(), ids=defect_ids())
def test_every_defect_actually_changes_the_story_image(row: dict[str, str]) -> None:
    """The variant must differ from the file the story would otherwise ship.

    Whole-file overwrite is what makes an identical variant dangerous rather than merely
    useless: nothing errors, the trial runs, the defect is simply not there, and the row
    scores as a catch QA never earned.
    """
    correct = frozen.story_image(APP, row["story"], row["path"], phase="post").read_bytes()
    assert (APP / "defects" / row["id"] / row["path"]).read_bytes() != correct


@pytest.mark.parametrize("row", defects(), ids=defect_ids())
def test_every_defect_declares_a_route_and_an_expectation(row: dict[str, str]) -> None:
    assert row["expect"] == "contradicted"
    assert row["caught_by"] in {"run", "audit"}
    assert row["why"].strip()


@pytest.mark.parametrize("row", defects(), ids=defect_ids())
def test_seeding_a_defect_stays_inside_the_story_diff(row: dict[str, str], tmp_path: Path) -> None:
    """A variant that lands anywhere else is a second, undocumented defect — and a trial
    carrying two of them scores one as a catch whichever one QA found."""
    def tree(root: Path) -> dict[Path, bytes]:
        return {
            path: path.read_bytes()
            for path in sorted(root.rglob("*"))
            if path.is_file() and ".git" not in path.relative_to(root).parts
        }

    dest = frozen.materialize(APP, row["story"], tmp_path / "policy-desk")
    before = tree(dest)
    frozen.seed_defect(APP, row, dest)
    after = tree(dest)

    assert set(after) == set(before)
    assert [p for p in after if after[p] != before[p]] == [dest / row["path"]]


# ── owedness: the property that makes a row scorable at all ───────────────────────────


@pytest.fixture(scope="module")
def owed_obligations(tmp_path_factory: pytest.TempPathFactory) -> dict[str, set[str]]:
    """The ids each story's trial is *required* to evidence, minted the way QA mints them.

    Not the graph's whole vocabulary: `build_context` against the materialized worktree is
    the same call the coder's QA lane makes, and its `required` flag is the thing this file
    exists to pin. Minted once per story and shared, because it is the slowest check here.
    """
    from ostler.qa.context import build_context  # noqa: PLC0415 - heavy, and only for this

    root = tmp_path_factory.mktemp("owed")
    packets: dict[str, set[str]] = {}
    for story in STORIES:
        dest = frozen.materialize(APP, story, root / story / "policy-desk")
        context = build_context(dest, base="HEAD", head="WORKTREE")
        packets[story] = {
            obligation["id"]
            for obligation in context["obligations"]
            if obligation.get("required", True)
        }
    return packets


@pytest.mark.parametrize("row", defects(), ids=defect_ids())
def test_every_defect_obligation_is_owed_by_its_story(
    row: dict[str, str], owed_obligations: dict[str, set[str]]
) -> None:
    """The row's obligation must be one this story's trial owes, not merely one the book
    mints.

    `build_evidence_map` scores `[o for o in scope if o.get("required", True)]` and nothing
    else, so an obligation that is present-but-context-only returns `inconclusive` with
    "obligation not owed by this trial" — a row that can never be a catch or a miss.

    The way this breaks is a refactor, not an edit to the answer key: a `file-owner`
    citation is demoted as soon as a second OKF node cites the same file, so merging two
    components into one file quietly unscores every defect seeded in either.
    """
    owed = owed_obligations[row["story"]]
    assert row["obligation"] in owed, (
        f"{row['id']}: {row['obligation']} is not owed by {row['story']} "
        f"({len(owed)} owed obligations); a shared source file demotes it to context-only"
    )


# ── the variants build ────────────────────────────────────────────────────────────────


def _variants(suffix: str) -> list[dict[str, str]]:
    return [row for row in defects() if row["path"].endswith(suffix)]


def _variant_ids(suffix: str) -> list[str]:
    return [row["id"] for row in _variants(suffix)]


@pytest.mark.parametrize("row", _variants(".go"), ids=_variant_ids(".go"))
def test_every_go_variant_compiles(row: dict[str, str], tmp_path: Path) -> None:
    """A variant that does not build is caught by every check there is and measures nothing.

    Skipped without a Go toolchain rather than assumed: the enforcing gate is the image the
    trial builds from `compose.yml`, and this is the early warning that runs in CI.
    """
    if shutil.which("go") is None:
        pytest.skip("no `go` on PATH; the compose image build is the enforcing gate")

    api = tmp_path / "api"
    shutil.copytree(APP / "app" / "api", api)
    shutil.copyfile(APP / "defects" / row["id"] / row["path"], api / Path(row["path"]).name)

    built = subprocess.run(
        ["go", "build", "./..."],
        cwd=api, capture_output=True, text=True,
        env={**os.environ, "GOFLAGS": "-mod=mod", "GOCACHE": str(tmp_path / "gocache")},
        check=False,
    )
    assert built.returncode == 0, built.stderr


@pytest.fixture(scope="module")
def typecheckable_web(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A copy of the client with its dependencies installed, ready to swap a file into.

    The install cannot live in the fixture tree: `node_modules` in a frozen app would be
    materialized into every trial and committed into its before-tree. So it is built once,
    outside, and each variant is checked by overwriting one file in `src/`.
    """
    if shutil.which("npm") is None:
        pytest.skip("no `npm` on PATH; the compose image build is the enforcing gate")

    web = tmp_path_factory.mktemp("web") / "web"
    shutil.copytree(APP / "app" / "web", web)
    installed = subprocess.run(
        ["npm", "ci", "--no-audit", "--no-fund"],
        cwd=web, capture_output=True, text=True, check=False,
    )
    if installed.returncode != 0:
        pytest.skip(f"`npm ci` unavailable here: {installed.stderr.strip()[-200:]}")
    return web


@pytest.mark.parametrize("row", _variants(".tsx"), ids=_variant_ids(".tsx"))
def test_every_client_variant_typechecks(row: dict[str, str], typecheckable_web: Path) -> None:
    """Same bar as the Go variants, through the check the client's own `build` script runs."""
    target = typecheckable_web / "src" / Path(row["path"]).name
    original = target.read_bytes()
    try:
        shutil.copyfile(APP / "defects" / row["id"] / row["path"], target)
        checked = subprocess.run(
            ["npx", "tsc", "--noEmit"],
            cwd=typecheckable_web, capture_output=True, text=True, check=False,
        )
        assert checked.returncode == 0, checked.stdout + checked.stderr
    finally:
        target.write_bytes(original)
