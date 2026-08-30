"""The mutant round's pure machinery: corpus schema, classification, and the pin-rate gap.

Everything here is literal — no docker, no agent, no seed. The corpus rules matter most
where they fail silently: a mutant outside its story's diff scores as a survivor against
QA for a fixture bug, a discard without a reason inflates the kill rate invisibly, and a
triage citation the witness's book does not back would make survivors green by editing
YAML. Each of those is a named `validate_mutants` problem or a classifier branch, and
each gets a test, because nothing else fails loudly when one regresses.
"""

from __future__ import annotations

import contextlib
import importlib.util
import json
import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest
import yaml

from paddock import loader
from paddock.pointer import Pointer
from paddock.runner import Run

DATA = Path(__file__).parents[1]


@contextlib.contextmanager
def _tasks_dir_on_path() -> Iterator[None]:
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
        sys.modules[name] = module
        spec.loader.exec_module(module)
    return module


mutants = _load("_mutants")
TrialError = mutants.TrialError


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def manifest(app: Path, data: dict[str, Any]) -> None:
    write(app / "mutants.yml", yaml.safe_dump(data))


def app_tree(tmp_path: Path) -> Path:
    """A minimal valid corpus: one story, one pool-A and one pool-B mutant, one discard."""
    app = tmp_path / "app"
    write(app / "stories" / "s1" / "diff.yml", "changed:\n- tally/count.py\n")
    write(app / "tally" / "count.py", "COUNT = 1\n")
    write(app / "mutants" / "M1" / "tally" / "count.py", "COUNT = 2\n")
    write(app / "mutants" / "M2" / "tally" / "count.py", "COUNT = 0\n")
    manifest(app, {
        "mutants": [
            {
                "id": "M1", "pool": "A", "story": "s1", "path": "tally/count.py",
                "symbols": ["tally/count.py::COUNT"], "bullet": "tally-count-b1",
                "behavior": "the running total starts one too high",
            },
            {
                "id": "M2", "pool": "B", "story": "s1", "path": "tally/count.py",
                "symbols": ["tally/count.py::COUNT"],
                "behavior": "an empty ledger reports minus one entries",
            },
        ],
        "discards": [
            {"id": "M3", "reason": "equivalent — no battery run distinguishes it from control"},
        ],
    })
    return app


# ── the corpus ────────────────────────────────────────────────────────────────────────


def test_a_good_corpus_validates_clean(tmp_path: Path) -> None:
    assert mutants.validate_mutants(app_tree(tmp_path)) == []


def test_no_manifest_and_no_rows_both_refuse_to_run(tmp_path: Path) -> None:
    with pytest.raises(TrialError, match="no mutant corpus"):
        mutants.load_mutants(tmp_path)
    manifest(tmp_path, {"mutants": []})
    with pytest.raises(TrialError, match="lists no mutants"):
        mutants.load_mutants(tmp_path)


def test_a_pool_outside_the_two_is_refused(tmp_path: Path) -> None:
    app = app_tree(tmp_path)
    manifest(app, {"mutants": [{"id": "M9", "pool": "C", "story": "s1", "path": "x"}]})
    with pytest.raises(TrialError, match="pool: 'C'"):
        mutants.load_mutants(app)


def test_every_way_the_corpus_lies_is_named(tmp_path: Path) -> None:
    """One broken manifest, every problem class in it, all reported at once."""
    app = app_tree(tmp_path)
    manifest(app, {
        "mutants": [
            # Valid, and then duplicated — the second M1 is the finding.
            {"id": "M1", "pool": "A", "story": "s1", "path": "tally/count.py",
             "bullet": "b1", "behavior": "off by one"},
            {"id": "M1", "pool": "A", "story": "s1", "path": "tally/count.py",
             "bullet": "b1", "behavior": "off by one"},
            # Pool A with no bullet, and no behavior line either.
            {"id": "M4", "pool": "A", "story": "s1", "path": "tally/count.py"},
            # A story the app does not have.
            {"id": "M5", "pool": "B", "story": "ghost", "path": "tally/count.py",
             "behavior": "x"},
            # In the tree but outside the story's diff — the before-tree trap.
            {"id": "M6", "pool": "B", "story": "s1", "path": "tally/other.py",
             "behavior": "x"},
            # In the diff but with no variant on disk.
            {"id": "M7", "pool": "B", "story": "s1", "path": "tally/count.py",
             "behavior": "x"},
        ],
        "discards": [
            {"id": "M8"},          # no reason
            {"id": "M2"},          # discarded, and its variant directory still exists
            {"id": "M1"},          # discarded while still listed as a mutant
        ],
    })
    problems = "\n".join(mutants.validate_mutants(app))
    assert "M1: duplicate mutant id" in problems
    assert "M4: pool A without a bullet:" in problems
    assert "M4: no behavior line" in problems
    assert "M5: story 'ghost'" in problems
    assert "M6: tally/other.py is not in s1's diff" in problems
    assert "M7: no variant at" in problems
    assert "M8: discarded without a reason" in problems
    assert "M2: discarded but its variant directory" in problems
    assert "M1: discarded and still listed as a mutant" in problems


