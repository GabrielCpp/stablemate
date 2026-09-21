"""Integrity tests for the frozen `depot-infra` app."""

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
    REGISTRY.reset()
    with _tasks_dir_on_path():
        sys.modules[name] = module
        spec.loader.exec_module(module)
    REGISTRY.reset()
    return module


frozen = _load("_frozenapp", DATA / "tasks" / "_frozenapp.py")
TASK = _load("_depot_infra_task", DATA / "tasks" / "depot_infra_qa.py")

STORIES = ("artifact-store", "deploy-identity")

EPIC = "0001-artifact-depot"

PINNED_PLUGIN = "8.16.0"

BUILD_OUTPUTS = ("pulumi/.pulumi-state", "pulumi/preview.json")


def manifest(story: str) -> dict[str, list[str]]:
    data = yaml.safe_load((APP / "stories" / story / "diff.yml").read_text(encoding="utf-8"))
    return {"changed": list(data.get("changed") or []), "added": list(data.get("added") or [])}


def defects() -> list[dict[str, str]]:
    data = yaml.safe_load((APP / "defects.yml").read_text(encoding="utf-8"))
    return list(data["defects"])


def defect_ids() -> list[str]:
    return [row["id"] for row in defects()]




def test_the_book_describes_nothing_that_runs() -> None:
    """The premise of the whole fixture, pinned so a later edit cannot quietly dilute it."""
    features = APP / "docs" / "features"
    contexts = {path.parent.name for path in features.rglob("*.md")}
    assert contexts == {"concepts", "ops"}, sorted(contexts)
    assert not (APP / "compose.yml").exists(), "a stackless fixture may not ship a stack"
    from ostler.api import Ostler  # noqa: PLC0415
    from ostler.qa import runbook  # noqa: PLC0415

    assert not runbook.stack_runbooks(Ostler(APP).graph), (
        "this fixture exercises the bring-up's `none` arm — its runbook runs a procedure, "
        "and a `kind: service` step here would give QA a stack to boot"
    )


def test_the_fixture_ships_the_stories_it_claims() -> None:
    from ostler.api import Ostler  # noqa: PLC0415

    okf = Ostler(APP)
    slugs = {node.get("slug") or node.get("name") for node in okf.list("story")}
    assert set(STORIES) <= slugs


def test_the_task_points_at_the_app_and_names_the_trial_dir() -> None:
    assert DATA / TASK.FIXTURE.app == APP
    assert TASK.FIXTURE.repo_dir == "depot-infra"
    assert {row["story"] for row in defects()} <= set(STORIES)


def test_the_audit_task_is_the_qa_round_with_the_auditor_turned_on() -> None:
    """`depot-infra-audit` exists to score the one row a first-verdict round cannot: it must run audit-on, be scoped to exactly the rows filed `caught_by: audit`, and share the QA task's app and repo_dir so the two labels stay comparable row-for-row."""
    audit = _load("_depot_infra_audit_task", DATA / "tasks" / "depot_infra_audit.py")
    assert audit.FIXTURE.first_verdict is False
    assert audit.FIXTURE.app == TASK.FIXTURE.app
    assert audit.FIXTURE.repo_dir == TASK.FIXTURE.repo_dir
    assert audit.FIXTURE.leverage == TASK.FIXTURE.leverage
    audit_rows = {row["id"] for row in defects() if row["caught_by"] == "audit"}
    assert set(audit.FIXTURE.defects) == audit_rows == {"D7"}


def test_the_tree_carries_no_build_output() -> None:
    """`make -C pulumi plan` writes into the app tree, and the seed digest has no excludes."""
    for rel in BUILD_OUTPUTS:
        assert not (APP / rel).exists(), (
            f"{rel} is a build output; delete it rather than excluding it from the seed"
        )


def test_the_dependencies_are_pinned_rather_than_vendored() -> None:
    """54 MB of `vendor/` would be the integrity story; `go.sum` is, and is much smaller."""
    assert not (APP / "pulumi" / "vendor").exists(), "never commit vendor/ — go.sum is the pin"
    assert (APP / "pulumi" / "go.sum").is_file()


def test_the_provider_version_is_pinned_in_the_program() -> None:
    """The pin D7 removes, asserted where it lives."""
    program = (APP / "pulumi" / "main.go").read_text(encoding="utf-8")
    assert f'providerVersion = "{PINNED_PLUGIN}"' in program, program
    assert "pulumi.Version(providerVersion)" in program




@pytest.mark.parametrize("story", STORIES)
def test_every_manifest_path_exists_in_the_app(story: str) -> None:
    diff = manifest(story)
    for rel in [*diff["changed"], *diff["added"]]:
        assert (APP / rel).is_file(), f"{story}: {rel} is in diff.yml but not in the app tree"


@pytest.mark.parametrize("story", STORIES)
def test_changed_paths_have_a_pre_image_and_added_paths_do_not(story: str) -> None:
    """A `changed:` path with no `pre/` is committed at its finished content and vanishes from the story's diff; an `added:` path with one is committed at all."""
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
    """A program has one `main` and a stack has one config file, so those two are shared and everything else belongs to exactly one story."""
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
    """A story's `pre/` image is the post-image of the last story that touched that file."""
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
    """The worktree holds the story's *post* image — the app tree only where it is the last story to ship that path."""
    dest = frozen.materialize(APP, story, tmp_path / "depot-infra")
    for rel in [*manifest(story)["changed"], *manifest(story)["added"]]:
        expected = frozen.story_image(APP, story, rel, phase="post").read_bytes()
        assert (dest / rel).read_bytes() == expected


