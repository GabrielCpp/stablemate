"""Integrity tests for the frozen `tally-cli` app.

The same rot classes as its two siblings — a book that stops being clean, a manifest that
stops matching the tree, a materialization that stops producing a worktree diff, an
answer-key row whose obligation is no longer owed, a variant that stops differing or stops
running. Three things about this app change how they present:

* **Nothing here is separated by a file.** All three stories touch `tally/cli.py` and two of
  them `tally/ledger.py`, so file-level ownership says nothing and every citation in the book
  is symbol-qualified. That is the fixture's premise, and `test_the_book_grounds_at_symbol_level`
  is what keeps a later "tidy" extraction from quietly turning it into a third `claims-api`.
* **The book is versioned per story.** Symbol grounding is exactly what makes an authored book
  anachronistic in an earlier image: a `code:` bullet naming `tally/report.py::summarize` in
  story 1's worktree is a dangling citation, and the packet says so at error severity. Each
  story therefore `pinned:`s its own trimmed copy of the book — one image, committed with the
  before tree and never touched after — and two tests below pin both halves of that: the image
  being identical in HEAD and the worktree, and the image holding up on its own.
* **The plans are frozen and shipped.** `docs/specs/<story>/qa_plan.py` is authored here rather
  than by the agent under measurement, so `ostler.qa.lint`'s allowlist and the plan validator's
  vocabulary are load-bearing for this fixture in a way they are not for one whose plans are
  written at trial time. The lint/validate pass below is the early warning that a tightened
  allowlist has silently broken the round.

There is no toolchain-gated extra. The product is stdlib-only Python reached over a process
boundary, so every gate in this file runs on any machine that can run the test suite.
"""

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
TASK = _load("_tally_cli_task", DATA / "tasks" / "tally_cli_qa.py")

#: Replay order, which is also dependency order: `import` merges into the ledger `init` and
#: `add` established, and `report` totals what the other two put there.
STORIES = ("ledger-init-add", "import-csv", "report-export")

EPIC = "0001-shared-expense-ledger"

#: The module every story edits — the reason this fixture exists at all.
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


def test_the_book_grounds_at_symbol_level() -> None:
    """The premise of the fixture, pinned so an ordinary edit cannot dilute it.

    A bare `- code: tally/cli.py` on a node that shares that file with two other nodes is
    demoted to context by ostler and takes every defect seeded behind it out of scoring —
    the exact failure `policy-desk`'s one-node-per-file layout exists to avoid, arriving
    here through the opposite door. Every citation of a module that holds behaviour has to
    name the function.
    """
    cited: dict[str, list[str]] = {}
    for page in (APP / "docs" / "features").rglob("*.md"):
        for target in code_bullets(page):
            cited.setdefault(target.split("::")[0], []).append(target)

    behavioural = {path: targets for path, targets in cited.items() if path.startswith("tally/")}
    unqualified = {
        path: targets
        for path, targets in behavioural.items()
        # `__init__.py` and `__main__.py` hold no behaviour to name: the first is the package
        # marker, the second two lines of entry point. Everything else must be symbol-cited.
        if path not in {"tally/__init__.py", "tally/__main__.py"}
        and any("::" not in target for target in targets)
    }
    assert not unqualified, unqualified
    assert len(cited[SHARED_SOURCE]) >= 3, cited[SHARED_SOURCE]


def test_the_book_describes_a_product_with_no_service_in_it() -> None:
    """`claims-api` removed the screen, `depot-infra` removed the process, and this one keeps
    the process but takes away the socket: there is nothing to start and nothing to reach."""
    features = APP / "docs" / "features"
    contexts = {path.parent.name for path in features.rglob("*.md")}
    assert contexts == {"tally", "concepts", "flows"}, sorted(contexts)
    assert not (APP / "compose.yml").exists(), "a serviceless fixture may not ship a stack"
    assert not (APP / "qa-stack.yml").exists(), "this fixture exercises `ensure_stack`'s skip arm"


def test_the_fixture_ships_the_stories_it_claims() -> None:
    from ostler.api import Ostler  # noqa: PLC0415

    okf = Ostler(APP)
    slugs = {node.get("slug") or node.get("name") for node in okf.list("story")}
    assert set(STORIES) <= slugs


def test_the_task_points_at_the_app_and_names_the_trial_dir() -> None:
    assert DATA / TASK.FIXTURE.app == APP
    # farrier derives generated skill names from the basename; anything else dangles.
    assert TASK.FIXTURE.repo_dir == "tally-cli"
    assert {row["story"] for row in defects()} <= set(STORIES)


