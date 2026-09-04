"""Integrity tests for the frozen `claims-api` app.

Same job as `test_policy_desk_app.py`, against a fixture with no screen in it at all. The
rot classes are the ones every frozen app has — a book that stops being clean, a manifest
that stops matching the tree, a materialization that stops producing a worktree diff, an
answer-key row whose obligation is no longer owed, a variant that stops differing or stops
building — and two things about this app change how they present:

* **Its three stories are pure additions.** Every path in every `diff.yml` is `added:`, so
  there is no `pre/`/`post/` chain to walk and the app tree is each story's post-image. The
  chain tests below still run and are deliberately kept rather than deleted: the moment a
  fourth story amends a file the earlier ones shipped, they are the only thing that notices.
* **Protection is not hand-wired per route.** `oapi-codegen`'s chi wrapper stamps
  `BearerAuthScopes` into the request context for exactly the operations `openapi.yml`
  secures, so the obligations C1/C2 sit on are owed through the generated layer. That layer
  is committed, and `test_the_generated_layer_is_committed` is why: a fixture that
  regenerates at trial time measures the generator's availability instead of QA.

This file is also, for now, the only thing that checks the answer key's obligation ids at
all. `ostler qa validate` binds a plan's `covers=` ids only inside a materialized trial, and
these nine ids were minted by hand — so `test_every_defect_obligation_is_owed_by_its_story`
below is the one gate between a typo and a row that scores `inconclusive` forever.

The build half is toolchain-gated on `go`. Where it is absent the check skips *naming what
is missing*, because the enforcing gate is the compose image the trial builds — this test is
the early warning, not the authority.
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
APP = DATA / "apps" / "claims-api"


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
TASK = _load("_claims_api_task", DATA / "tasks" / "claims_api_qa.py")

#: Replay order, which is also dependency order: nothing can be scoped or adjudicated until
#: a claim can be filed.
STORIES = ("claims-crud", "claims-tenancy", "claims-adjudication")

EPIC = "0001-claims-desk"


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
    """A non-canonical fixture buries the book diff a scored round is read from."""
    from ostler.api import Ostler  # noqa: PLC0415 - a heavy import only this test needs

    unformatted = Ostler(APP).fmt(check=True)
    assert not unformatted, f"run `ostler fmt` in {APP}: {unformatted}"


def test_the_book_has_no_screen_in_it() -> None:
    """The premise of the whole fixture, pinned so a later edit cannot quietly dilute it.

    `claims-api` exists to ask what the leverage keys read when there is nothing to open:
    `entry` and `deep_links` are supposed to come back blank because the book never claims a
    surface a browser could reach. A `gui/` node added here would still be a perfectly good
    OKF node, and it would silently turn this fixture into a second `policy-desk`.

    The other four contexts are the book's own — concepts, flows, ops and the `http/` server
    node — and they are what makes the blank interesting rather than empty: this is a fully
    grounded book that simply has no screen in it.
    """
    features = APP / "docs" / "features"
    contexts = {path.parent.name for path in features.rglob("*.md")}
    assert "http" in contexts
    assert not contexts & {"gui", "screens", "mobile"}, sorted(contexts)


def test_the_fixture_ships_the_stories_it_claims() -> None:
    from ostler.api import Ostler  # noqa: PLC0415

    okf = Ostler(APP)
    slugs = {node.get("slug") or node.get("name") for node in okf.list("story")}
    assert set(STORIES) <= slugs


def test_the_task_points_at_the_app_and_names_the_trial_dir() -> None:
    assert DATA / TASK.FIXTURE.app == APP
    # farrier derives generated skill names from the basename; anything else dangles.
    assert TASK.FIXTURE.repo_dir == "claims-api"
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


def test_no_story_ships_a_path_another_story_already_shipped() -> None:
    """Every path in this app belongs to exactly one story.

    That is what makes the app tree each story's post-image and lets all three stories ship
    with no `post/` directory at all. It is an invariant of *this* fixture rather than of
    frozen apps generally, so it is asserted rather than assumed: a fourth story that amends
    `submit.go` has to declare it `changed:` and carry the images, and the test below is
    what turns that from a silent mis-scored trial into a failure.
    """
    seen: dict[str, str] = {}
    for story in STORIES:
        diff = manifest(story)
        for rel in [*diff["changed"], *diff["added"]]:
            assert rel not in seen, f"{story} and {seen[rel]} both ship {rel}"
            seen[rel] = story


def test_each_story_starts_where_the_previous_one_ended() -> None:
    """A story's `pre/` image is the post-image of the last story that touched that file.

    Vacuous today — this app's stories are pure additions — and kept for the story that
    breaks that. Its fallback for an earlier story's content is the app tree, which is the
    *last* story's content, so an amended file compared against that would be a story
    compared against its own future.
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


def test_the_generated_layer_is_committed() -> None:
    """`gen/` is part of the fixture, not a build product of the trial.

    The generator is pinned at its call site in `app/api/Makefile` and never runs during a
    round. If `gen/` were absent the trial would either fail to build or reach out for
    `oapi-codegen` at scoring time, and either way the number would be about the toolchain.
    """
    generated = sorted(p.name for p in (APP / "app" / "api" / "gen").glob("*.gen.go"))
    assert generated == ["server.gen.go", "types.gen.go"], generated
    makefile = (APP / "app" / "api" / "Makefile").read_text(encoding="utf-8")
    assert "oapi-codegen/v2/cmd/oapi-codegen@v" in makefile, (
        "the generator must be pinned at its call site by `@version`, with no tools.go"
    )


