"""Integrity tests for the frozen `tally-cli` app."""

from __future__ import annotations

import contextlib
import importlib.util
import re
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType

import pytest
from ostler.refs import CodeRef, parse_code_ref, render_code_ref
from paddock.registry import REGISTRY
import yaml

DATA = Path(__file__).parents[1]
APP = DATA / "apps" / "tally-cli"


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
TASK = _load("_tally_cli_task", DATA / "tasks" / "tally_cli_qa.py")

STORIES = ("ledger-init-add", "import-csv", "report-export")

EPIC = "0001-shared-expense-ledger"

SHARED_SOURCE = "tally/cli.py"

_CODE_BULLET = re.compile(r"^- code: (\S+)", re.MULTILINE)


def manifest(story: str) -> dict[str, list[str]]:
    data = yaml.safe_load((APP / "stories" / story / "diff.yml").read_text(encoding="utf-8"))
    return {kind: list(data.get(kind) or []) for kind in ("changed", "added", "pinned")}


def defects() -> list[dict[str, str]]:
    data = yaml.safe_load((APP / "defects.yml").read_text(encoding="utf-8"))
    return list(data["defects"])


def defect_ids() -> list[str]:
    return [row["id"] for row in defects()]


def code_bullets(page: Path) -> list[str]:
    return _CODE_BULLET.findall(page.read_text(encoding="utf-8"))




def test_the_book_grounds_at_symbol_level() -> None:
    """The premise of the fixture, pinned so an ordinary edit cannot dilute it."""
    cited: dict[str, list[CodeRef]] = {}
    for page in (APP / "docs" / "features").rglob("*.md"):
        for target in code_bullets(page):
            ref = parse_code_ref(target)
            cited.setdefault(ref.path, []).append(ref)

    behavioural = {path: refs for path, refs in cited.items() if path.startswith("tally/")}
    unqualified = {
        path: [render_code_ref(ref) for ref in refs]
        for path, refs in behavioural.items()
        if path not in {"tally/__init__.py", "tally/__main__.py"}
        and any(not ref.symbol for ref in refs)
    }
    assert not unqualified, unqualified
    assert len(cited[SHARED_SOURCE]) >= 3, cited[SHARED_SOURCE]


def test_the_book_describes_a_product_with_no_service_in_it() -> None:
    """`claims-api` removed the screen, `depot-infra` removed the process, and this one keeps the process but takes away the socket: there is nothing to start and nothing to reach."""
    from ostler.model import load  # noqa: PLC0415 - a heavy import only this test needs
    from ostler.qa.runbook import stack_runbooks  # noqa: PLC0415

    features = APP / "docs" / "features"
    contexts = {path.parent.name for path in features.rglob("*.md")}
    assert contexts == {"tally", "concepts", "flows", "ops", "fixtures"}, sorted(contexts)
    assert not (APP / "compose.yml").exists(), "a serviceless fixture may not ship a stack"
    assert not stack_runbooks(load(APP)), (
        "this fixture exercises the bring-up's `none` arm — no runbook node may declare a stack"
    )


def test_the_fixture_ships_the_stories_it_claims() -> None:
    from ostler.api import Ostler  # noqa: PLC0415

    okf = Ostler(APP)
    slugs = {node.get("slug") or node.get("name") for node in okf.list("story")}
    assert set(STORIES) <= slugs


def test_the_task_points_at_the_app_and_names_the_trial_dir() -> None:
    assert DATA / TASK.FIXTURE.app == APP
    assert TASK.FIXTURE.repo_dir == "tally-cli"
    assert {row["story"] for row in defects()} <= set(STORIES)


