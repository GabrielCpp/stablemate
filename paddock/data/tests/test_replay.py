"""The replay library's contracts: what a round plans, and what a rewind undoes.

Neither is checkable by running a task — a real trial is a forty-minute agent run behind a
docker stack — and both are exactly the kind of thing that breaks silently. A pin list that
has drifted still runs; it just replays a different commit. A rewind that deletes one file
too many still runs; it just measures a flow being handed less than it was handed
historically, which reads as the loop getting worse.

The declaring fixtures are asserted here too, for the same reason: `expense_split.py` and
`link_shortener_replay.py` are now five and two rows of data, and a typo in a row is not a
crash.
"""

from __future__ import annotations

import contextlib
import importlib
import importlib.util
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType

import pytest

from paddock import loader, registry
from paddock.pointer import Pointer
from paddock.runner import Run

DATA = Path(__file__).parents[1]


@contextlib.contextmanager
def _tasks_dir_on_path() -> Iterator[None]:
    """Stand in for the interpreter, exactly as `paddock.loader` does."""
    saved = sys.path[:]
    sys.path.insert(0, str(DATA / "tasks"))
    try:
        yield
    finally:
        sys.path[:] = saved


def _load(name: str) -> ModuleType:
    path = DATA / "tasks" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None  # noqa: S101 - a real file on disk
    module = importlib.util.module_from_spec(spec)
    with _tasks_dir_on_path():
        # The declaration calls in a task body write to the process-wide registry the
        # loader owns; resetting first is what lets this import happen beside any other.
        registry.REGISTRY.reset()
        sys.modules[name] = module
        spec.loader.exec_module(module)
    return module


with _tasks_dir_on_path():
    replay = importlib.import_module("_replay")
    sm = importlib.import_module("_stablemate")

expense_split = _load("expense_split")
link_shortener = _load("link_shortener_replay")


def git(*args: str, cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=str(cwd), check=True, capture_output=True, text=True)


def make_run(tmp_path: Path, **params: str) -> Run:
    """A `Run` carrying nothing but params — every function under test reads only those."""
    return Run(
        task=loader.load_path(DATA / "tasks" / "expense_split.py"),
        label="t1",
        stage=tmp_path / "stage",
        repo=tmp_path / "stage" / "expense-split",
        scratch=tmp_path / "scratch",
        config=tmp_path / "config.toml",
        data_dir=DATA,
        store=tmp_path / "store",
        seed=Pointer(name="expense-split", repo_dir="expense-split", sha256="0" * 64, bytes=1),
        params=params,
    )


def test_every_expense_split_story_is_pinned_once_on_both_flows() -> None:
    stories = [pin.story for pin in expense_split.FIXTURE.pins]
    assert stories == sorted(set(stories), key=stories.index), "a story is pinned twice"
    assert len(stories) == 5
    for pin in expense_split.FIXTURE.pins:
        # A pin that lost half its pair still runs and replays the wrong flow's state.
        assert pin.commit("qa") and pin.commit("docs")


def test_a_fixture_only_declares_flows_the_library_can_rewind() -> None:
    """A flow with no rewind rule is entered on a tree that already holds its own output.

    That measures a lane confirming its own work, which is the most expensive way there is
    to learn nothing — and it does not fail, so nothing but this says so.
    """
    for fixture in (expense_split.FIXTURE, link_shortener.FIXTURE):
        assert set(fixture.flows) <= set(replay.KNOWN_FLOWS)


def test_a_round_pairs_every_pinned_story_with_every_flow_it_pinned(tmp_path: Path) -> None:
    fixture = expense_split.FIXTURE
    plan = replay.plan_round(make_run(tmp_path), fixture)
    # Stories outermost, so a round interrupted halfway has finished stories rather than
    # half a flow of every story — and only the flows each pin carries a commit for, so
    # the library's default flow list growing (it gained "dev") does not plan trials
    # whose first act is to fail a checkout.
    assert [(pin.story, flow) for pin, flow in plan] == [
        (pin.story, flow)
        for pin in fixture.pins
        for flow in fixture.flows
        if flow in pin.commits
    ]
    assert [flow for _, flow in plan[:2]] == ["qa", "docs"]


def test_a_round_skips_a_flow_a_story_has_no_pin_for(tmp_path: Path) -> None:
    """A fixture may pin one flow for one story and both for another; the round follows.

    Without this the link-shortener fixture — docs-pinned only — would plan QA trials whose
    first act is to fail a checkout.
    """
    plan = replay.plan_round(make_run(tmp_path), link_shortener.FIXTURE)
    assert [(pin.story, flow) for pin, flow in plan] == [
        ("create-short-links", "docs"),
        ("redirect-short-links", "docs"),
    ]