def test_discards_are_read_but_never_run(tmp_path: Path) -> None:
    app = app_tree(tmp_path)
    assert [row["id"] for row in mutants.load_discards(app)] == ["M3"]
    assert [row["id"] for row in mutants.load_mutants(app)] == ["M1", "M2"]


def test_select_narrows_and_refuses_the_unknown(tmp_path: Path) -> None:
    app = app_tree(tmp_path)
    assert [r["id"] for r in mutants.select_mutants(app, ())] == ["M1", "M2"]
    assert [r["id"] for r in mutants.select_mutants(app, ("M2",))] == ["M2"]
    with pytest.raises(TrialError, match="no such mutant"):
        mutants.select_mutants(app, ("M9",))


def test_seed_overwrites_the_target_whole(tmp_path: Path) -> None:
    app = app_tree(tmp_path)
    repo = tmp_path / "repo"
    write(repo / "tally" / "count.py", "COUNT = 1\n")
    row = mutants.load_mutants(app)[0]
    mutants.seed_mutant(app, row, repo)
    assert (repo / "tally" / "count.py").read_text(encoding="utf-8") == "COUNT = 2\n"


def test_seed_refuses_a_target_missing_from_the_tree(tmp_path: Path) -> None:
    app = app_tree(tmp_path)
    repo = tmp_path / "repo"
    repo.mkdir()
    with pytest.raises(TrialError, match="not in the materialized tree"):
        mutants.seed_mutant(app, mutants.load_mutants(app)[0], repo)


def test_seed_refuses_a_path_outside_the_story_diff(tmp_path: Path) -> None:
    app = app_tree(tmp_path)
    row = {**mutants.load_mutants(app)[0], "path": "tally/other.py"}
    write(app / "mutants" / "M1" / "tally" / "other.py", "x = 1\n")
    repo = tmp_path / "repo"
    write(repo / "tally" / "other.py", "x = 0\n")
    with pytest.raises(TrialError, match="not in s1's diff"):
        mutants.seed_mutant(app, row, repo)


def test_survival_is_byte_equality_with_the_variant(tmp_path: Path) -> None:
    app = app_tree(tmp_path)
    row = mutants.load_mutants(app)[0]
    witness = tmp_path / "witness"
    write(witness / "tally" / "count.py", "COUNT = 2\n")
    assert mutants.mutant_survived(app, row, witness) is True
    write(witness / "tally" / "count.py", "COUNT = 1\n")
    assert mutants.mutant_survived(app, row, witness) is False
    (witness / "tally" / "count.py").unlink()
    assert mutants.mutant_survived(app, row, witness) is False


# ── the don't-care vocabulary ─────────────────────────────────────────────────────────


def book(tmp_path: Path) -> Path:
    """A loadable one-screen book carrying a cited `unspecified:` bullet."""
    root = tmp_path / "book"
    write(root / "docs" / "decisions" / "sort-order.md", "# Sort order\n\nUnordered.\n")
    write(
        root / "docs" / "features" / "svc" / "gui" / "screens" / "widget.md",
        "---\ntype: screen\nslug: widget\ntitle: Widget\n---\n# Widget\n\n"
        "- route: `/widget`\n"
        "- unspecified: result order ([sort order](../../../../decisions/sort-order.md))\n",
    )
    return root


def test_dont_cares_reads_the_witness_book(tmp_path: Path) -> None:
    cares = mutants.dont_cares(book(tmp_path))
    assert len(cares) == 1
    ((node, values),) = cares.items()
    assert "widget" in node
    assert any("result order" in value for value in values)


