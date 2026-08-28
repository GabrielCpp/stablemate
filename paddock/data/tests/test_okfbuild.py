"""The book-building rulers: pure functions over a witness tree, `–` when they cannot read.

Everything here is literal — a canned book written into `tmp_path`, a hand-rolled
`trials.json`, no agent, no docker, no builder run. What is pinned is the part a live
round cannot debug when it goes wrong: that each ruler measures the witness it is given,
that an unreadable witness renders as `–` and never as `0`, and that the headline says
what the round did rather than what it hoped.
"""

from __future__ import annotations

import contextlib
import importlib.util
import json
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

from paddock import loader
from paddock.pointer import Pointer
from paddock.runner import Run

DATA = Path(__file__).parents[1]


@contextlib.contextmanager
def _tasks_dir_on_path() -> Iterator[None]:
    """Stand in for the interpreter, exactly as `paddock.loader` does.

    Task modules are loose files that import their siblings by bare name, so a loader —
    here, the test — has to put their directory on the path the way `python tasks/x.py`
    would, and take it off again.
    """
    saved = sys.path[:]
    sys.path.insert(0, str(DATA / "tasks"))
    try:
        yield
    finally:
        sys.path[:] = saved


_spec = importlib.util.spec_from_file_location("_okfbuild", DATA / "tasks" / "_okfbuild.py")
assert _spec is not None and _spec.loader is not None  # noqa: S101 - a real file on disk
okfbuild = importlib.util.module_from_spec(_spec)
with _tasks_dir_on_path():
    sys.modules["_okfbuild"] = okfbuild
    _spec.loader.exec_module(okfbuild)

BLANK = okfbuild.BLANK


# ── the canned witness ────────────────────────────────────────────────────────────────


def fixture() -> object:
    return okfbuild.Fixture(service="svc", source_path="svc", repo_dir="app")


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def witness(tmp_path: Path) -> Path:
    """A loadable two-node book: a concept, and a screen whose `detail:` points at it."""
    root = tmp_path / "witness"
    write(
        root / "docs" / "features" / "svc" / "policy-format.md",
        "---\ntype: concept\nslug: policy-format\ntitle: Policy format\n---\n"
        "# Policy format\n",
    )
    write(
        root / "docs" / "features" / "svc" / "gui" / "screens" / "widget.md",
        "---\ntype: screen\nslug: widget\ntitle: Widget\n---\n# Widget\n\n"
        "- route: `/widget`\n- detail: [Policy format](../../policy-format.md)\n",
    )
    return root


# ── the rulers ────────────────────────────────────────────────────────────────────────


def test_doctor_and_fmt_read_the_witness(tmp_path: Path) -> None:
    root = witness(tmp_path)
    doctor = okfbuild.doctor_counts(root)
    assert doctor is not None
    assert isinstance(doctor["errors"], int) and isinstance(doctor["warnings"], int)
    unformatted = okfbuild.fmt_check(root)
    assert isinstance(unformatted, list)


def test_an_unreadable_witness_is_none_never_a_count(tmp_path: Path) -> None:
    """A build that died before writing anything must score `–`, not `0e/0w` clean."""
    empty = tmp_path / "empty"
    empty.mkdir()
    assert okfbuild.doctor_counts(empty) is None
    assert okfbuild.fmt_check(empty) is None
    assert okfbuild.graph_counts(empty) is None


def test_coverage_is_the_builders_own_claim(tmp_path: Path) -> None:
    root = witness(tmp_path)
    assert okfbuild.coverage_counts(root, fixture()) is None
    write(
        root / "docs" / "features" / "svc" / "coverage.json",
        json.dumps({"covered": 3, "total": 4, "waived": 0}),
    )
    assert okfbuild.coverage_counts(root, fixture()) == {"covered": 3, "total": 4}
    write(root / "docs" / "features" / "svc" / "coverage.json", "not json")
    assert okfbuild.coverage_counts(root, fixture()) is None


