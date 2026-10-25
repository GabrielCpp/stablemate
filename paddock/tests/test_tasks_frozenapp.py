"""The frozen-app answer key: defects, their selection, the round's plan and the fixture's guard."""

from __future__ import annotations

from pathlib import Path

import pytest
from fakes import DOCS, PRODUCTS, STORY, fake_run, folder_run
from smoke import git

from paddock.tasks import frozenapp as fz
from paddock.tasks import leverage as lev
from paddock.tasks.stablemate import TrialError


def write_key(app: Path, body: str) -> Path:
    app.mkdir(parents=True, exist_ok=True)
    (app / "defects.yml").write_text(body, encoding="utf-8")
    return app


KEY = """defects:
  - id: D1
    story: S-1
    path: a.py
    expect: contradicted
  - id: D2
    story: S-1
    path: b.py
    expect: contradicted
    caught_by: audit
"""


def test_a_fixture_refuses_a_leverage_key_it_does_not_have() -> None:
    with pytest.raises(ValueError, match="leverage must name one or more of"):
        fz.Fixture(app="apps/x", repo_dir="x", leverage=("obligations", "clicks"))
    assert fz.Fixture(app="apps/x", repo_dir="x").leverage == lev.LEVERAGE_KEYS


def test_load_defects_defaults_the_catch_route_and_refuses_an_unknown_one(tmp_path: Path) -> None:
    rows = fz.load_defects(write_key(tmp_path / "app", KEY))
    assert [row["caught_by"] for row in rows] == ["run", "audit"]
    with pytest.raises(TrialError, match="caught_by: 'nope'"):
        fz.load_defects(write_key(tmp_path / "bad", KEY.replace("audit", "nope")))


def test_a_missing_answer_key_is_named(tmp_path: Path) -> None:
    with pytest.raises(TrialError, match="no answer key"):
        fz.load_defects(tmp_path)


def test_select_defects_keeps_the_asked_order_and_names_a_stranger(tmp_path: Path) -> None:
    app = write_key(tmp_path / "app", KEY)
    assert [row["id"] for row in fz.select_defects(app, ("D2", "D1"))] == ["D2", "D1"]
    assert len(fz.select_defects(app, ())) == 2
    with pytest.raises(TrialError, match="no such defect"):
        fz.select_defects(app, ("D9",))


def test_key_dir_reads_the_app_beside_the_benchmarks_tasks(tmp_path: Path) -> None:
    run = fake_run(tmp_path)
    fixture = fz.Fixture(app="apps/x", repo_dir="x")
    with pytest.raises(TrialError, match="no answer key under"):
        fz.key_dir(run, fixture)
    write_key(run.benchmark.root / "apps" / "x", KEY)
    assert fz.key_dir(run, fixture) == run.benchmark.root / "apps" / "x"


def test_headline_counts_caught_missed_and_false() -> None:
    trials = [
        {"defect": "D1", "verdict": "caught"},
        {"defect": "D2", "verdict": "missed"},
        {"defect": fz.CLEAN, "verdict": "false"},
    ]
    assert fz.headline(trials).startswith("caught 1/2  missed 1  false 1")


def test_the_trials_dir_lives_in_the_stage(tmp_path: Path) -> None:
    run = fake_run(tmp_path)
    assert fz.trials_dir(run) == run.stage / "artifacts" / "trials"
    assert fz.trials_dir(run).is_dir()


def folder_key(run, body: str = KEY) -> Path:
    """The answer key of a folder benchmark: its stories, one defect variant and its rows, all by member-prefixed path."""
    app = write_key(run.benchmark.root / "apps" / "x", body)
    story = app / "stories" / STORY
    story.mkdir(parents=True)
    (story / "diff.yml").write_text("changed:\n  - api-service/app.py\n", encoding="utf-8")
    (story / "pre" / "api-service").mkdir(parents=True)
    (story / "pre" / "api-service" / "app.py").write_text("api = 0\n", encoding="utf-8")
    variant = app / "defects" / "D1" / "api-service"
    variant.mkdir(parents=True)
    (variant / "app.py").write_text("api = BAD\n", encoding="utf-8")
    return app


FOLDER_KEY = f"""defects:
  - id: D1
    story: {STORY}
    path: api-service/app.py
    obligation: ob-1
    expect: contradicted
"""