def test_dont_cares_degrades_to_empty_never_a_crash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An ostler without the A4 vocabulary, and a book that will not load, both read as
    `{}` — a triage citation then scores survivor, never an exception."""
    from ostler import registry

    assert mutants.dont_cares(tmp_path / "nothing-here") == {}
    monkeypatch.setattr(registry, "SHARED_ADVISORY_KEYS", ())
    assert mutants.dont_cares(book(tmp_path)) == {}


# ── classification ────────────────────────────────────────────────────────────────────


ROW = {"id": "M1", "pool": "A", "story": "s1", "path": "tally/count.py"}
CITED = {**ROW, "unspecified": "screen:widget"}
CARES = {"screen:widget": ["result order"]}


def test_a_contradicted_obligation_kills_and_names_the_bullet() -> None:
    statuses = {"b2": "covered", "b1": "contradicted"}
    assert mutants.classify_mutant(ROW, statuses, {}, survived=True, cares={}) == (
        "killed", "b1",
    )


def test_an_audit_refutation_kills() -> None:
    verdict = mutants.classify_mutant(
        ROW, {"b1": "covered"}, {"verdict": "refuted"}, survived=True, cares={},
    )
    assert verdict == ("killed", "audit refutation")


def test_a_repaired_mutant_is_a_kill_even_with_no_evidence_map() -> None:
    """The byte witness outranks the map's absence: a flow that repaired the seeded file
    demonstrably acted on it, whatever else it failed to write."""
    verdict = mutants.classify_mutant(ROW, None, {}, survived=False, cares={})
    assert verdict == ("killed", "mutant repaired")


def test_no_evidence_map_is_inconclusive_not_a_survivor() -> None:
    verdict = mutants.classify_mutant(ROW, None, {}, survived=True, cares={})
    assert verdict == ("inconclusive", "no evidence map")


def test_a_backed_citation_is_resolved_by_design() -> None:
    verdict = mutants.classify_mutant(CITED, {"b1": "covered"}, {}, survived=True, cares=CARES)
    assert verdict == ("resolved", "don't-care on screen:widget")


def test_a_citation_the_book_does_not_back_is_a_survivor_with_its_staleness_named() -> None:
    """Editing the manifest must not be a way to make survivors green: the resolution is
    believed only against the book the trial actually ran under."""
    verdict, because = mutants.classify_mutant(
        CITED, {"b1": "covered"}, {}, survived=True, cares={},
    )
    assert verdict == "survivor"
    assert "screen:widget" in because and "no unspecified" in because


def test_a_clean_run_over_a_surviving_mutant_is_a_survivor() -> None:
    verdict = mutants.classify_mutant(ROW, {"b1": "covered"}, {}, survived=True, cares={})
    assert verdict == ("survivor", "ran clean")


# ── the pin rate ──────────────────────────────────────────────────────────────────────


def trial(pool: str, verdict: str) -> dict[str, str]:
    return {"pool": pool, "verdict": verdict}


def test_pin_rates_exclude_resolutions_from_the_denominator() -> None:
    rates = mutants.pin_rates([
        trial("A", "killed"), trial("A", "killed"), trial("A", "survivor"),
        trial("B", "killed"), trial("B", "resolved"), trial("B", "survivor"),
    ])
    assert rates["pools"]["A"]["rate"] == pytest.approx(2 / 3)
    assert rates["pools"]["B"]["rate"] == pytest.approx(1 / 2)
    assert rates["gap"] == pytest.approx(2 / 3 - 1 / 2)


def test_an_empty_pool_is_blank_never_zero() -> None:
    rates = mutants.pin_rates([trial("A", "killed")])
    assert rates["pools"]["A"]["rate"] == 1.0
    assert rates["pools"]["B"]["rate"] is None
    assert rates["gap"] is None


def test_an_inconclusive_trial_blanks_its_pools_rate() -> None:
    """A rate computed over an outage is a number about this machine — the pool goes
    blank, and the headline says how many trials never answered."""
    rates = mutants.pin_rates([
        trial("A", "killed"), trial("A", "inconclusive"),
        trial("B", "killed"),
    ])
    assert rates["pools"]["A"]["rate"] is None
    assert rates["pools"]["B"]["rate"] == 1.0
    assert rates["gap"] is None


def test_a_pool_consumed_whole_by_resolutions_is_blank() -> None:
    rates = mutants.pin_rates([trial("A", "resolved"), trial("B", "killed")])
    assert rates["pools"]["A"]["rate"] is None
    assert rates["gap"] is None


def test_the_headline_reads_like_the_plan_says_it_should() -> None:
    line = mutants.headline([
        trial("A", "killed"), trial("A", "killed"), trial("A", "survivor"),
        trial("B", "killed"), trial("B", "resolved"), trial("B", "survivor"),
    ])
    assert line == "pin-gap +0.17  (A 2/3 killed, B 1/2, 2 survivors, 1 resolved-by-design)"


def test_the_headline_prints_blanks_and_flags_the_outage() -> None:
    line = mutants.headline([trial("A", "killed"), trial("A", "inconclusive")])
    assert line.startswith("pin-gap –")
    assert "B –" in line
    assert "inconclusive 1" in line


# ── the round ─────────────────────────────────────────────────────────────────────────


def make_run(tmp_path: Path, **params: str) -> Run:
    return Run(
        task=loader.load_path(DATA / "tasks" / "expense_split.py"),
        label="t1",
        stage=tmp_path / "stage",
        repo=tmp_path / "stage" / "app",
        scratch=tmp_path / "scratch",
        config=tmp_path / "config.toml",
        data_dir=tmp_path,
        store=tmp_path / "store",
        seed=Pointer(name="app", repo_dir="app", sha256="0" * 64, bytes=1),
        params=params,
    )


def test_the_round_scopes_by_param_and_ledgers_the_mutant_shape(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One dry round: the QA lane gets the mutant's story and the audit-on flag, the run
    ids carry the `-mut-` spine, and the ledger lands in `mutants.json` with pool and
    bullet — everything `score_round` will later read back."""
    app_tree(tmp_path)
    run = make_run(tmp_path, mutants="M2")
    fixture = mutants.fz.Fixture(app="app", repo_dir="app", first_verdict=False)
    commands: list[tuple[str, ...]] = []

    def fake_cli(*argv: str, **_kwargs: object) -> SimpleNamespace:
        commands.append(argv)
        return SimpleNamespace(returncode=0)

    def fake_materialize(_source: Path, _story: str, dest: Path, *_a: object) -> Path:
        dest.mkdir(parents=True, exist_ok=True)
        return dest

    def fake_witness(_repo: Path, dest: Path, extra: tuple[str, ...] = ()) -> Path:
        dest.mkdir(parents=True, exist_ok=True)
        return dest

    monkeypatch.setattr(mutants, "stablemate_checkout", lambda _run: tmp_path / "sm")
    monkeypatch.setattr(mutants, "effective", lambda _run: tmp_path / "config.toml")
    monkeypatch.setattr(mutants, "pin_held", lambda _pinned: None)
    monkeypatch.setattr(mutants, "no_leaks", lambda *_a, **_k: contextlib.nullcontext())
    monkeypatch.setattr(mutants, "seed_mutant", lambda *_a: None)
    monkeypatch.setattr(mutants.fz, "materialize", fake_materialize)
    monkeypatch.setattr(mutants.fz, "reset_stack_state", lambda _repo: None)
    monkeypatch.setattr(mutants.fz, "capture_witness", fake_witness)
    monkeypatch.setattr(mutants.fx, "timing_of", lambda *_a: {})
    monkeypatch.setattr(mutants.fx, "laps_of", lambda *_a: {})
    monkeypatch.setattr(run, "cli", fake_cli)

    mutants.run_round(run, fixture)

    qa = next(argv for argv in commands if "qa" in argv)
    params = json.loads(qa[qa.index("--params") + 1])
    assert params["story"] == "s1"
    assert params["stop_at_first_verdict"] is False
    run_id = qa[qa.index("--run-id") + 1]
    assert "-mut-s1-M2-" in run_id
    ledger = json.loads(
        (run.stage / "artifacts" / "trials" / "mutants.json").read_text(encoding="utf-8")
    )
    assert [entry["mutant"] for entry in ledger] == ["M2"]
    assert ledger[0]["pool"] == "B"
    assert ledger[0]["bullet"] == ""
    assert ledger[0]["audit_turn"] is True


def test_an_invalid_corpus_stops_the_round_before_any_trial(tmp_path: Path) -> None:
    app = app_tree(tmp_path)
    manifest(app, {"mutants": [
        {"id": "M1", "pool": "A", "story": "s1", "path": "tally/count.py",
         "behavior": "off by one"},  # pool A, no bullet
    ]})
    with pytest.raises(TrialError, match="cannot be scored"):
        mutants.run_round(make_run(tmp_path), mutants.fz.Fixture(app="app", repo_dir="app"))
