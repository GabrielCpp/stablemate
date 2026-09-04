"""Integrity tests for the frozen tally-cli mutant corpus.

The corpus is curated once and never re-litigated per run, which makes every one of its
claims a thing that can rot silently: a variant that drifts back to byte-identity with
its story image scores as a kill QA never earned; a pool-A bullet that stops being owed
turns its row `inconclusive` forever; a discard whose directory reappears is half a
mutant nobody can classify. This file re-states each curation rule from the manifest
header as a check, in the `test_tally_cli_app.py` pattern.

The expensive property — that every kept mutant is *distinguishable by observation* —
is re-proved here with the same battery the curation gate used, frozen beside the corpus
at `mutants/battery.py`. Each mutant's seeded tree is materialized once at module scope
and shared by the run-check, the owedness check and the battery check, so the round trip
stays affordable while still exercising exactly what `run_round` will do to it.
"""

from __future__ import annotations

import contextlib
import importlib.util
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType

import pytest
import yaml
from paddock.registry import REGISTRY

pytestmark = pytest.mark.mutation

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
mutants = _load("_mutants", DATA / "tasks" / "_mutants.py")
TASK = _load("_tally_cli_mutants_task", DATA / "tasks" / "tally_cli_mutants.py")

# The battery lives *inside* the captured app tree, and `seed capture` refuses a tree
# holding a `__pycache__` — so its import may not write bytecode next to it.
_saved_dont_write = sys.dont_write_bytecode
sys.dont_write_bytecode = True
try:
    battery = _load("_tally_battery", APP / "mutants" / "battery.py")
finally:
    sys.dont_write_bytecode = _saved_dont_write


def rows() -> list[dict[str, str]]:
    return mutants.load_mutants(APP)


def row_ids() -> list[str]:
    return [str(row["id"]) for row in rows()]


def pool_a() -> list[dict[str, str]]:
    return [row for row in rows() if row["pool"] == "A"]


# ── the corpus as a whole ─────────────────────────────────────────────────────────────


def test_the_manifest_validates() -> None:
    """`validate_mutants` is what `run_round` refuses on; a red row here fails the round
    before any trial spends a budget on it."""
    assert mutants.validate_mutants(APP) == []


def test_the_corpus_names_its_mutants_once() -> None:
    ids = row_ids()
    assert len(ids) == len(set(ids)), ids
    dirs = {
        path.name
        for path in (APP / "mutants").iterdir()
        if path.is_dir() and path.name != "__pycache__"
    }
    assert dirs == set(ids), "every variant directory is a kept mutant, and vice versa"


def test_both_pools_are_populated() -> None:
    """The pin-rate gap is a difference of two rates; an empty pool makes one of them
    undefined and the headline a lie about the other."""
    pools = {str(row["pool"]) for row in rows()}
    assert pools == {"A", "B"}, pools


def test_discards_are_logged_and_shipped_nowhere() -> None:
    discards = mutants.load_discards(APP)
    assert discards, "the gate discarded candidates; a corpus with none has lost its log"
    for row in discards:
        assert str(row["reason"]).strip(), row
        assert not (APP / "mutants" / str(row["id"])).exists(), (
            f"{row['id']}: discarded but its variant directory is still in the corpus"
        )


def test_pool_a_avoids_the_answer_key() -> None:
    """A pool-A bullet repeating a defects.yml obligation measures the `-qa` fixture
    twice and the book's marginal value zero times."""
    defects = yaml.safe_load((APP / "defects.yml").read_text(encoding="utf-8"))["defects"]
    keyed = {str(row["obligation"]) for row in defects}
    bullets = {str(row["bullet"]) for row in pool_a()}
    assert not (bullets & keyed), bullets & keyed


def test_the_task_points_at_the_app_and_runs_the_whole_corpus() -> None:
    assert DATA / TASK.FIXTURE.app == APP
    assert TASK.FIXTURE.repo_dir == "tally-cli"
    # An empty tuple means `select_mutants` returns every row — the corpus is the round.
    assert TASK.FIXTURE.defects == ()


# ── the variants ──────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("row", rows(), ids=row_ids())
def test_every_variant_is_python_that_compiles(row: dict[str, str]) -> None:
    """A variant that cannot compile dies at import, which any plan's first `qa.require`
    catches — a kill that measures nothing about detection."""
    variant = mutants.variant_path(APP, row)
    assert str(row["path"]).endswith(".py"), row
    compile(variant.read_text(encoding="utf-8"), str(variant), "exec")