def test_params_narrow_a_round_and_a_typo_is_refused(tmp_path: Path) -> None:
    fixture = expense_split.FIXTURE
    plan = replay.plan_round(make_run(tmp_path, stories="expense-list", flows="qa"), fixture)
    assert [(pin.story, flow) for pin, flow in plan] == [("expense-list", "qa")]

    with pytest.raises(sm.TrialError, match="no pin for"):
        replay.plan_round(make_run(tmp_path, stories="expense-lists"), fixture)
    with pytest.raises(sm.TrialError, match="this fixture replays"):
        replay.plan_round(make_run(tmp_path, flows="review"), fixture)
    # And a flow the *library* knows but this fixture does not pin is refused just as
    # loudly, rather than silently planning nothing.
    with pytest.raises(sm.TrialError, match="this fixture replays"):
        replay.plan_round(make_run(tmp_path, flows="qa"), link_shortener.FIXTURE)


def test_the_qa_rewind_removes_the_flows_outputs_and_nothing_else(tmp_path: Path) -> None:
    fixture = expense_split.FIXTURE
    repo = tmp_path / "repo"
    spec = repo / "docs" / "specs" / "expense-list"
    spec.mkdir(parents=True)
    (spec / "story.md").write_text("the story", encoding="utf-8")
    (spec / "implementation-plan.md").write_text("the plan", encoding="utf-8")
    (spec / "qa-plan.yml").write_text("scenarios: []", encoding="utf-8")
    (spec / "qa-evidence.json").write_text("{}", encoding="utf-8")
    (spec / "qa").mkdir()
    (spec / "qa" / "shot.png").write_bytes(b"")
    # An agent-invented name, not a contract one: this is what the QA agent actually left in
    # balance-settlement's spec dir, and it survived the rewind until a pin sweep found it.
    (spec / "qa-smoke-proof.txt").write_text("smoke ok", encoding="utf-8")
    # A frozen app keeps its harness beside the spec, which is why the strip is an explicit
    # list and not a `qa*` sweep — a sweep would take this with it.
    (spec / "qa_plan.py").write_text("SCENARIOS = []", encoding="utf-8")

    replay.rewind(repo, fixture, fixture.pins[3], "qa")

    # The story and the plan are what the flow is *entered* with; everything the flow
    # writes has to be gone, or the trial measures a repair of its own last answer.
    assert sorted(p.name for p in spec.iterdir()) == [
        "implementation-plan.md",
        "qa_plan.py",
        "story.md",
    ]


def test_the_qa_rewind_refuses_a_pin_whose_spec_dir_is_absent(tmp_path: Path) -> None:
    fixture = expense_split.FIXTURE
    repo = tmp_path / "repo"
    (repo / "docs").mkdir(parents=True)
    with pytest.raises(sm.TrialError, match="still right"):
        replay.rewind(repo, fixture, fixture.pins[0], "qa")


def _book_repo(tmp_path: Path) -> tuple[Path, str]:
    """A two-commit book: `group.md`, then `expense.md` beside it."""
    repo = tmp_path / "repo"
    features = repo / "docs" / "features"
    features.mkdir(parents=True)
    git("init", "--quiet", "--initial-branch", "main", cwd=repo)
    git("config", "user.email", "benchmark@example.com", cwd=repo)
    git("config", "user.name", "stablemate benchmark", cwd=repo)
    (features / "group.md").write_text("group", encoding="utf-8")
    git("add", "--all", cwd=repo)
    git("commit", "--quiet", "-m", "group-membership", cwd=repo)
    (features / "expense.md").write_text("expense", encoding="utf-8")
    git("add", "--all", cwd=repo)
    git("commit", "--quiet", "-m", "expense-record", cwd=repo)
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=str(repo), check=True, capture_output=True, text=True
    ).stdout.strip()
    return repo, head


def test_the_docs_rewind_leaves_the_book_one_story_behind(tmp_path: Path) -> None:
    repo, head = _book_repo(tmp_path)

    pin = replay.Pin(story="expense-record", commits={"docs": head})
    replay.rewind(repo, expense_split.FIXTURE, pin, "docs")

    # The book as it stood *before* this story landed: the real historical input, and one
    # story behind rather than empty — a book rewound further is missing entries outside
    # this story's obligations, which is a different complaint for a reviewer to make.
    assert sorted(p.name for p in (repo / "docs" / "features").iterdir()) == ["group.md"]


def test_book_from_replays_a_story_whose_docs_lane_never_ran(tmp_path: Path) -> None:
    """There is no commit to be the parent of, so the entry state is a tree as it stands.

    The default would rewind to `head~` and hand the lane a book missing the *previous*
    story as well — a strictly easier and historically wrong input.
    """
    repo, head = _book_repo(tmp_path)

    pin = replay.Pin(story="never-documented", commits={"docs": head}, book_from=head)
    replay.rewind(repo, expense_split.FIXTURE, pin, "docs")

    assert sorted(p.name for p in (repo / "docs" / "features").iterdir()) == [
        "expense.md",
        "group.md",
    ]