def test_the_qa_lane_opts_into_the_interpreter_and_nothing_else() -> None:
    """The whole transport, declared in one place.

    A plan may not import the package — `ostler.qa.lint` is an AST allowlist — so `python3`
    is how a scenario reaches the product, and the fixture is unrunnable without it. It is
    an opt-in rather than a builtin on purpose: the tracked task config is what resolves it,
    so the round does not depend on what any particular machine's `~/.config` happens to say.
    """
    agents = yaml.safe_load((APP / "agents.yml").read_text(encoding="utf-8"))
    assert agents.get("qa", {}).get("tools") == ["python3"], agents.get("qa")
    config = (DATA / "configs" / "opencode.toml").read_text(encoding="utf-8")
    assert "[qa_tools.python3]" in config, "the task config must resolve the opted-in tool"


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
def test_pinned_paths_have_a_pinned_image_and_no_other(story: str) -> None:
    """A `pinned:` path has exactly one image. A `pre/` or `post/` copy beside it is the old
    duplicate arrangement creeping back — two files that have to be kept byte-identical by a
    test, where one file is identical by construction."""
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
    """Stated as an assertion because it is the fixture, not a property of it.

    If a refactor ever gives each subcommand its own module, every defect below becomes
    catchable by file-level reasoning and the fixture stops measuring the thing it was
    built to measure — while every other test in this file still passes.
    """
    for story in STORIES:
        diff = manifest(story)
        assert SHARED_SOURCE in {*diff["changed"], *diff["added"]}, story


def test_each_story_starts_where_the_previous_one_ended() -> None:
    """A story's `pre/` image is the post-image of the last story that touched that file.

    Load bearing here in a way it is not for `claims-api`: `cli.py` is carried across all
    three stories as duplicated bytes rather than references, and duplicated content drifts
    silently — in the direction that scores as a catch.
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


@pytest.mark.parametrize("story", STORIES[:-1])
def test_every_early_story_pins_its_own_book(story: str) -> None:
    """Every story but the last carries its own trimmed book under `pinned:`, and the image
    is not the finished one: a pinned copy identical to the app tree would be the anachronism
    with extra steps."""
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
    """The property `pinned:` exists to hold by construction: the pinned image is what HEAD
    holds, what the worktree holds, and what the fixture ships — so the book is present and
    current in the trial and contributes no line to `HEAD..WORKTREE`."""
    dest = frozen.materialize(APP, story, tmp_path / "tally-cli")
    for rel in manifest(story)["pinned"]:
        shipped = (APP / "stories" / story / "pinned" / rel).read_bytes()
        committed = subprocess.run(
            ["git", "show", f"HEAD:{rel}"], cwd=dest, capture_output=True, check=True
        ).stdout
        assert committed == shipped, f"{story}: HEAD:{rel} is not the pinned image"
        assert (dest / rel).read_bytes() == shipped, f"{story}: worktree {rel} is not the pinned image"


# ── materialization ───────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("story", STORIES)
def test_materialize_leaves_exactly_this_story_uncommitted(story: str, tmp_path: Path) -> None:
    dest = frozen.materialize(APP, story, tmp_path / "tally-cli")
    diff = manifest(story)

    porcelain = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=dest, capture_output=True, text=True, check=True,
    ).stdout.splitlines()
    dirty = {line[3:]: line[:2].strip() for line in porcelain}

    # A `pinned:` path is committed at the content the worktree holds and never shows up as
    # dirty. That is the point of it.
    assert set(dirty) == {*diff["changed"], *diff["added"]}
    for rel in diff["added"]:
        assert dirty[rel] == "??"


@pytest.mark.parametrize("story", STORIES)
def test_materialize_puts_this_story_content_in_the_worktree(story: str, tmp_path: Path) -> None:
    """The worktree holds the story's *post* image — the app tree only where it is the last
    story to ship that path."""
    dest = frozen.materialize(APP, story, tmp_path / "tally-cli")
    for rel in [*manifest(story)["changed"], *manifest(story)["added"]]:
        expected = frozen.story_image(APP, story, rel, phase="post").read_bytes()
        assert (dest / rel).read_bytes() == expected


def test_materialize_does_not_ship_the_answer_key(tmp_path: Path) -> None:
    """An agent that can read `defects.yml` is not being measured on detection, and nothing
    in its output would say so."""
    dest = frozen.materialize(APP, STORIES[0], tmp_path / "tally-cli")
    for name in frozen.NOT_THE_APP:
        assert not (dest / name).exists(), f"{name} was copied into the trial tree"


@pytest.mark.parametrize("story", STORIES)
def test_materialize_keeps_every_authored_story(story: str, tmp_path: Path) -> None:
    """`stories` is excluded at the app root only — it is also what an epic calls its story
    folders, and excluding it at any depth deletes every `story.md`."""
    dest = frozen.materialize(APP, STORIES[0], tmp_path / "tally-cli")
    epic = dest / "docs" / "epics" / EPIC
    assert (epic / "epic.md").is_file()
    assert (epic / "stories" / story / "story.md").is_file()


@pytest.mark.parametrize("story", STORIES)
def test_materialized_book_is_unchanged(story: str, tmp_path: Path) -> None:
    """The book sits at its authored state on both sides of HEAD, so QA cannot read the
    obligations as part of the work under review."""
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
    """The anachronism test proper: the trimmed book has to hold up against its own image.

    Everything else about the per-story book is bookkeeping about bytes; this is the thing
    the bookkeeping is for. `doctor` resolves every citation against the tree it is run in,
    so a bullet naming `tally/report.py::summarize` in story 1 is an error here — and an
    error here is a blocking health finding in the trial's packet, before a scenario runs.
    """
    from ostler.api import Ostler  # noqa: PLC0415 - a heavy import only this test needs

    dest = frozen.materialize(APP, story, tmp_path / "tally-cli")
    report = Ostler(dest).doctor().data
    assert report["errors"] == 0, report["findings"]


@pytest.mark.parametrize("story", STORIES)
def test_the_obligation_packet_builds_clean_on_a_trial(story: str, tmp_path: Path) -> None:
    """Every story's QA context builds with no error-severity health finding.

    This is what a trial does first, and an `unmapped-change` there is not a warning the run
    walks past: the QA lane sends the packet to a repair agent, which edits the frozen book
    before a scenario runs. The control then measures a fixture nobody authored, and the
    minutes and tokens the repair spent land in the score as QA's.
    """
    from ostler.api import Ostler  # noqa: PLC0415 - a heavy import only this test needs

    dest = frozen.materialize(APP, story, tmp_path / "tally-cli")
    outcome = Ostler(dest).qa_context(base="HEAD", spec=dest / "docs" / "specs" / story)
    errors = [
        finding for finding in outcome.data.get("healthFindings", [])
        if finding.get("severity") == "error"
    ]
    assert not errors, errors
    assert outcome.ok, outcome.data.get("status")


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

    Note which image: two of the three source files are shared, so this is the story's own
    `post/` and not the app tree. A variant of `cli.py` for story 1 compared against the app
    tree would differ by two whole subcommands nobody seeded.
    """
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
    """A variant that lands anywhere else is a second, undocumented defect — and a trial
    carrying two of them scores one as a catch whichever one QA found."""
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


