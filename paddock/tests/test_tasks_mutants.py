"""The mutant corpus: loading, selecting, and the pool a mutant must name."""

from __future__ import annotations

from pathlib import Path

import pytest
from fakes import fake_run

from paddock.tasks import mutants
from paddock.tasks.stablemate import TrialError

CORPUS = """mutants:
  - id: M1
    story: S-1
    path: a.py
    pool: A
    bullet: x
    behavior: flips a sign
  - id: M2
    story: S-1
    path: b.py
    pool: B
    behavior: drops a check
discards:
  - id: M3
    reason: equivalent
"""


def write_corpus(app: Path, body: str = CORPUS) -> Path:
    app.mkdir(parents=True, exist_ok=True)
    (app / "mutants.yml").write_text(body, encoding="utf-8")
    return app


def test_load_mutants_reads_the_rows_and_refuses_an_unknown_pool(tmp_path: Path) -> None:
    assert [row["id"] for row in mutants.load_mutants(write_corpus(tmp_path / "app"))] == ["M1", "M2"]
    with pytest.raises(TrialError, match="the pools are A, B"):
        mutants.load_mutants(write_corpus(tmp_path / "bad", CORPUS.replace("pool: B", "pool: Z")))


def test_a_missing_corpus_is_named(tmp_path: Path) -> None:
    with pytest.raises(TrialError, match="no mutant corpus"):
        mutants.load_manifest(tmp_path)


def test_select_mutants_keeps_the_asked_order_and_names_a_stranger(tmp_path: Path) -> None:
    app = write_corpus(tmp_path / "app")
    assert [row["id"] for row in mutants.select_mutants(app, ("M2", "M1"))] == ["M2", "M1"]
    with pytest.raises(TrialError, match="no such mutant"):
        mutants.select_mutants(app, ("M9",))


def test_the_corpus_is_read_beside_the_benchmarks_tasks(tmp_path: Path) -> None:
    run = fake_run(tmp_path)
    fixture = mutants.fz.Fixture(app="apps/x", repo_dir="x")
    with pytest.raises(TrialError, match="no mutant corpus under"):
        mutants.corpus_dir(run, fixture)
    write_corpus(run.benchmark.root / "apps" / "x")
    assert mutants.corpus_dir(run, fixture) == run.benchmark.root / "apps" / "x"
