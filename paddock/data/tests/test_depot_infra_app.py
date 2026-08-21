"""Integrity tests for the frozen `depot-infra` app.

The same rot classes as `test_claims_api_app.py` and `test_policy_desk_app.py` — a book that
stops being clean, a manifest that stops matching the tree, a materialization that stops
producing a worktree diff, an answer-key row whose obligation is no longer owed, a variant
that stops differing or stops building — against a fixture where nothing runs at all. Three
things about this app change how they present:

* **There is no product to start.** No `compose.yml`, no port, no `qa-stack.yml`: the whole
  observable behaviour of this repo is the document `pulumi preview --json` writes. So the
  premise test below is not "no screen" but "no server either", and the toolchain-gated
  extra is a preview rather than a build of a running image.
* **Every normative claim is a `consistency:` bullet on a concept node.** The `### field`
  sections an infrastructure book invites were written, parsed clean, and minted exactly
  zero obligations; they were deleted for it. `test_the_answer_key_only_names_minted_ids`
  is not what caught that — the packet is — but the owedness test below is what keeps a
  later re-introduction from silently un-owing a row.
* **Two of the app's files are shared between the two stories.** `main.go` and
  `Pulumi.dev.yaml` are `added:` in story 1 and `changed:` in story 2, so this fixture —
  unlike `claims-api` — actually exercises the pre/post chain, and the chain test is load
  bearing rather than kept for later.

The preview extra is gated on two preconditions, not one: `pulumi` on PATH *and* the pinned
gcp resource plugin resolving. A preview that reaches out for a plugin measures the network,
and one run against a different plugin measures a different provider. Where either is
missing it skips naming both, because the enforcing gate is the trial itself — this test is
the early warning.
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
APP = DATA / "apps" / "depot-infra"


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
TASK = _load("_depot_infra_task", DATA / "tasks" / "depot_infra_qa.py")

#: Replay order, which is also dependency order: the identity is granted on the bucket, so
#: there is nothing for story 2 to bind to until story 1 has declared the store.
STORIES = ("artifact-store", "deploy-identity")

EPIC = "0001-artifact-depot"

#: The provider the program pins. The preview extra refuses to run against any other one.
PINNED_PLUGIN = "8.16.0"

#: Build outputs the `pulumi/Makefile` bootstraps and `pulumi/.gitignore` ignores. They must
#: not be in the tree: `Pointer.verify_tree` re-digests the source directory with no excludes
#: at all, so a generated file living here is drift the seed can never match.
BUILD_OUTPUTS = ("pulumi/.pulumi-state", "pulumi/preview.json")


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


def test_the_book_describes_nothing_that_runs() -> None:
    """The premise of the whole fixture, pinned so a later edit cannot quietly dilute it.

    `claims-api` removed the screen; this removes the process. A `gui/` node would turn it
    into a second `policy-desk`, and an `http/` node into a second `claims-api` — either
    would give the QA lane a surface to drive, which is the one thing this fixture is for
    not having. What is left is the book's own: the depot's concepts and its ops.
    """
    features = APP / "docs" / "features"
    contexts = {path.parent.name for path in features.rglob("*.md")}
    assert contexts == {"concepts", "ops"}, sorted(contexts)
    assert not (APP / "compose.yml").exists(), "a stackless fixture may not ship a stack"
    assert not (APP / "qa-stack.yml").exists(), "this fixture exercises `ensure_stack`'s skip arm"


def test_the_fixture_ships_the_stories_it_claims() -> None:
    from ostler.api import Ostler  # noqa: PLC0415

    okf = Ostler(APP)
    slugs = {node.get("slug") or node.get("name") for node in okf.list("story")}
    assert set(STORIES) <= slugs


def test_the_task_points_at_the_app_and_names_the_trial_dir() -> None:
    assert DATA / TASK.FIXTURE.app == APP
    # farrier derives generated skill names from the basename; anything else dangles.
    assert TASK.FIXTURE.repo_dir == "depot-infra"
    assert {row["story"] for row in defects()} <= set(STORIES)


def test_the_tree_carries_no_build_output() -> None:
    """`make -C pulumi plan` writes into the app tree, and the seed digest has no excludes.

    `pulumi/Makefile` bootstraps `.pulumi-state/` and writes `preview.json`; both are
    gitignored, which is enough for git and not enough for the seed. `Pointer.verify_tree`
    calls `digest_tree(source)` with no exclude list, so either of them left here after a
    local preview makes the fixture read as drifted from a seed that is perfectly current —
    and re-capturing to silence it bakes a build output into the seed for good.
    """
    for rel in BUILD_OUTPUTS:
        assert not (APP / rel).exists(), (
            f"{rel} is a build output; delete it rather than excluding it from the seed"
        )


def test_the_dependencies_are_pinned_rather_than_vendored() -> None:
    """54 MB of `vendor/` would be the integrity story; `go.sum` is, and is much smaller."""
    assert not (APP / "pulumi" / "vendor").exists(), "never commit vendor/ — go.sum is the pin"
    assert (APP / "pulumi" / "go.sum").is_file()


def test_the_provider_version_is_pinned_in_the_program() -> None:
    """The pin D7 removes, asserted where it lives.

    A preview cannot see this — the installed plugin reports its own version either way,
    which is the entire reason D7 is `caught_by: audit`. So the fixture's own test is the
    only mechanical thing that notices the constant drifting away from the plugin the
    preview extra below insists on.
    """
    program = (APP / "pulumi" / "main.go").read_text(encoding="utf-8")
    assert f'providerVersion = "{PINNED_PLUGIN}"' in program, program
    assert "pulumi.Version(providerVersion)" in program


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


def test_the_two_shared_files_are_the_only_ones_two_stories_touch() -> None:
    """A program has one `main` and a stack has one config file, so those two are shared and
    everything else belongs to exactly one story.

    Asserted rather than assumed, because it is what decides whether the app tree is a
    story's post-image: for the seven unshared paths it is, and for these two it is not —
    story 1 carries its own `post/` images of them, and `story_image`'s app-tree fallback
    would otherwise hand story 1 story 2's content and score a diff against its own future.
    """
    owners: dict[str, list[str]] = {}
    for story in STORIES:
        diff = manifest(story)
        for rel in [*diff["changed"], *diff["added"]]:
            owners.setdefault(rel, []).append(story)
    shared = sorted(rel for rel, stories in owners.items() if len(stories) > 1)
    assert shared == ["pulumi/Pulumi.dev.yaml", "pulumi/main.go"], shared
    for rel in shared:
        assert (APP / "stories" / STORIES[0] / "post" / rel).is_file(), (
            f"{rel} is shared: story 1 needs its own post/ image of it"
        )


def test_each_story_starts_where_the_previous_one_ended() -> None:
    """A story's `pre/` image is the post-image of the last story that touched that file.

    Not vacuous here, unlike in `claims-api`: story 2 changes both shared files, and its
    `pre/` images are byte-identical duplicates of story 1's `post/` images rather than
    references to them. Duplicated content drifts silently, and in the direction that scores
    as a catch — this is the only thing that notices.
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
    dest = frozen.materialize(APP, story, tmp_path / "depot-infra")
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
    """The worktree holds the story's *post* image — the app tree only where it is the last
    story to ship that path."""
    dest = frozen.materialize(APP, story, tmp_path / "depot-infra")
    for rel in [*manifest(story)["changed"], *manifest(story)["added"]]:
        expected = frozen.story_image(APP, story, rel, phase="post").read_bytes()
        assert (dest / rel).read_bytes() == expected