# ── owedness: the property that makes a row scorable at all ───────────────────────────


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
    """The row's obligation must be one this story's trial owes, not merely one the book
    mints.

    This is the test the whole fixture is arranged around. Three stories share `cli.py`, so
    owedness here is decided by symbol grounding and by nothing else: demote one citation to
    a bare file and the rows behind it go `inconclusive` forever, looking exactly like a QA
    lane that never answered.
    """
    owed = owed_obligations[row["story"]]
    assert row["obligation"] in owed, (
        f"{row['id']}: {row['obligation']} is not owed by {row['story']} "
        f"({len(owed)} owed obligations); a bare-file citation demotes it to context-only"
    )


# ── the variants run ──────────────────────────────────────────────────────────────────


def test_every_variant_is_python() -> None:
    """The one kind this fixture has, and the one the gates below cover. A variant in any
    other language would slip past every check in this file."""
    assert all(row["path"].endswith(".py") for row in defects()), defects()


@pytest.mark.parametrize("row", defects(), ids=defect_ids())
def test_every_variant_still_runs_the_product(row: dict[str, str], tmp_path: Path) -> None:
    """A variant that crashes the CLI is caught by the first `qa.require` in any plan.

    This is the fixture's central claim stated mechanically: all seven defects leave a
    program that starts, parses its arguments and does something plausible — QA has to read
    what it did to find them, rather than watch it fall over. A syntax error or an import
    that no longer resolves would score as a catch measuring nothing about detection.
    """
    dest = frozen.materialize(APP, row["story"], tmp_path / "tally-cli")
    frozen.seed_defect(APP, row, dest)
    started = subprocess.run(
        [sys.executable, "-m", "tally", "--help"],
        cwd=dest, capture_output=True, text=True, check=False, timeout=60,
    )
    assert started.returncode == 0, started.stderr[-2000:]