def test_materialize_does_not_ship_the_answer_key(tmp_path: Path) -> None:
    """An agent that can read `defects.yml` is not being measured on detection, and nothing in its output would say so."""
    dest = frozen.materialize(APP, "artifact-store", tmp_path / "depot-infra")
    for name in frozen.NOT_THE_APP:
        assert not (dest / name).exists(), f"{name} was copied into the trial tree"


@pytest.mark.parametrize("story", STORIES)
def test_materialize_keeps_every_authored_story(story: str, tmp_path: Path) -> None:
    """`stories` is excluded at the app root only — it is also what an epic calls its story folders, and excluding it at any depth deletes every `story.md`."""
    dest = frozen.materialize(APP, "artifact-store", tmp_path / "depot-infra")
    epic = dest / "docs" / "epics" / EPIC
    assert (epic / "epic.md").is_file()
    assert (epic / "stories" / story / "story.md").is_file()


@pytest.mark.parametrize("story", STORIES)
def test_the_obligation_packet_builds_clean_on_a_trial(story: str, tmp_path: Path) -> None:
    """Every story's QA context builds with no error-severity health finding."""
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
    """The book sits at its authored state on both sides of HEAD, so QA cannot read the obligations as part of the work under review."""
    dest = frozen.materialize(APP, "deploy-identity", tmp_path / "depot-infra")
    changed_docs = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all", "--", "docs"],
        cwd=dest, capture_output=True, text=True, check=True,
    ).stdout
    assert changed_docs == ""




def test_the_answer_key_names_its_defects_once() -> None:
    ids = defect_ids()
    assert len(ids) == len(set(ids)), ids
    assert set(ids) == {path.name for path in (APP / "defects").iterdir() if path.is_dir()}


@pytest.mark.parametrize("row", defects(), ids=defect_ids())
def test_every_defect_variant_exists_on_both_sides(row: dict[str, str]) -> None:
    """A variant with no counterpart in the app overwrites nothing the story implements; an app path with no variant is a row that applies nothing at all."""
    assert (APP / "defects" / row["id"] / row["path"]).is_file()
    assert (APP / row["path"]).is_file()


@pytest.mark.parametrize("row", defects(), ids=defect_ids())
def test_every_defect_actually_changes_the_story_image(row: dict[str, str]) -> None:
    """The variant must differ from the file the story would otherwise ship."""
    correct = frozen.story_image(APP, row["story"], row["path"], phase="post").read_bytes()
    assert (APP / "defects" / row["id"] / row["path"]).read_bytes() != correct


@pytest.mark.parametrize("row", defects(), ids=defect_ids())
def test_every_defect_declares_a_route_and_an_expectation(row: dict[str, str]) -> None:
    assert row["expect"] == "contradicted"
    assert row["caught_by"] in {"run", "audit"}
    assert row["why"].strip()


@pytest.mark.parametrize("row", defects(), ids=defect_ids())
def test_seeding_a_defect_stays_inside_the_story_diff(row: dict[str, str], tmp_path: Path) -> None:
    """A variant that lands anywhere else is a second, undocumented defect — and a trial carrying two of them scores one as a catch whichever one QA found."""
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
    """The row's obligation must be one this story's trial owes, not merely one the book mints."""
    owed = owed_obligations[row["story"]]
    assert row["obligation"] in owed, (
        f"{row['id']}: {row['obligation']} is not owed by {row['story']} "
        f"({len(owed)} owed obligations); a shared source file demotes it to context-only"
    )


def test_the_stack_contract_is_owed_by_the_story_that_rides_it() -> None:
    """D7's anchor is the coarsest in this key, and that is a deliberate choice worth pinning."""
    audit_rows = [row for row in defects() if row["caught_by"] == "audit"]
    assert [row["id"] for row in audit_rows] == ["D7"], audit_rows
    assert audit_rows[0]["obligation"] == "okf:docs/features/depot/ops/depot-stack.md:contract"




@pytest.fixture(scope="module")
def gocache(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """One Go build cache for every compile in this module, rather than one per test."""
    return tmp_path_factory.mktemp("gocache")


def _variants(suffix: str) -> list[dict[str, str]]:
    return [row for row in defects() if row["path"].endswith(suffix)]


def _variant_ids(suffix: str) -> list[str]:
    return [row["id"] for row in _variants(suffix)]


def test_every_variant_is_go_or_stack_config() -> None:
    """The two kinds this fixture has, and the two the gates below cover between them."""
    assert sorted(_variant_ids(".go") + _variant_ids(".yaml")) == sorted(defect_ids())


@pytest.mark.parametrize("row", _variants(".go"), ids=_variant_ids(".go"))
@pytest.mark.toolchain
def test_every_go_variant_compiles(row: dict[str, str], tmp_path: Path, gocache: Path) -> None:
    """A variant that does not build is caught by every check there is and measures nothing."""
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
    """The stack config's variant has no compiler, so this is its whole build gate."""
    parsed = yaml.safe_load((APP / "defects" / row["id"] / row["path"]).read_text(encoding="utf-8"))
    assert isinstance(parsed, dict), parsed
    assert parsed.get("config"), parsed




def _pulumi_is_usable() -> str:
    """Empty when a preview can run here, otherwise the reason it cannot — naming both."""
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
    """A plan taken the documented way: through the Makefile, which states the backend."""
    env = {**os.environ, "GOFLAGS": "-mod=mod", "GOCACHE": str(gocache)}
    return subprocess.run(
        ["make", "-C", str(program), "plan"],
        capture_output=True, text=True, env=env, check=False, timeout=900,
    )


@pytest.mark.parametrize(
    "row", [None, *defects()], ids=["clean", *defect_ids()],
)
@pytest.mark.toolchain
def test_the_preview_completes_on_the_clean_tree_and_on_every_variant(
    row: dict[str, str] | None, tmp_path: Path, gocache: Path
) -> None:
    """A variant that breaks the preview is a crash, not a defect."""
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