def test_materialize_does_not_ship_the_answer_key(tmp_path: Path) -> None:
    """An agent that can read `defects.yml` is not being measured on detection, and nothing
    in its output would say so."""
    dest = frozen.materialize(APP, "artifact-store", tmp_path / "depot-infra")
    for name in frozen.NOT_THE_APP:
        assert not (dest / name).exists(), f"{name} was copied into the trial tree"


@pytest.mark.parametrize("story", STORIES)
def test_materialize_keeps_every_authored_story(story: str, tmp_path: Path) -> None:
    """`stories` is excluded at the app root only — it is also what an epic calls its story
    folders, and excluding it at any depth deletes every `story.md`."""
    dest = frozen.materialize(APP, "artifact-store", tmp_path / "depot-infra")
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

    dest = frozen.materialize(APP, story, tmp_path / "depot-infra")
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
    dest = frozen.materialize(APP, "deploy-identity", tmp_path / "depot-infra")
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
    real, present, and out of scope, which scores as a miss against QA for a fixture bug.

    It is worse than out of scope, too. `seed_defect` is a whole-file overwrite, so a
    variant aimed at a committed path adds a path to `HEAD..WORKTREE` that the control
    trial never had — the trial's obligation packet is then wider than the control's, and
    the two are no longer the same measurement.
    """
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

    Note which image: for the two shared paths this is the story's own `post/`, not the app
    tree. D7 overwrites `pulumi/main.go` for story 1, whose post-image is the bucket-only
    entry point — compared against the app tree (story 2's `main.go`) it would differ for
    reasons that have nothing to do with the missing pin.
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

    dest = frozen.materialize(APP, row["story"], tmp_path / "depot-infra")
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
        dest = frozen.materialize(APP, story, root / story / "depot-infra")
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

    These ids were written by hand and no other check reads them: `ostler qa validate` binds
    a plan's `covers=` ids only inside a materialized trial, so a mistyped anchor or an
    off-by-one bullet index would otherwise surface as rows scoring `inconclusive` forever
    while looking exactly like a QA result.

    Every claim in this book is a `consistency:` bullet on a concept node, and the index in
    each id is that bullet's position within its node. Re-order the bullets and every row
    below still resolves — to the wrong clause. This test does not catch that; the `why`
    prose beside each row is what a reader checks it against.
    """
    owed = owed_obligations[row["story"]]
    assert row["obligation"] in owed, (
        f"{row['id']}: {row['obligation']} is not owed by {row['story']} "
        f"({len(owed)} owed obligations); a shared source file demotes it to context-only"
    )