def test_the_harness_restore_brings_in_config_the_history_never_tracked(tmp_path: Path) -> None:
    """A clone at a pin that predates tracking `agents.yml` installs nothing at all.

    This is not part of the state the flow was entered in — it is the part of the tree the
    capture failed to record — which is why it is applied after the rewind and names only
    files that describe the repo rather than the work.
    """
    repo, _ = _book_repo(tmp_path)
    (repo / "agents.yml").write_text("packs:\n  - go\n", encoding="utf-8")
    git("add", "--all", cwd=repo)
    git("commit", "--quiet", "-m", "track the harness", cwd=repo)
    harness_ref = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=str(repo), check=True, capture_output=True, text=True
    ).stdout.strip()
    (repo / "agents.yml").unlink()

    fixture = replay.Fixture(
        app="x", pins=(), harness=("agents.yml",), harness_ref=harness_ref
    )
    replay.restore_harness(repo, fixture)

    assert (repo / "agents.yml").read_text(encoding="utf-8") == "packs:\n  - go\n"


def test_the_harness_restore_refuses_paths_with_no_ref_to_take_them_from(tmp_path: Path) -> None:
    fixture = replay.Fixture(app="x", pins=(), harness=("agents.yml",))
    with pytest.raises(sm.TrialError, match="no `harness_ref`"):
        replay.restore_harness(tmp_path, fixture)


def test_the_backfill_gives_a_predating_story_the_dependencies_section(tmp_path: Path) -> None:
    """expense-split was captured before `## Dependencies` was a required story section.

    Without the backfill every pin stops at the first node — "story.md is still a bare
    scaffold" — on both flows, and the fixture measures nothing.
    """
    story_md = tmp_path / "docs" / "epics" / "0001-groups" / "stories" / "create-group" / "story.md"
    story_md.parent.mkdir(parents=True)
    story_md.write_text(
        "---\nslug: create-group\n---\n# Story: Create a Group\n\n## Context\n\nprose.\n",
        encoding="utf-8",
    )

    replay.backfill_story_sections(tmp_path)

    written = story_md.read_text(encoding="utf-8")
    assert "## Dependencies\n\n(none)\n" in written
    # Ahead of the prose, and the prose itself untouched — the trial is entered with the
    # story the original run was entered with, plus a heading that reads as no edge.
    assert written.index("## Dependencies") < written.index("## Context")
    assert written.endswith("## Context\n\nprose.\n")


def test_the_backfill_leaves_a_story_that_already_declares_dependencies_alone(
    tmp_path: Path,
) -> None:
    story_md = tmp_path / "docs" / "epics" / "0001-groups" / "stories" / "create-group" / "story.md"
    story_md.parent.mkdir(parents=True)
    # A real edge, which a second `(none)` section would sit above and contradict.
    before = "# Story\n\n## Dependencies\n\n- Blocked by: group-membership\n\n## Context\n\nx.\n"
    story_md.write_text(before, encoding="utf-8")

    replay.backfill_story_sections(tmp_path)

    assert story_md.read_text(encoding="utf-8") == before


def test_the_pack_fix_subscribes_the_captured_app_to_the_docs_pack(tmp_path: Path) -> None:
    """expense-split was captured subscribing to `product-planning` and `go` only.

    The docs lane's prompts carry a `skill_load_ref` to `ostler-documentation`, which ships
    in the `stablemate` pack — so without this every docs trial renders the prompt's
    placeholder text and measures the agent inventing a documentation doctrine.
    """
    agents_yml = tmp_path / "agents.yml"
    agents_yml.write_text(
        "repo:\n  name: bench-expense-split\npacks:\n  - product-planning\n  - go\n"
        "workflows:\n  - coder\n",
        encoding="utf-8",
    )

    replay.subscribe_to_packs(tmp_path, expense_split.FIXTURE.packs)

    written = agents_yml.read_text(encoding="utf-8")
    assert "packs:\n  - product-planning\n  - go\n  - stablemate\n" in written
    # Appended to the block, not to the file: the keys after it are still keys.
    assert written.endswith("workflows:\n  - coder\n")


def test_the_pack_fix_is_a_no_op_when_the_pack_is_already_declared(tmp_path: Path) -> None:
    agents_yml = tmp_path / "agents.yml"
    before = "packs:\n  - stablemate\n  - go\n\n# a comment the seed owns\nworkflows:\n  - coder\n"
    agents_yml.write_text(before, encoding="utf-8")

    replay.subscribe_to_packs(tmp_path, ("stablemate",))

    # Byte-for-byte, comment included — a YAML round-trip would have dropped that line.
    assert agents_yml.read_text(encoding="utf-8") == before


def test_the_pack_fix_is_skipped_entirely_by_a_fixture_that_declares_none(tmp_path: Path) -> None:
    """The link-shortener seed already subscribes to `stablemate`, so there is nothing to
    patch — and a fixture with no packs must not require an `agents.yml` to exist yet."""
    assert link_shortener.FIXTURE.packs == ()
    replay.subscribe_to_packs(tmp_path, ())


def test_the_pack_fix_refuses_an_agents_yml_with_no_packs_block(tmp_path: Path) -> None:
    (tmp_path / "agents.yml").write_text("repo:\n  name: x\n", encoding="utf-8")
    with pytest.raises(sm.TrialError, match="no `packs:` block"):
        replay.subscribe_to_packs(tmp_path, ("stablemate",))