# ── materialization ───────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("story", STORIES)
def test_materialize_leaves_exactly_this_story_uncommitted(story: str, tmp_path: Path) -> None:
    dest = frozen.materialize(APP, story, tmp_path / "claims-api")
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
    dest = frozen.materialize(APP, story, tmp_path / "claims-api")
    for rel in [*manifest(story)["changed"], *manifest(story)["added"]]:
        expected = frozen.story_image(APP, story, rel, phase="post").read_bytes()
        assert (dest / rel).read_bytes() == expected


def test_materialize_does_not_ship_the_answer_key(tmp_path: Path) -> None:
    """An agent that can read `defects.yml` is not being measured on detection, and nothing
    in its output would say so."""
    dest = frozen.materialize(APP, "claims-crud", tmp_path / "claims-api")
    for name in frozen.NOT_THE_APP:
        assert not (dest / name).exists(), f"{name} was copied into the trial tree"


@pytest.mark.parametrize("story", STORIES)
def test_materialize_keeps_every_authored_story(story: str, tmp_path: Path) -> None:
    """`stories` is excluded at the app root only — it is also what an epic calls its story
    folders, and excluding it at any depth deletes every `story.md`."""
    dest = frozen.materialize(APP, "claims-crud", tmp_path / "claims-api")
    epic = dest / "docs" / "epics" / EPIC
    assert (epic / "epic.md").is_file()
    assert (epic / "stories" / story / "story.md").is_file()


@pytest.mark.parametrize("story", STORIES)
def test_the_obligation_packet_builds_clean_on_a_trial(story: str, tmp_path: Path) -> None:
    """Every story's QA context builds with no error-severity health finding.

    This is what a trial does first, and an `unmapped-change` there is not a warning the run
    walks past: the QA lane sends the packet to a repair agent, which edits the frozen book
    before a scenario runs. The control then measures a fixture nobody authored, and the
    minutes and tokens the repair spent land in the score as QA's.
    """
    from ostler.api import Ostler  # noqa: PLC0415 - a heavy import only this test needs

    dest = frozen.materialize(APP, story, tmp_path / "claims-api")
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
    dest = frozen.materialize(APP, "claims-adjudication", tmp_path / "claims-api")
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

    dest = frozen.materialize(APP, row["story"], tmp_path / "claims-api")
    before = tree(dest)
    frozen.seed_defect(APP, row, dest)
    after = tree(dest)

    assert set(after) == set(before)
    assert [p for p in after if after[p] != before[p]] == [dest / row["path"]]


# ── owedness: the property that makes a row scorable at all ───────────────────────────


@pytest.fixture(scope="module")
def owed_obligations(tmp_path_factory: pytest.TempPathFactory) -> dict[str, set[str]]:
    """The ids each story's trial is *required* to evidence, minted the way QA mints them."""
    from ostler.qa.context import build_context  # noqa: PLC0415 - heavy, and only for this

    root = tmp_path_factory.mktemp("owed")
    packets: dict[str, set[str]] = {}
    for story in STORIES:
        dest = frozen.materialize(APP, story, root / story / "claims-api")
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

    For this fixture it carries a second job the others do not have: these nine ids were
    written by hand, and no other check reads them. `ostler qa validate` binds `covers=` ids
    only inside a materialized trial, so a mistyped anchor or an off-by-one bullet index
    would otherwise surface as nine months of `inconclusive` rows that look like a QA
    result.
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


@pytest.fixture(scope="module")
def gocache(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Share Go's content-addressed build cache across this module's variants."""
    return tmp_path_factory.mktemp("claims-gocache")


def test_every_variant_is_a_go_file() -> None:
    """There is no client here, so `.go` is the whole answer key — and the build gate below
    covers all of it. A `.tsx` or `.py` variant would slip past every check in this file."""
    assert _variant_ids(".go") == defect_ids()


@pytest.mark.parametrize("row", _variants(".go"), ids=_variant_ids(".go"))
def test_every_go_variant_compiles(
    row: dict[str, str], tmp_path: Path, gocache: Path
) -> None:
    """A variant that does not build is caught by every check there is and measures nothing.

    Vetted as well as built: this app's variants are behavioral rather than syntactic, and a
    `go vet` finding — an unused result, a bad format verb — is the kind of thing a reviewer
    would catch before QA ever ran, which would score the row against the wrong lane.
    """
    if shutil.which("go") is None:
        pytest.skip("no `go` on PATH; the compose image build is the enforcing gate")

    api = tmp_path / "api"
    shutil.copytree(APP / "app" / "api", api)
    shutil.copyfile(APP / "defects" / row["id"] / row["path"], api / Path(row["path"]).name)

    env = {**os.environ, "GOFLAGS": "-mod=mod", "GOCACHE": str(gocache)}
    built = subprocess.run(
        ["go", "build", "./..."],
        cwd=api, capture_output=True, text=True, env=env, check=False,
    )
    assert built.returncode == 0, built.stderr
    vetted = subprocess.run(
        ["go", "vet", "./..."],
        cwd=api, capture_output=True, text=True, env=env, check=False,
    )
    assert vetted.returncode == 0, vetted.stderr
