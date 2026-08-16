"""`scripts/bench_ostler_doctor.py` + `make bench-doctor` — the doctor benchmark harness.

The point of the harness is that a timing anyone quotes can be re-derived by someone
else, so what these tests hold it to is the *decomposition* the cache increments are
judged on — `model.load` cold and warm, `doctor.run` cold and warm, the eight named
checks, the three components inside `_check_ui` — plus the book's shape, because a
timing with no shape beside it is comparable to nothing.

Three properties beyond "it prints numbers":

* the book is an argument with no default. The measured book lives outside this repo, so
  a `make bench-doctor` that quietly measures *something* is worse than one that stops;
* `--json` carries the same measurements as the table, so an increment's before/after is
  a diff and not a paragraph;
* the harness only measures. It edits no ostler module and changes no `doctor` verdict —
  a benchmark that perturbs what it times reports a number about itself.

The harness is run the way an operator runs it: as a subprocess, against a real book on
disk (the shared `repo` fixture, plus UI nodes so the shape counts are not all zero).
The assertions match label *names*, not layout: the harness may punctuate and nest its
report however it likes, as long as every measurement is findable and numeric.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import TypeGuard

import pytest

from ostler.cli import main as ostler_main
from ostler.model import load

from conftest import feature_md, write

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "bench_ostler_doctor.py"

#: Every phase the plan's decomposition names, in the spelling the plan uses. The table
#: and the JSON both have to cover all of them, or two runs are not comparable.
PHASES = ("model.load", "doctor.run")
CHECKS = (
    "_check_ui",
    "_ui_graph",
    "_check_conformance",
    "_check_reachability",
    "_check_locators",
    "_check_milestones",
    "_check_epic",
    "_check_frozen",
)
UI_COMPONENTS = ("_check_ui_file", "_check_code_grounding", "required-bullet")

#: Trailing key components a report is free to append to a measurement's name without
#: changing which measurement it is (`_check_ui_seconds`, `required_bullet_loop_ms`).
UNITS = frozenset({"s", "sec", "secs", "second", "seconds", "ms", "elapsed", "time",
                   "loop", "total", "count", "n", "num"})

SCREEN = """\
---
type: screen
slug: dash
title: Dashboard
---
# Dashboard

Shows the [rec](../../area/rec.md) feature.

## Components

### file-row
- selector: `.row`
"""


def _norm(text: str) -> str:
    """Lowercased, with every run of non-alphanumerics collapsed to `_`.

    So `model.load`, `model load` and `Model Load` all compare equal — the harness picks
    its own label punctuation without this suite dictating it.
    """
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def _leaves(value: object, prefix: str = "") -> list[tuple[str, object]]:
    """Every scalar in a nested JSON document, as (normalised key path, value)."""
    out: list[tuple[str, object]] = []
    if isinstance(value, dict):
        for key, sub in value.items():
            out.extend(_leaves(sub, f"{prefix}_{_norm(str(key))}"))
        return out
    if isinstance(value, list):
        for index, sub in enumerate(value):
            out.extend(_leaves(sub, f"{prefix}_{index}"))
        return out
    return [(prefix.strip("_"), value)]


def _numeric(value: object) -> TypeGuard[int | float]:
    """A JSON number — `True`/`False` are `int`s to Python and measurements to nobody."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _strip_units(path: str) -> str:
    parts = path.split("_")
    while len(parts) > 1 and parts[-1] in UNITS:
        parts.pop()
    return "_".join(parts)


def _timings(leaves: list[tuple[str, object]], *tokens: str) -> list[float]:
    """The numeric leaves naming this measurement and no narrower one.

    A leaf qualifies when its key path carries every token and *ends* with one of them
    (units aside) — which is what keeps `_check_ui` from also collecting `_check_ui_file`.
    """
    wanted = [_norm(t) for t in tokens]
    found = []
    for path, value in leaves:
        if not _numeric(value) or not all(t in path for t in wanted):
            continue
        tail = _strip_units(path)
        if any(tail.endswith(t) or tail.endswith(f"{t}s") for t in wanted):
            found.append(float(value))
    return found


def _require_timing(leaves: list[tuple[str, object]], *tokens: str) -> None:
    found = _timings(leaves, *tokens)
    keys = sorted(p for p, _ in leaves)
    assert found, f"no measurement for {' '.join(tokens)} among {keys}"
    assert all(t >= 0.0 for t in found), f"{tokens} reported a negative duration: {found}"


def _counts(leaves: list[tuple[str, object]], *patterns: str) -> list[float]:
    """Numeric leaves whose key path carries any of these spellings of one shape count."""
    return [float(v) for path, v in leaves if _numeric(v) and any(p in path for p in patterns)]


@pytest.fixture
def book(repo: Path) -> Path:
    """The shared fixture repo, plus a screen and a third feature doc.

    UI nodes and a link target are what make the shape counts non-trivial: a book with
    zero of both cannot tell "counted it" from "printed a zero".
    """
    write(repo / "docs/features/groom/gui/screens/dash.md", SCREEN)
    write(repo / "docs/features/area/rec3.md", feature_md("rec3", "Rec 3", area="area"))
    return repo