@pytest.mark.parametrize("row", rows(), ids=row_ids())
def test_every_variant_differs_from_its_story_post_image(row: dict[str, str]) -> None:
    """Whole-file overwrite makes an identical variant dangerous rather than useless:
    nothing errors, the trial runs, and the row scores as a kill QA never earned. The
    comparison is against the story's own `post/` image, not the finished app — two of
    the three source files keep growing after their first story."""
    correct = frozen.story_image(APP, row["story"], row["path"], phase="post").read_bytes()
    assert mutants.variant_path(APP, row).read_bytes() != correct


@pytest.mark.parametrize("row", rows(), ids=row_ids())
def test_every_variant_defines_the_symbols_it_claims(row: dict[str, str]) -> None:
    """The `symbols:` list is what a triage session greps for; a renamed function that
    nobody re-recorded makes the manifest describe a mutation that is not there."""
    text = mutants.variant_path(APP, row).read_text(encoding="utf-8")
    for symbol in row["symbols"]:
        assert f"def {symbol}(" in text, f"{row['id']}: {symbol} not defined in the variant"


# ── the seeded trees: run, owedness, distinguishability ───────────────────────────────


@pytest.fixture(scope="module")
def seeded_trees(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    """One materialized-and-seeded tree per mutant — exactly what `run_round` hands the
    trial — shared by every check below so the corpus round-trip stays affordable."""
    root = tmp_path_factory.mktemp("seeded")
    trees: dict[str, Path] = {}
    for row in rows():
        dest = frozen.materialize(APP, str(row["story"]), root / str(row["id"]) / "tally-cli")
        mutants.seed_mutant(APP, row, dest)
        trees[str(row["id"])] = dest
    return trees


@pytest.fixture(scope="module")
def control_transcripts(tmp_path_factory: pytest.TempPathFactory) -> dict[str, str]:
    """The battery's word on each unmutated story image, computed once per story."""
    root = tmp_path_factory.mktemp("control")
    stories = {str(row["story"]) for row in rows()}
    return {
        story: battery.transcript(frozen.materialize(APP, story, root / story / "tally-cli"))
        for story in sorted(stories)
    }


@pytest.mark.parametrize("row", rows(), ids=row_ids())
def test_every_mutant_still_runs_the_product(
    row: dict[str, str], seeded_trees: dict[str, Path]
) -> None:
    """The corpus's central claim stated mechanically: every mutant leaves a program that
    starts and parses its arguments — QA has to read what it did to find it."""
    started = subprocess.run(
        [sys.executable, "-m", "tally", "--help"],
        cwd=seeded_trees[str(row["id"])],
        capture_output=True, text=True, check=False, timeout=60,
    )
    assert started.returncode == 0, started.stderr[-2000:]


@pytest.mark.parametrize("row", pool_a(), ids=[str(row["id"]) for row in pool_a()])
def test_every_pool_a_bullet_is_owed_by_its_seeded_tree(
    row: dict[str, str], seeded_trees: dict[str, Path]
) -> None:
    """The relaxed pool-A rule's verifiable half: the bullet each mutant claims to
    violate mints an obligation the trial is *required* to evidence, computed from the
    seeded tree the way QA computes it. A bullet demoted to context-only turns the row
    `inconclusive` forever, looking exactly like a QA lane that never answered."""
    from ostler.qa.context import build_context  # noqa: PLC0415 - heavy, and only for this

    context = build_context(seeded_trees[str(row["id"])], base="HEAD", head="WORKTREE")
    owed = {
        obligation["id"]
        for obligation in context["obligations"]
        if obligation.get("required", True)
    }
    assert row["bullet"] in owed, (
        f"{row['id']}: {row['bullet']} is not owed after seeding ({len(owed)} owed)"
    )


@pytest.mark.parametrize("row", rows(), ids=row_ids())
def test_the_battery_distinguishes_every_mutant_from_control(
    row: dict[str, str],
    seeded_trees: dict[str, Path],
    control_transcripts: dict[str, str],
) -> None:
    """The equivalence gate, re-run against the frozen corpus. A mutant whose transcript
    has drifted back to equality with its story image is indistinguishable by
    observation and belongs under `discards:`, not in the denominator as a survivor no
    triage could ever retire."""
    got = battery.transcript(seeded_trees[str(row["id"])])
    assert got != control_transcripts[str(row["story"])], (
        f"{row['id']}: battery transcript equal to the {row['story']} control"
    )
