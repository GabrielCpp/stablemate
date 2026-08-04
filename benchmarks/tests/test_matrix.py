"""Tests for the model-set matrix.

The matrix exists to compare configurations, so its trustworthy-ness rests entirely on
what it holds constant. These cover exactly that, and nothing about table formatting:

* a set's models beat the spec's — the spec is the benchmark, the set is the experiment;
* two sets driving one spec write to different places, or the last one to finish silently
  becomes all of them;
* the judge is pinned and does NOT follow the backend a set runs its workflows on, which
  is the defect that would make every delta measure the instrument;
* a duplicate set label is refused, because cells are keyed by label;
* gold is refused when the workflow source, the backlog or the judge moved under it;
* a per-bullet delta is computed against gold rather than against the mean, since two sets
  can tie on the headline having failed on disjoint bullets.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest
import yaml


def _load(name: str):
    path = Path(__file__).parents[1] / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    # A real file on disk always yields both; the import machinery answers None only for
    # the cases this is not (a namespace package, an unimportable path).
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


bench = _load("bench")
matrix = _load("matrix")


SETS = {
    "judge": {"cli": "claude", "model": "opus"},
    "gold": "gold",
    "sets": [
        {"label": "gold", "cli": "claude",
         "power": {"high": {"claude": {"model": "opus"}}}},
        {"label": "cheap", "cli": "opencode",
         "power": {"high": {"opencode": {"model": "qwen3.6-27b"}}}},
    ],
    "tasks": [],
}


@pytest.fixture
def sets_file(tmp_path: Path):
    def write(**overrides) -> Path:
        p = tmp_path / "sets.yml"
        p.write_text(yaml.safe_dump({**SETS, **overrides}), encoding="utf-8")
        return p
    return write


# ── The spec stays fixed; the set is what varies ──────────────────────────────────────


@pytest.fixture
def spec_file(tmp_path: Path) -> Path:
    p = tmp_path / "bench.yml"
    p.write_text(yaml.safe_dump({
        "target": str(tmp_path / "repo"),
        "surfaces": [{"service": "api", "service_root": "api"}],
        # The task set pins a cheap tier so its runs fit inside an hour. A set must be
        # able to overrule that — otherwise the experiment cannot reach the tier it is
        # about, and every cell would silently measure the spec's budget model.
        "power": {"high": {"claude": {"model": "sonnet", "effort": "low"}},
                  "low": {"claude": {"model": "haiku"}}},
        "judge": {},
    }), encoding="utf-8")
    return p


def test_a_sets_power_overlays_the_specs(spec_file: Path, monkeypatch):
    monkeypatch.setenv("BENCH_POWER",
                       json.dumps({"high": {"opencode": {"model": "qwen3.6-27b"}}}))
    spec = bench.load_spec(spec_file)
    assert spec.power["high"] == {"claude": {"model": "sonnet", "effort": "low"},
                                  "opencode": {"model": "qwen3.6-27b"}}
    # A tier the set says nothing about keeps the spec's value rather than vanishing.
    assert spec.power["low"] == {"claude": {"model": "haiku"}}


def test_a_spec_without_a_set_is_unchanged(spec_file: Path, monkeypatch):
    monkeypatch.delenv("BENCH_POWER", raising=False)
    monkeypatch.delenv("BENCH_RUNS", raising=False)
    spec = bench.load_spec(spec_file)
    assert spec.power == {"high": {"claude": {"model": "sonnet", "effort": "low"}},
                          "low": {"claude": {"model": "haiku"}}}
    assert spec.logs == spec_file.parent / ".runs"
    assert spec.label == ""


def test_two_sets_do_not_share_a_runs_dir(spec_file: Path, tmp_path: Path, monkeypatch):
    dirs = set()
    for label in ("gold", "cheap"):
        monkeypatch.setenv("BENCH_SET", label)
        monkeypatch.setenv("BENCH_RUNS", str(tmp_path / label / ".runs"))
        spec = bench.load_spec(spec_file)
        assert spec.label == label
        dirs.add(spec.logs)
    assert len(dirs) == 2


def test_a_malformed_override_is_fatal_not_empty(spec_file: Path, monkeypatch):
    # Silently empty would mean the run used the operator's ambient config while
    # producing a scorecard indistinguishable from a real one.
    monkeypatch.setenv("BENCH_POWER", "{not json")
    with pytest.raises(SystemExit, match="BENCH_POWER"):
        bench.load_spec(spec_file)
    monkeypatch.setenv("BENCH_POWER", '["a", "list"]')
    with pytest.raises(SystemExit, match="must be a JSON object"):
        bench.load_spec(spec_file)


# ── The judge is the instrument, so it must not vary with what it measures ────────────


def test_the_judge_ignores_the_backend_the_set_runs_on(spec_file: Path, monkeypatch):
    monkeypatch.setenv("AGENT_CLI", "opencode")          # what the SET runs its work on
    monkeypatch.setenv("BENCH_JUDGE", json.dumps({"cli": "claude", "model": "opus"}))
    spec = bench.load_spec(spec_file)

    asked: list[str | None] = []
    monkeypatch.setattr(bench, "get_backend",
                        lambda name=None: asked.append(name) or _FakeBackend())
    monkeypatch.setattr(bench, "judge_one", lambda *a, **k: {})
    bench.judge_backlog(spec, [], jobs=1)
    assert asked == ["claude"]


def test_an_unpinned_judge_still_falls_back(spec_file: Path, monkeypatch):
    monkeypatch.delenv("BENCH_JUDGE", raising=False)
    spec = bench.load_spec(spec_file)
    asked: list[str | None] = []
    monkeypatch.setattr(bench, "get_backend",
                        lambda name=None: asked.append(name) or _FakeBackend())
    monkeypatch.setattr(bench, "judge_one", lambda *a, **k: {})
    bench.judge_backlog(spec, [], jobs=1)
    assert asked == [None]  # get_backend's own AGENT_CLI → claude ladder, unchanged


class _FakeBackend:
    name = "fake"

    def run_turn(self, *a, **k) -> str:
        return ""


def test_sets_yml_requires_a_pinned_judge(sets_file):
    with pytest.raises(SystemExit, match="judge.cli"):
        matrix.load_matrix(sets_file(judge={"model": "opus"}))


# ── Cells are keyed by label ──────────────────────────────────────────────────────────


def test_a_duplicate_label_is_refused(sets_file):
    dupe = [*SETS["sets"], {"label": "cheap", "cli": "aider",
                            "power": {"high": {"aider": {"model": "x"}}}}]
    with pytest.raises(SystemExit, match="duplicate set label"):
        matrix.load_matrix(sets_file(sets=dupe))


def test_a_set_without_a_power_map_is_refused(sets_file):
    with pytest.raises(SystemExit, match="no `power`"):
        matrix.load_matrix(sets_file(sets=[{"label": "bare", "cli": "claude"}]))


def test_an_unknown_gold_is_caught_at_load(sets_file):
    with pytest.raises(SystemExit, match="no set 'nope'"):
        matrix.load_matrix(sets_file(gold="nope"))


def test_a_set_carries_its_whole_mapping_not_a_model_name(sets_file):
    mx = matrix.load_matrix(sets_file())
    cheap = mx.set("cheap")
    assert cheap.env() == {"AGENT_CLI": "opencode", "BENCH_SET": "cheap",
                           "BENCH_POWER": json.dumps(cheap.power)}


# ── Gold is frozen, and refused when the ground under it moved ────────────────────────


def _freeze(monkeypatch, tmp_path: Path, mx, task: str, **manifest) -> None:
    monkeypatch.setattr(matrix, "DATA", tmp_path / "data")
    cell = matrix.cell_dir(mx.gold, task)
    cell.mkdir(parents=True, exist_ok=True)
    base = {"workflow_sha": "abc123", "spec_sha": "deadbeef", "judge": mx.judge,
            "finished_at": "2026-08-03T00:00:00+00:00", "satisfaction_pct": 61.1}
    (cell / "manifest.json").write_text(json.dumps({**base, **manifest}), encoding="utf-8")


@pytest.fixture
def frozen(sets_file, tmp_path: Path, monkeypatch):
    spec = tmp_path / "tasks" / "demo" / "bench.yml"
    spec.parent.mkdir(parents=True)
    spec.write_text("target: /tmp/x\nsurfaces: [{service: api, service_root: api}]\n",
                    encoding="utf-8")
    mx = matrix.load_matrix(sets_file(tasks=[str(spec)]))
    monkeypatch.setattr(matrix, "workflow_sha", lambda: "abc123")
    monkeypatch.setattr(matrix, "spec_sha", lambda _p: "deadbeef")
    return mx, tmp_path, monkeypatch


def test_a_current_gold_is_usable(frozen):
    mx, tmp_path, monkeypatch = frozen
    _freeze(monkeypatch, tmp_path, mx, "demo")
    assert matrix.gold_staleness(mx, "demo") == ""


def test_gold_is_refused_when_the_workflow_moved(frozen):
    mx, tmp_path, monkeypatch = frozen
    _freeze(monkeypatch, tmp_path, mx, "demo", workflow_sha="999999")
    assert "workflow" in matrix.gold_staleness(mx, "demo")


def test_gold_is_refused_when_the_backlog_moved(frozen):
    mx, tmp_path, monkeypatch = frozen
    _freeze(monkeypatch, tmp_path, mx, "demo", spec_sha="different")
    assert "spec/backlog" in matrix.gold_staleness(mx, "demo")


def test_gold_is_refused_when_the_judge_changed(frozen):
    mx, tmp_path, monkeypatch = frozen
    _freeze(monkeypatch, tmp_path, mx, "demo", judge={"cli": "aider", "model": "cheap"})
    assert "judge" in matrix.gold_staleness(mx, "demo")


def test_a_missing_gold_names_the_command_that_makes_one(frozen):
    mx, tmp_path, monkeypatch = frozen
    monkeypatch.setattr(matrix, "DATA", tmp_path / "data")
    assert "matrix.py gold --task demo" in matrix.gold_staleness(mx, "demo")


# ── A partial run is a result ─────────────────────────────────────────────────────────


def test_a_chain_that_failed_at_coder_still_counts_as_run():
    # Re-running it would discard the hour that bought the partial score.
    assert matrix.is_complete({"finished_at": "t", "satisfaction_pct": 12.0,
                               "phases": [{"name": "coder", "rc": 1}]})


def test_a_cell_with_no_score_is_not_complete():
    assert not matrix.is_complete({"finished_at": "t", "satisfaction_pct": None})
    assert not matrix.is_complete({"satisfaction_pct": 50.0})
    assert not matrix.is_complete(None)


# ── The report subtracts gold per bullet, not on the mean ─────────────────────────────


def test_per_bullet_deltas_are_against_gold(sets_file, tmp_path: Path, monkeypatch):
    mx = matrix.load_matrix(sets_file())
    monkeypatch.setattr(matrix, "DATA", tmp_path / "data")
    for label, levels in (("gold", {"a": 3, "b": 2}), ("cheap", {"a": 1, "b": 3})):
        runs = matrix.cell_dir(label, "demo") / ".runs"
        runs.mkdir(parents=True)
        (runs / "scorecard.json").write_text(json.dumps({
            "satisfaction_pct": round(sum(levels.values()) / (3 * len(levels)) * 100, 1),
            "bullets": [{"id": k, "level": v} for k, v in levels.items()],
        }), encoding="utf-8")
        matrix.write_manifest(label, "demo", {"phases": [], "workflow_sha": "abc123",
                                              "spec_sha": "deadbeef"})
    report = matrix.render_report(mx, "demo")
    assert "| `a` | 3 | 1 (-2) |" in report   # cheap lost two levels on `a`
    assert "| `b` | 2 | 3 (+1) |" in report   # and gained one on `b`