def test_a_folder_stage_is_materialized_as_a_repo_per_member_at_the_before_commit(tmp_path: Path) -> None:
    run = folder_run(tmp_path)
    app = folder_key(run, FOLDER_KEY)
    installed: list[str] = []

    tree_root = fz.materialize(
        run.stage, STORY, tmp_path / "trial" / "x", lambda repo: installed.append(repo.name),
        stories=app, run=run,
    )

    assert sorted(installed) == sorted(PRODUCTS)
    for member in (*PRODUCTS, DOCS):
        assert (tree_root / member / ".git").is_dir()
        assert git(tree_root / member, "log", "-1", "--format=%s") == f"before {STORY}"
    assert git(tree_root / "api-service", "show", "HEAD:app.py") == "api = 0"
    assert (tree_root / "api-service" / "app.py").read_text(encoding="utf-8") == "api = 1\n"
    assert not (tree_root / "stories").exists()
    assert not (tree_root / DOCS / "specs" / STORY / "qa-plan.yml").exists()


def test_a_folder_materialize_without_the_run_is_refused(tmp_path: Path) -> None:
    run = folder_run(tmp_path)
    app = folder_key(run, FOLDER_KEY)
    with pytest.raises(TrialError, match="needs the run"):
        fz.materialize(run.stage, STORY, tmp_path / "trial" / "x", None, stories=app)


def test_a_defect_is_seeded_and_judged_at_its_member_prefixed_path(tmp_path: Path) -> None:
    run = folder_run(tmp_path)
    app = folder_key(run, FOLDER_KEY)
    tree_root = fz.materialize(run.stage, STORY, tmp_path / "trial" / "x", None, stories=app, run=run)
    row = fz.select_defects(app, ("D1",))[0]

    assert fz.validate_defects(app) == []
    fz.seed_defect(app, row, tree_root)

    assert (tree_root / "api-service" / "app.py").read_text(encoding="utf-8") == "api = BAD\n"
    assert fz.defect_survived(app, row, tree_root)
    (tree_root / "api-service" / "app.py").write_text("api = 1\n", encoding="utf-8")
    assert not fz.defect_survived(app, row, tree_root)


def test_a_folder_witness_keeps_the_docs_home_and_each_members_config(tmp_path: Path) -> None:
    run = folder_run(tmp_path)
    app = folder_key(run, FOLDER_KEY)
    tree_root = fz.materialize(run.stage, STORY, tmp_path / "trial" / "x", None, stories=app, run=run)
    (tree_root / DOCS / "specs" / STORY / "qa.md").write_text("done\n", encoding="utf-8")

    witness = fz.capture_witness(
        tree_root, tmp_path / "witness", extra=("api-service/app.py",), run=run
    )

    assert (witness / DOCS / "docs" / "services" / "book.md").is_file()
    assert (witness / DOCS / "specs" / STORY / "qa.md").is_file()
    assert (witness / "web-app" / "agents.yml").is_file()
    assert (witness / "api-service" / "app.py").is_file()
    assert not (witness / DOCS / "agents.yml").exists()


def test_the_stack_state_is_reset_in_every_member_that_has_a_compose_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for member in ("api-service", "web-app"):
        (tmp_path / member).mkdir()
    (tmp_path / "api-service" / "compose.yml").write_text("services: {}\n", encoding="utf-8")
    seen: list[str] = []
    monkeypatch.setattr(fz.subprocess, "run", lambda argv, cwd, **_: seen.append(cwd))

    fz.reset_stack_state(tmp_path, ("api-service", "web-app"))

    assert seen == [str(tmp_path / "api-service")]


def test_the_qa_launch_of_a_folder_carries_the_workspace_and_a_config_into_the_tree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = folder_run(tmp_path)
    calls: list[tuple[tuple[str, ...], dict]] = []
    monkeypatch.setattr(run, "cli", lambda *argv, **kwargs: calls.append((argv, kwargs)), raising=False)
    monkeypatch.setattr(fz, "stablemate_checkout", lambda _run: tmp_path / "checkout")
    tree_root = tmp_path / "trial" / "x"

    fz.launch_qa(
        run, fz.Fixture(app="apps/x", repo_dir="x"), tree_root,
        run_id="r1", story=STORY, budget=60.0, runs_dir=tmp_path / "runs",
    )

    (argv, kwargs), = calls
    assert argv[argv.index("--workspace") + 1] == "desk"
    config = Path(argv[argv.index("--config") + 1])
    assert str(tree_root / "api-service") in config.read_text(encoding="utf-8")
    assert kwargs["cwd"] == tree_root / DOCS
    assert kwargs["env"]["AGENT_REPO_DIR"] == str(tree_root / DOCS)
    assert kwargs["env"]["STABLEMATE_ARTIFACTS_DIR"] == str(tree_root / DOCS)
    assert kwargs["env"]["WORKHORSE_MAX_RUNTIME_S"] == "60.0"
    assert '"repo_dir": "' + str(tree_root / DOCS) in argv[argv.index("--params") + 1]