def _run_script(book: Path, *args: str, timeout: int = 900) -> subprocess.CompletedProcess[str]:
    assert SCRIPT.exists(), f"the benchmark harness is missing: {SCRIPT}"
    return subprocess.run(  # noqa: S603
        [sys.executable, str(SCRIPT), str(book), *args],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        stdin=subprocess.DEVNULL,
        timeout=timeout,
        check=False,
    )


def _run_make(*args: str, timeout: int = 900) -> subprocess.CompletedProcess[str]:
    make = shutil.which("make")
    assert make, "make is this repo's entry point for every dev tool; it must be on PATH"
    return subprocess.run(  # noqa: S603
        [make, "bench-doctor", *args],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        stdin=subprocess.DEVNULL,
        timeout=timeout,
        check=False,
    )


def _json_report(book: Path) -> dict:
    done = _run_script(book, "--json")
    assert done.returncode == 0, done.stderr or done.stdout
    report = json.loads(done.stdout)
    assert isinstance(report, dict), "a diffable report is one object, not a stream"
    return report


def test_make_bench_doctor_without_docs_refuses_and_measures_nothing():
    """No `DOCS=`, no default: the measured book cannot be guessed, so the target stops.

    A baked-in default is the failure this rules out — it would measure whatever happened
    to be there and report a number nobody could place.
    """
    done = _run_make()

    assert done.returncode != 0, done.stdout
    combined = done.stdout + done.stderr
    assert "DOCS" in combined, f"the failure has to name the missing argument: {combined!r}"
    # And nothing was measured on the way to failing.
    assert "model.load" not in combined and "doctor.run" not in combined, combined


def test_make_bench_doctor_with_docs_reports_the_whole_decomposition(book: Path):
    done = _run_make(f"DOCS={book}", timeout=1800)

    assert done.returncode == 0, done.stderr or done.stdout
    normalised = _norm(done.stdout)
    for label in (*PHASES, *CHECKS, *UI_COMPONENTS):
        assert _norm(label) in normalised, f"{label} missing from the table"
    assert "cold" in normalised and "warm" in normalised, done.stdout


def test_the_table_gives_every_phase_check_and_component_a_number(book: Path):
    done = _run_script(book)
    assert done.returncode == 0, done.stderr or done.stdout

    lines = done.stdout.splitlines()
    for label in (*PHASES, *CHECKS, *UI_COMPONENTS):
        token = _norm(label)
        rows = [line for line in lines if token in _norm(line)]
        assert rows, f"{label} has no row in the table:\n{done.stdout}"
        assert any(re.search(r"\d", row) for row in rows), f"{label}'s row carries no timing"


def test_json_carries_the_same_measurements_as_the_table(book: Path):
    leaves = _leaves(_json_report(book))

    for phase in PHASES:
        for temperature in ("cold", "warm"):
            _require_timing(leaves, phase, temperature)
    for label in (*CHECKS, *UI_COMPONENTS):
        _require_timing(leaves, label)


def test_json_reports_the_books_shape_beside_the_timings(book: Path):
    leaves = _leaves(_json_report(book))
    graph = load(book)
    markdown_files = sorted(book.rglob("*.md"))

    assert len(markdown_files) in _counts(leaves, "files", "file_count", "file_total")
    assert float(sum(p.stat().st_size for p in markdown_files)) in _counts(leaves, "byte")
    assert len(graph.ui_nodes) in _counts(leaves, "ui_node", "node_ui", "ui_nodes")
    assert len(graph.features) in _counts(leaves, "feature")
    assert any(c >= 1 for c in _counts(leaves, "link_target", "link", "target"))


def test_two_json_runs_differ_only_in_their_timings(book: Path):
    first, second = _leaves(_json_report(book)), _leaves(_json_report(book))

    assert sorted(p for p, _ in first) == sorted(p for p, _ in second)
    for patterns in (("files", "file_count", "file_total"), ("byte",),
                     ("ui_node", "node_ui", "ui_nodes"), ("feature",)):
        assert _counts(first, *patterns) == _counts(second, *patterns)


def _tree_digest(root: Path) -> str:
    sha = hashlib.sha256()
    for path in sorted(p for p in root.rglob("*.py") if "__pycache__" not in p.parts):
        sha.update(str(path.relative_to(root)).encode())
        sha.update(path.read_bytes())
    return sha.hexdigest()


def _doctor_json(book: Path, capsys) -> str:
    capsys.readouterr()
    ostler_main(["-C", str(book), "doctor", "--json"])
    return capsys.readouterr().out


def test_the_harness_only_measures(book: Path, capsys):
    """It edits no ostler module, and `doctor` says exactly what it said before."""
    before_report = _doctor_json(book, capsys)
    before_ostler = _tree_digest(REPO_ROOT / "ostler" / "ostler")

    done = _run_script(book, "--json")
    assert done.returncode == 0, done.stderr or done.stdout

    assert _tree_digest(REPO_ROOT / "ostler" / "ostler") == before_ostler
    assert _doctor_json(book, capsys) == before_report