def test_the_qa_lane_opts_into_the_interpreter_and_nothing_else() -> None:
    """The whole transport, declared in one place."""
    agents = yaml.safe_load((APP / "agents.yml").read_text(encoding="utf-8"))
    assert agents.get("qa", {}).get("tools") == ["python3"], agents.get("qa")
    config = (DATA / "configs" / "opencode.toml").read_text(encoding="utf-8")
    assert "[qa_tools.python3]" in config, "the task config must resolve the opted-in tool"




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
def test_pinned_paths_have_a_pinned_image_and_no_other(story: str) -> None:
    """A `pinned:` path has exactly one image."""
    diff = manifest(story)
    for rel in diff["pinned"]:
        assert (APP / "stories" / story / "pinned" / rel).is_file(), f"{story}: no pinned/ for {rel}"
        for phase in ("pre", "post"):
            assert not (APP / "stories" / story / phase / rel).exists(), (
                f"{story}: {rel} is pinned but also has a {phase}/ image"
            )


@pytest.mark.parametrize("story", STORIES)
def test_no_image_names_a_path_the_manifest_does_not(story: str) -> None:
    """A stale `pre/`, `post/` or `pinned/` file is dead weight that reads as coverage."""
    diff = manifest(story)
    declared = {*diff["changed"], *diff["added"], *diff["pinned"]}
    for phase in ("pre", "post", "pinned"):
        root = APP / "stories" / story / phase
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if path.is_file():
                rel = path.relative_to(root).as_posix()
                assert rel in declared, f"{story}: {phase}/{rel} is not in diff.yml"


def test_every_story_edits_the_same_module() -> None:
    """Stated as an assertion because it is the fixture, not a property of it."""
    for story in STORIES:
        diff = manifest(story)
        assert SHARED_SOURCE in {*diff["changed"], *diff["added"]}, story


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


@pytest.mark.parametrize("story", STORIES[:-1])
def test_every_early_story_pins_its_own_book(story: str) -> None:
    """Every story but the last carries its own trimmed book under `pinned:`, and the image is not the finished one: a pinned copy identical to the app tree would be the anachronism with extra steps."""
    pinned = set(manifest(story)["pinned"])
    for rel in ("docs/features/tally/tally.md", "docs/features/tally/flows/track-a-trip.md"):
        assert rel in pinned, f"{story} must pin {rel}"
        image = APP / "stories" / story / "pinned" / rel
        assert image.read_bytes() != (APP / rel).read_bytes(), (
            f"{story}: pinned {rel} is the finished book — nothing was trimmed"
        )


def test_the_last_story_pins_nothing() -> None:
    """The one story whose image the app tree already is — which is why it pins nothing."""
    assert manifest(STORIES[-1])["pinned"] == []


@pytest.mark.parametrize("story", STORIES[:-1])
def test_a_pinned_path_is_identical_in_head_and_worktree_after_materialize(
    story: str, tmp_path: Path
) -> None:
    """The property `pinned:` exists to hold by construction: the pinned image is what HEAD holds, what the worktree holds, and what the fixture ships — so the book is present and current in the trial and contributes no line to `HEAD..WORKTREE`."""
    dest = frozen.materialize(APP, story, tmp_path / "tally-cli")
    for rel in manifest(story)["pinned"]:
        shipped = (APP / "stories" / story / "pinned" / rel).read_bytes()
        committed = subprocess.run(
            ["git", "show", f"HEAD:{rel}"], cwd=dest, capture_output=True, check=True
        ).stdout
        assert committed == shipped, f"{story}: HEAD:{rel} is not the pinned image"
        assert (dest / rel).read_bytes() == shipped, f"{story}: worktree {rel} is not the pinned image"




@pytest.mark.parametrize("story", STORIES)
def test_materialize_leaves_exactly_this_story_uncommitted(story: str, tmp_path: Path) -> None:
    dest = frozen.materialize(APP, story, tmp_path / "tally-cli")
    diff = manifest(story)

    porcelain = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=dest, capture_output=True, text=True, check=True,
    ).stdout.splitlines()
    dirty = {line[3:]: line[:2].strip() for line in porcelain}

    assert set(dirty) == {*diff["changed"], *diff["added"]}
    for rel in diff["added"]:
        assert dirty[rel] == "??"


@pytest.mark.parametrize("story", STORIES)
def test_materialize_puts_this_story_content_in_the_worktree(story: str, tmp_path: Path) -> None:
    """The worktree holds the story's *post* image — the app tree only where it is the last story to ship that path."""
    dest = frozen.materialize(APP, story, tmp_path / "tally-cli")
    for rel in [*manifest(story)["changed"], *manifest(story)["added"]]:
        expected = frozen.story_image(APP, story, rel, phase="post").read_bytes()
        assert (dest / rel).read_bytes() == expected