def test_graph_counts_the_loaded_book(tmp_path: Path) -> None:
    graph = okfbuild.graph_counts(witness(tmp_path))
    assert graph is not None
    # Two nodes, and at least the node-level contract each one mints.
    assert graph["nodes"] == 2
    assert graph["obligations"] >= 2


def test_judgment_counts_concepts_and_their_inbound_details(tmp_path: Path) -> None:
    judgment = okfbuild.judgment_counts(witness(tmp_path))
    assert judgment == {"concepts": 1, "detail_links": 1}


def test_judgment_is_blank_when_the_registry_lacks_the_vocabulary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Against a registry with no `rule:` on concept, a zero would blame the build for
    the toolchain — the column degrades to `–` instead (the Track-A degrade)."""
    from ostler import registry

    monkeypatch.setattr(registry, "declared_keys", lambda node_type: frozenset())
    assert okfbuild.judgment_counts(witness(tmp_path)) is None


# ── the score ─────────────────────────────────────────────────────────────────────────


def make_run(tmp_path: Path, **params: str) -> Run:
    """A `Run` carrying nothing but params and paths — what `score_round` reads."""
    return Run(
        task=loader.load_path(DATA / "tasks" / "expense_split.py"),
        label="t1",
        stage=tmp_path / "stage",
        repo=tmp_path / "stage" / "app",
        scratch=tmp_path / "scratch",
        config=tmp_path / "config.toml",
        data_dir=DATA,
        store=tmp_path / "store",
        seed=Pointer(name="app", repo_dir="app", sha256="0" * 64, bytes=1),
        params=params,
    )


def stage_trial(run: Run, witness_dir: Path, *, rc: int = 0, wall: float = 2580.0) -> None:
    trials = run.stage / "artifacts" / "trials"
    trials.mkdir(parents=True, exist_ok=True)
    (trials / "trials.json").write_text(
        json.dumps([{
            "run_id": "app-t1-build",
            "rc": rc,
            "wall": wall,
            "witness": str(witness_dir.relative_to(run.stage)),
        }]),
        encoding="utf-8",
    )


def test_score_round_prints_the_rulers_it_could_read(tmp_path: Path) -> None:
    run = make_run(tmp_path)
    root = tmp_path / "stage" / "artifacts" / "trials" / "app-t1-build" / "witness"
    write(
        root / "docs" / "features" / "svc" / "policy-format.md",
        "---\ntype: concept\nslug: policy-format\ntitle: Policy format\n---\n"
        "# Policy format\n",
    )
    write(
        root / "docs" / "features" / "svc" / "coverage.json",
        json.dumps({"covered": 3, "total": 4}),
    )
    stage_trial(run, root)

    score = okfbuild.score_round(run, fixture())
    assert score.headline.startswith("book built: doctor ")
    assert "coverage 3/4" in score.headline
    assert "rc 0 in 43m" in score.headline
    assert not score.caveats
    assert score.data["coverage"] == {"covered": 3, "total": 4}


def test_score_round_renders_blank_for_what_it_could_not_read(tmp_path: Path) -> None:
    run = make_run(tmp_path)
    root = tmp_path / "stage" / "artifacts" / "trials" / "app-t1-build" / "witness"
    root.mkdir(parents=True)
    stage_trial(run, root, rc=7)

    score = okfbuild.score_round(run, fixture())
    assert f"doctor {BLANK}" in score.headline
    assert f"fmt {BLANK}" in score.headline
    assert f"coverage {BLANK}" in score.headline
    assert f"obligations {BLANK}" in score.headline
    assert "rc 7" in score.headline
    assert score.caveats and "rc 7" in score.caveats[0]


def test_score_round_without_a_ledger_says_so(tmp_path: Path) -> None:
    score = okfbuild.score_round(make_run(tmp_path), fixture())
    assert score.headline == "no build recorded — the round did not reach a run"