def test_the_stack_contract_is_owed_by_the_story_that_rides_it() -> None:
    """D7's anchor is the coarsest in this key, and that is a deliberate choice worth pinning.

    Nothing owns the program's build inputs but the stack's ops node, so the vanished
    provider pin is filed against `depot-stack:contract`. If a later book edit gives that
    claim a node of its own, this row should move — and the failure that says so is a
    reader's, not a runner's, which is why the note lives here rather than in an assert.
    """
    audit_rows = [row for row in defects() if row["caught_by"] == "audit"]
    assert [row["id"] for row in audit_rows] == ["D7"], audit_rows
    assert audit_rows[0]["obligation"] == "okf:docs/features/depot/ops/depot-stack.md:contract"


# ── the variants build ────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def gocache(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """One Go build cache for every compile in this module, rather than one per test.

    The pulumi + gcp SDK is a large dependency tree and a cold cache rebuilds all of it. A
    per-test cache made this file take twelve minutes, nearly all of it recompiling the same
    unchanged packages eight times over. Sharing is safe because the cache is content
    addressed — a variant's object is keyed by the variant's own source — and it is still
    scoped to the run rather than to the developer's `~/.cache`.
    """
    return tmp_path_factory.mktemp("gocache")


def _variants(suffix: str) -> list[dict[str, str]]:
    return [row for row in defects() if row["path"].endswith(suffix)]


def _variant_ids(suffix: str) -> list[str]:
    return [row["id"] for row in _variants(suffix)]


def test_every_variant_is_go_or_stack_config() -> None:
    """The two kinds this fixture has, and the two the gates below cover between them. A
    variant in any third language would slip past every check in this file."""
    assert sorted(_variant_ids(".go") + _variant_ids(".yaml")) == sorted(defect_ids())


@pytest.mark.parametrize("row", _variants(".go"), ids=_variant_ids(".go"))
def test_every_go_variant_compiles(row: dict[str, str], tmp_path: Path, gocache: Path) -> None:
    """A variant that does not build is caught by every check there is and measures nothing.

    Vetted as well as built: these variants are all behavioral — a member added, a default
    flipped, a resource that stopped being declared — and a `go vet` finding would be the
    kind of thing a reviewer catches before QA runs, scoring the row against the wrong lane.
    """
    if shutil.which("go") is None:
        pytest.skip("no `go` on PATH; the trial's own build step is the enforcing gate")

    program = tmp_path / "pulumi"
    shutil.copytree(APP / "pulumi", program)
    shutil.copyfile(APP / "defects" / row["id"] / row["path"], program / Path(row["path"]).name)

    env = {**os.environ, "GOFLAGS": "-mod=mod", "GOCACHE": str(gocache)}
    built = subprocess.run(
        ["go", "build", "./..."],
        cwd=program, capture_output=True, text=True, env=env, check=False,
    )
    assert built.returncode == 0, built.stderr
    vetted = subprocess.run(
        ["go", "vet", "./..."],
        cwd=program, capture_output=True, text=True, env=env, check=False,
    )
    assert vetted.returncode == 0, vetted.stderr


@pytest.mark.parametrize("row", _variants(".yaml"), ids=_variant_ids(".yaml"))
def test_every_stack_config_variant_parses(row: dict[str, str]) -> None:
    """The stack config's variant has no compiler, so this is its whole build gate.

    A malformed `Pulumi.dev.yaml` fails the preview outright, and a preview that never
    completed is a crash rather than a defect — the row would score as caught by a trial
    that measured nothing.
    """
    parsed = yaml.safe_load((APP / "defects" / row["id"] / row["path"]).read_text(encoding="utf-8"))
    assert isinstance(parsed, dict), parsed
    assert parsed.get("config"), parsed


# ── the preview: the only observable this fixture has ─────────────────────────────────


def _pulumi_is_usable() -> str:
    """Empty when a preview can run here, otherwise the reason it cannot — naming both.

    Two preconditions, not one. `pulumi` on PATH is the obvious half; the pinned gcp
    resource plugin resolving locally is the half that decides whether a preview is a
    measurement or a download — an absent plugin sends the CLI to the network, and a
    *different* plugin previews a different provider's defaults.
    """
    if shutil.which("pulumi") is None:
        return "`pulumi` is not on PATH"
    listed = subprocess.run(
        ["pulumi", "plugin", "ls"], capture_output=True, text=True, check=False
    )
    installed = {
        fields[2]
        for line in listed.stdout.splitlines()
        if len(fields := line.split()) >= 3 and fields[:2] == ["gcp", "resource"]
    }
    if PINNED_PLUGIN not in installed:
        return (
            f"the pinned gcp resource plugin {PINNED_PLUGIN} does not resolve locally "
            f"(installed: {sorted(installed) or 'none'})"
        )
    return ""


def _preview(program: Path, gocache: Path) -> subprocess.CompletedProcess[str]:
    """A plan taken the documented way: through the Makefile, which states the backend.

    Never `pulumi login` — the Makefile exports `PULUMI_BACKEND_URL` at a directory beside
    the program, so the preview a test takes and the preview a person takes are the same
    preview and neither touches an account.
    """
    env = {**os.environ, "GOFLAGS": "-mod=mod", "GOCACHE": str(gocache)}
    return subprocess.run(
        ["make", "-C", str(program), "plan"],
        capture_output=True, text=True, env=env, check=False, timeout=900,
    )


@pytest.mark.parametrize(
    "row", [None, *defects()], ids=["clean", *defect_ids()],
)
def test_the_preview_completes_on_the_clean_tree_and_on_every_variant(
    row: dict[str, str] | None, tmp_path: Path, gocache: Path
) -> None:
    """A variant that breaks the preview is a crash, not a defect.

    This is the fixture's central claim stated mechanically: all seven defects leave a plan
    that is a valid plan, and QA has to read it to find them rather than watch a command
    fail. A row whose preview exits non-zero scores as caught by the first `qa.require` in
    any plan, which measures nothing about detection at all.
    """
    reason = _pulumi_is_usable()
    if reason:
        pytest.skip(
            f"a preview needs both `pulumi` on PATH and the pinned gcp resource plugin "
            f"{PINNED_PLUGIN} installed locally, and {reason}; the trial's own QA run is "
            f"the enforcing gate"
        )

    story = row["story"] if row else STORIES[-1]
    dest = frozen.materialize(APP, story, tmp_path / "depot-infra")
    if row:
        frozen.seed_defect(APP, row, dest)

    planned = _preview(dest / "pulumi", gocache)
    assert planned.returncode == 0, planned.stderr[-4000:]
    assert (dest / "pulumi" / "preview.json").is_file()