def test_materialize_does_not_ship_the_answer_key(tmp_path: Path) -> None:
    """An agent that can read `defects.yml` is not being measured on detection, and nothing in its output would say so."""
    dest = frozen.materialize(APP, STORIES[0], tmp_path / "tally-cli")
    for name in frozen.NOT_THE_APP:
        assert not (dest / name).exists(), f"{name} was copied into the trial tree"


@pytest.mark.parametrize("story", STORIES)
def test_materialize_keeps_every_authored_story(story: str, tmp_path: Path) -> None:
    """`stories` is excluded at the app root only — it is also what an epic calls its story folders, and excluding it at any depth deletes every `story.md`."""
    dest = frozen.materialize(APP, STORIES[0], tmp_path / "tally-cli")
    epic = dest / "docs" / "epics" / EPIC
    assert (epic / "epic.md").is_file()
    assert (epic / "stories" / story / "story.md").is_file()


@pytest.mark.parametrize("story", STORIES)
def test_materialized_book_is_unchanged(story: str, tmp_path: Path) -> None:
    """The book sits at its authored state on both sides of HEAD, so QA cannot read the obligations as part of the work under review."""
    dest = frozen.materialize(APP, story, tmp_path / "tally-cli")
    changed_docs = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all", "--", "docs"],
        cwd=dest, capture_output=True, text=True, check=True,
    ).stdout
    assert changed_docs == ""


@pytest.mark.parametrize("story", STORIES)
def test_the_materialized_book_cites_nothing_the_image_does_not_have(
    story: str, tmp_path: Path
) -> None:
    """The anachronism test proper: the trimmed book has to hold up against its own image."""
    from ostler.api import Ostler  # noqa: PLC0415 - a heavy import only this test needs

    dest = frozen.materialize(APP, story, tmp_path / "tally-cli")
    report = Ostler(dest).doctor().data
    assert report["errors"] == 0, report["findings"]


@pytest.mark.parametrize("story", STORIES)
def test_the_obligation_packet_builds_clean_on_a_trial(story: str, tmp_path: Path) -> None:
    """Every story's QA context builds with no error-severity health finding."""
    from ostler.api import Ostler  # noqa: PLC0415 - a heavy import only this test needs

    dest = frozen.materialize(APP, story, tmp_path / "tally-cli")
    outcome = Ostler(dest).qa_context(base="HEAD", spec=dest / "docs" / "specs" / story)
    errors = [
        finding for finding in outcome.data.get("healthFindings", [])
        if finding.get("severity") == "error"
    ]
    assert not errors, errors
    assert outcome.ok, outcome.data.get("status")




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
    assert row["caught_by"] == "run", (
        f"{row['id']}: this fixture has no audit-only row — claims-api's C9 and "
        f"depot-infra's D7 already cover that arm of the scorer"
    )
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

    dest = frozen.materialize(APP, row["story"], tmp_path / "tally-cli")
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
        dest = frozen.materialize(APP, story, root / story / "tally-cli")
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
        f"({len(owed)} owed obligations); a bare-file citation demotes it to context-only"
    )




def test_every_variant_is_python() -> None:
    """The one kind this fixture has, and the one the gates below cover."""
    assert all(row["path"].endswith(".py") for row in defects()), defects()


@pytest.mark.parametrize("row", defects(), ids=defect_ids())
def test_every_variant_still_runs_the_product(row: dict[str, str], tmp_path: Path) -> None:
    """A variant that crashes the CLI is caught by the first `qa.require` in any plan."""
    dest = frozen.materialize(APP, row["story"], tmp_path / "tally-cli")
    frozen.seed_defect(APP, row, dest)
    started = subprocess.run(
        [sys.executable, "-m", "tally", "--help"],
        cwd=dest, capture_output=True, text=True, check=False, timeout=60,
    )
    assert started.returncode == 0, started.stderr[-2000:]
