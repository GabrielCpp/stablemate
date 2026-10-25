"""The replay plan: which pinned stories run on which flows."""

from __future__ import annotations

from pathlib import Path

import pytest
from fakes import DOCS, STORY, commit_all, folder_run
from fakes import fake_run
from smoke import git

from paddock.tasks import replay
from paddock.tasks.stablemate import TrialError

FIXTURE = replay.Fixture(
    app="apps/x",
    pins=(
        replay.Pin("S-1", {"qa": "c1", "docs": "c2"}),
        replay.Pin("S-2", {"qa": "c3"}),
    ),
    flows=("qa", "docs"),
)


def test_the_plan_runs_every_pinned_story_on_every_flow_it_has(tmp_path: Path) -> None:
    plan = replay.plan_round(fake_run(tmp_path), FIXTURE)
    assert [(pin.story, flow) for pin, flow in plan] == [("S-1", "qa"), ("S-1", "docs"), ("S-2", "qa")]


def test_the_stories_and_flows_inputs_narrow_the_plan(tmp_path: Path) -> None:
    run = fake_run(tmp_path, inputs={"stories": ["S-1"], "flows": ["docs"]})
    assert [(pin.story, flow) for pin, flow in replay.plan_round(run, FIXTURE)] == [("S-1", "docs")]


def test_an_unpinned_story_or_unknown_flow_is_refused(tmp_path: Path) -> None:
    with pytest.raises(TrialError, match="no pin for: S-9"):
        replay.plan_round(fake_run(tmp_path, inputs={"stories": ["S-9"]}), FIXTURE)
    with pytest.raises(TrialError, match="this fixture replays"):
        replay.plan_round(fake_run(tmp_path, inputs={"flows": ["dev"]}), FIXTURE)


def test_a_pin_without_a_commit_for_the_flow_is_named() -> None:
    with pytest.raises(TrialError, match="no dev commit pinned"):
        FIXTURE.pins[0].commit("dev")
    assert FIXTURE.pins[0].entry_ref("qa") == "c1~"


def advance(repo: Path, rel: str, body: str) -> str:
    (repo / rel).parent.mkdir(parents=True, exist_ok=True)
    (repo / rel).write_text(body, encoding="utf-8")
    return commit_all(repo, f"change {rel}")


def staged_pin(run, flow: str) -> tuple[replay.Pin, str, str, str]:
    """A pin on every member that has moved since its first commit, and the commits it names."""
    api = advance(run.stage / "api-service", "app.py", "api = 2\n")
    web = advance(run.stage / "web-app", "app.py", "web = 2\n")
    book = advance(run.stage / DOCS, "docs/services/book.md", "# book, later\n")
    return replay.Pin(STORY, {flow: {"api-service": api, DOCS: book}}), api, web, book


def test_a_pin_names_a_commit_per_member_on_a_folder_stage(tmp_path: Path) -> None:
    pin = replay.Pin("S-1", {"qa": {"api-service": "c1"}, "dev": "c2"})
    members = ("api-service", "web-app")
    assert pin.commits_of("qa", members) == {"api-service": "c1"}
    assert pin.commit("qa", "api-service") == "c1"
    assert pin.entry_ref("qa", "api-service") == "c1~"
    with pytest.raises(TrialError, match="name each member"):
        pin.commits_of("dev", members)
    with pytest.raises(TrialError, match="names commits per member"):
        pin.commit("qa")
    with pytest.raises(TrialError, match="names nope"):
        replay.Pin("S-1", {"qa": {"nope": "c1"}}).commits_of("qa", members)
    assert pin.commits_of("dev", ()) == {"": "c2"}


def test_a_folder_checkout_enters_each_pinned_member_at_its_commit_and_leaves_the_rest_at_head(
    tmp_path: Path,
) -> None:
    run = folder_run(tmp_path)
    first_api = git(run.stage / "api-service", "rev-parse", "HEAD")
    _, _api, web, _book = staged_pin(run, "qa")
    pin = replay.Pin(STORY, {"qa": {"api-service": first_api}})
    installed: list[str] = []

    dest = replay.checkout(
        run, replay.Fixture(app="x", pins=(pin,)), pin, "qa", tmp_path / "trial" / "x",
        lambda repo: installed.append(repo.name),
    )

    assert git(dest / "api-service", "rev-parse", "HEAD") == first_api
    assert git(dest / "web-app", "rev-parse", "HEAD") == web
    assert (dest / "api-service" / "app.py").read_text(encoding="utf-8") == "api = 1\n"
    assert not (dest / DOCS / "specs" / STORY / "qa-plan.yml").exists()
    assert sorted(installed) == ["api-service", "web-app"]


def test_a_folder_dev_replay_rewinds_every_pinned_member_and_finds_the_story(tmp_path: Path) -> None:
    run = folder_run(tmp_path)
    pin, *_ = staged_pin(run, "dev")

    dest = replay.checkout(
        run, replay.Fixture(app="x", pins=(pin,)), pin, "dev", tmp_path / "trial" / "x", lambda _repo: None
    )

    assert (dest / "api-service" / "app.py").read_text(encoding="utf-8") == "api = 1\n"
    assert (dest / "web-app" / "app.py").read_text(encoding="utf-8") == "web = 2\n"
    assert (dest / DOCS / "docs" / "services" / "book.md").read_text(encoding="utf-8") == "# book\n"


def test_a_folder_docs_replay_rewinds_the_book_in_the_docs_home(tmp_path: Path) -> None:
    run = folder_run(tmp_path)
    pin, *_ = staged_pin(run, "docs")

    dest = replay.checkout(
        run, replay.Fixture(app="x", pins=(pin,)), pin, "docs", tmp_path / "trial" / "x", lambda _repo: None
    )

    assert (dest / DOCS / "docs" / "services" / "book.md").read_text(encoding="utf-8") == "# book\n"


def test_a_plain_commit_on_a_folder_stage_is_refused_at_checkout(tmp_path: Path) -> None:
    run = folder_run(tmp_path)
    pin = replay.Pin(STORY, {"qa": "c1"})
    with pytest.raises(TrialError, match="name each member"):
        replay.checkout(
            run, replay.Fixture(app="x", pins=(pin,)), pin, "qa", tmp_path / "trial" / "x", lambda _repo: None
        )


def test_the_flow_launch_of_a_folder_carries_the_workspace_and_a_config_into_the_tree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = folder_run(tmp_path)
    calls: list[tuple[tuple[str, ...], dict]] = []
    monkeypatch.setattr(run, "cli", lambda *argv, **kwargs: calls.append((argv, kwargs)), raising=False)
    monkeypatch.setattr(replay.sm, "stablemate_checkout", lambda _run: tmp_path / "checkout")
    tree_root = tmp_path / "trial" / "x"

    replay.launch_flow(
        run, tree_root, "dev", run_id="r1", story=STORY, budget=60.0, runs_dir=tmp_path / "runs"
    )

    (argv, kwargs), = calls
    assert argv[argv.index("workhorse-coder") + 2] == "dev"
    assert argv[argv.index("--workspace") + 1] == "desk"
    config = Path(argv[argv.index("--config") + 1])
    assert str(tree_root / "web-app") in config.read_text(encoding="utf-8")
    assert kwargs["cwd"] == tree_root / DOCS
    assert kwargs["env"]["AGENT_REPO_DIR"] == str(tree_root / DOCS)
