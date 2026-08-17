#!/usr/bin/env python3
"""``make bench-doctor DOCS=<path>`` — the reproducible baseline for ``ostler doctor``.

Every timing the parse-cache plan is steered by came from ad-hoc profiling in a throwaway
session, which means nobody else can re-derive it and no increment can be checked against
it. This harness is that profiling, committed: it reports the same decomposition the plan
is built on — ``model.load`` cold and warm, ``doctor.run`` cold and warm, the per-check
split, and the three components inside ``_check_ui`` — plus the book's shape, because a
timing with no shape beside it is comparable to nothing.

**The book is an argument with no default.** The measured book lives outside this repo and
cannot be committed to it, so a baked-in path would be both wrong and unshippable. ``DOCS=``
is required; ``make bench-doctor`` with no ``DOCS=`` stops rather than measuring whatever
happened to be underfoot and reporting a number nobody can place.

**It only measures.** No ostler module is edited and no ``doctor`` verdict changes. The
per-check split comes from wrapping the check functions on the module object for the
duration of one extra run, and the ``_check_ui`` components from timing the line events of
``_check_ui``'s own frame for one more — both restored afterwards, both on throwaway
finding lists whose contents are discarded.

**Two independent axes, and they are not the same axis.** *Cold* and *warm* are within one
process: the first call and the second, the distinction the plan's original numbers were
taken under. *Index state* is across processes, and it is the one the persistent cache
actually moves — every ``ostler`` invocation is a fresh process, so the number an operator
feels is a first call in a new process against an index somebody else's run filled. The
harness reports three index states, each measured with every process-lifetime cache cleared
first:

``no-index``
    The session disabled. The pre-cache baseline, and what ``--no-index`` costs today.
``cold-index``
    An empty index directory. Pays every parse *and* the writes — the price of being first.
``warm-index``
    The same directory, now filled by the ``cold-index`` pass. **This is the acceptance
    gate's speed half:** the plan's "each ~0 warm" and "total <5s" targets are about this
    column, and a harness that never opened a session could not report it. Measuring only
    within-process warmth would have described a cache the plan is not about.

The per-check split and the ``_check_ui`` components are measured under ``warm-index``,
after that pair, so they describe a warm process against a filled index — and the
components additionally carry line-tracing overhead, so they are for comparing an increment
against a baseline taken the same way, not against the phase totals above them.

**The index directory is a throwaway.** A benchmark that filled the operator's real cache
would change the machine it was measuring and make the next run's ``cold`` a fiction, so
each invocation builds its own directory under a temporary root unless ``--index-dir`` says
otherwise.
"""
from __future__ import annotations

import argparse
import ast
import inspect
import json
import sys
import tempfile
import time
from collections import defaultdict
from collections.abc import Callable, Iterator
from contextlib import contextmanager, redirect_stdout
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ostler import doctor, index, inventory, links, markdown, model

#: The index states each phase is measured under, in the order they must run: ``cold-index``
#: fills the directory ``warm-index`` then reads. ``no-index`` is first because it is the
#: baseline the other two are read against.
NO_INDEX = "no-index"
COLD_INDEX = "cold-index"
WARM_INDEX = "warm-index"
INDEX_STATES = (NO_INDEX, COLD_INDEX, WARM_INDEX)

#: The check functions ``doctor.run`` calls, in the spelling the plan's table uses. A check
#: that the profile or the book never reaches reports 0.0 with zero calls beside it, rather
#: than dropping out of the table — an absent row and a fast row are not the same finding.
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

#: The three components inside ``_check_ui``, and how each is recognised in its source. The
#: spans are read out of the AST rather than written down as line numbers, so an edit to
#: ``doctor.py`` moves them instead of silently mis-attributing them.
UI_FILE_LOOP = "_check_ui_file loop"
UI_CODE_GROUNDING = "_check_code_grounding"
UI_REQUIRED_BULLETS = "required-bullet loop"
UI_REMAINDER = "remainder (links, anchors, relations)"


@dataclass
class Timings:
    """Wall-clock seconds per label, plus how many times each label was entered."""

    seconds: dict[str, float] = field(default_factory=lambda: defaultdict(float))
    calls: dict[str, int] = field(default_factory=lambda: defaultdict(int))

    def add(self, label: str, elapsed: float) -> None:
        self.seconds[label] += elapsed
        self.calls[label] += 1

    def as_dict(self, labels: tuple[str, ...]) -> dict[str, dict[str, float | int]]:
        return {label: {"seconds": round(self.seconds.get(label, 0.0), 6),
                        "calls": self.calls.get(label, 0)}
                for label in labels}


@contextmanager
def _stopwatch(record: Callable[[float], None]) -> Iterator[None]:
    start = time.perf_counter()
    try:
        yield
    finally:
        record(time.perf_counter() - start)


def _drop_process_caches() -> None:
    """Empty every process-lifetime cache, so the next call is cold in the sense meant.

    There are three, and a harness that clears one is measuring the other two. They are
    listed exhaustively rather than discovered, because a cache this misses does not fail
    the run — it quietly reports somebody else's warm number as this pass's cold one, which
    is the failure mode that makes a benchmark worse than no benchmark.

    - ``model._FEATURE_DOC_CACHE`` — per-path frontmatter and UI nodes.
    - ``model._DOC_CACHE`` — the parsed document memo in front of the index.
    - ``inventory._SYMBOL_MEMO`` — per-file declaration sets for code grounding.
    """
    model._FEATURE_DOC_CACHE.clear()
    model._DOC_CACHE.clear()
    inventory._SYMBOL_MEMO.clear()


def _cold(book: Path) -> model.Graph:
    """Load the book with every process-lifetime cache emptied first.

    Those caches survive for the life of the process, so the *second* load in a harness
    that measured naively would be the only honest cold number it ever took. Clearing them
    is what makes "cold" mean cold rather than "first".
    """
    _drop_process_caches()
    return model.load(book)


# ---- the book's shape ---------------------------------------------------------------

def shape(book: Path, graph: model.Graph) -> dict[str, int]:
    """File count, total bytes, UI nodes, feature docs, link targets.

    A timing is a number about a book, and two timings are comparable only when the books
    are. ``link_targets`` is the count that matters most of the five: it is the set of
    files ``links._compute_anchors`` re-reads and re-parses, and on the plan's book that
    set alone is 386 files and 22 of the 143 seconds.
    """
    files = sorted(book.rglob("*.md"))
    linked, existing = _link_targets(book, graph)
    return {
        "markdown_files": len(files),
        "total_bytes": sum(p.stat().st_size for p in files),
        "ui_nodes": len(graph.ui_nodes),
        "feature_docs": len(graph.features),
        "link_targets": linked,
        "link_targets_existing": existing,
        "epics": len(graph.epics),
    }


def _link_targets(book: Path, graph: model.Graph) -> tuple[int, int]:
    """``(distinct files the book's doc links name, how many of them exist)``.

    Resolved with ostler's own resolver, over every markdown file under the book — the
    same denominator ``markdown_files`` and ``total_bytes`` use, and wider than
    ``_check_ui``'s features-only link scan, because a story citing a feature doc is a
    target file that gets read and parsed like any other.

    Both numbers, because they answer different questions and neither implies the other.
    The first is how much link work the book asks for. The second is the set
    ``links._compute_anchors`` actually re-reads and re-parses — the 386 files and 22 of
    the 143 seconds the plan is about — and the gap between them is the book's dangling
    links, which cost a ``stat`` and nothing more.
    """
    resolver = links.LinkResolver(graph)
    targets: set[Path] = set()
    existing: set[Path] = set()
    for path in sorted(book.rglob("*.md")):
        if not path.is_file():
            continue
        try:
            body = path.read_text(encoding="utf-8")
        except OSError:
            continue
        for _text, href, _line in markdown.iter_links(body):
            target = resolver.resolve(path, href)
            if target is None:
                continue
            targets.add(target.path)
            if target.file_exists:
                existing.add(target.path)
    return len(targets), len(existing)


# ---- the per-check split ------------------------------------------------------------

def per_check(graph: model.Graph) -> Timings:
    """One extra ``doctor.run``, with each named check wrapped in a stopwatch.

    The wrappers are installed on the module object and removed in a ``finally``, and the
    report the run produces is thrown away: nothing outside this function can observe that
    the run happened, which is the whole contract a benchmark owes the thing it times.
    """
    timings = Timings()
    originals = {name: getattr(doctor, name) for name in CHECKS}

    def wrap(name: str, fn: Callable[..., Any]) -> Callable[..., Any]:
        def timed(*args: Any, **kwargs: Any) -> Any:
            start = time.perf_counter()
            try:
                return fn(*args, **kwargs)
            finally:
                timings.add(name, time.perf_counter() - start)
        return timed

    try:
        for name, fn in originals.items():
            setattr(doctor, name, wrap(name, fn))
        doctor.run(graph)
    finally:
        for name, fn in originals.items():
            setattr(doctor, name, fn)
    return timings


# ---- the components inside _check_ui ------------------------------------------------

def _ui_component_spans() -> list[tuple[str, int, int]]:
    """``(label, first_line, last_line)`` for each top-level statement of ``_check_ui``.

    Read from the AST of the running ``doctor.py``, and classified by what each statement
    mentions rather than by where it sits, because a line number written down here is a
    mis-attribution waiting for the next edit to ``doctor.py``. The two loops over
    ``graph.ui_nodes`` are told apart by ``bullet_keys``, which only the required-bullet
    one reads.
    """
    source = Path(inspect.getsourcefile(doctor) or "").read_text(encoding="utf-8")
    tree = ast.parse(source)
    body: list[ast.stmt] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_check_ui":
            body = node.body
            break
    spans: list[tuple[str, int, int]] = []
    for stmt in body:
        names = {n.id for n in ast.walk(stmt) if isinstance(n, ast.Name)}
        names |= {n.attr for n in ast.walk(stmt) if isinstance(n, ast.Attribute)}
        if "_check_ui_file" in names:
            label = UI_FILE_LOOP
        elif "_check_code_grounding" in names:
            label = UI_CODE_GROUNDING
        elif isinstance(stmt, ast.For) and "bullet_keys" in names:
            label = UI_REQUIRED_BULLETS
        else:
            label = UI_REMAINDER
        spans.append((label, stmt.lineno, stmt.end_lineno or stmt.lineno))
    return spans


def ui_components(graph: model.Graph) -> Timings:
    """Time ``_check_ui``'s own frame line by line, and fold the lines into components.

    A line event fires only for ``_check_ui``'s frame, so the gap between two of them
    covers everything the earlier line did *including* the calls it made — which is
    exactly the attribution wanted: the statement that runs the file loop is charged the
    whole loop. This costs tracing overhead the other measurements do not pay, so these
    three numbers are comparable to another run of this harness and not to the phase
    totals above them.
    """
    timings = Timings()
    spans = _ui_component_spans()
    by_line = {label: 0.0 for label, _, _ in spans}
    per_line: dict[int, float] = defaultdict(float)
    state: dict[str, Any] = {"line": None, "at": 0.0}

    def on_line(_code: Any, line_number: int) -> None:
        now = time.perf_counter()
        if state["line"] is not None:
            per_line[state["line"]] += now - state["at"]
        state["line"] = line_number
        state["at"] = time.perf_counter()

    mon = sys.monitoring
    tool_id = mon.PROFILER_ID
    code = doctor._check_ui.__code__
    mon.use_tool_id(tool_id, "bench-ostler-doctor")
    try:
        mon.register_callback(tool_id, mon.events.LINE, on_line)
        mon.set_local_events(tool_id, code, mon.events.LINE)
        doctor._check_ui(graph, [])
        if state["line"] is not None:
            per_line[state["line"]] += time.perf_counter() - state["at"]
    finally:
        mon.set_local_events(tool_id, code, 0)
        mon.register_callback(tool_id, mon.events.LINE, None)
        mon.free_tool_id(tool_id)

    for line, elapsed in per_line.items():
        for label, first, last in spans:
            if first <= line <= last:
                by_line[label] += elapsed
                break
    for label in (UI_FILE_LOOP, UI_CODE_GROUNDING, UI_REQUIRED_BULLETS, UI_REMAINDER):
        timings.add(label, by_line.get(label, 0.0))
    return timings


# ---- the measurement --------------------------------------------------------------

def _phases_under(book: Path) -> tuple[model.Graph, dict[str, float]]:
    """One index state's four phase timings, and the graph they were taken against.

    The caller has already opened — or declined to open — the session, so this is only the
    stopwatch work. Keeping the session out of here is what makes the three states
    comparable: they differ in exactly one thing, and it is the thing being measured.
    """
    phases = Timings()

    with _stopwatch(lambda s: phases.add("model.load cold", s)):
        graph = _cold(book)
    with _stopwatch(lambda s: phases.add("model.load warm", s)):
        model.load(book)

    with _stopwatch(lambda s: phases.add("doctor.run cold", s)):
        doctor.run(graph)
    with _stopwatch(lambda s: phases.add("doctor.run warm", s)):
        doctor.run(graph)

    return graph, {
        "model_load_cold_seconds": round(phases.seconds["model.load cold"], 6),
        "model_load_warm_seconds": round(phases.seconds["model.load warm"], 6),
        "doctor_run_cold_seconds": round(phases.seconds["doctor.run cold"], 6),
        "doctor_run_warm_seconds": round(phases.seconds["doctor.run warm"], 6),
    }


def measure(book: Path, index_dir: Path) -> dict[str, Any]:
    """Every measurement, taken under each of the three index states.

    The states run in the order :data:`INDEX_STATES` gives and that order is load-bearing:
    ``cold-index`` is what fills the directory ``warm-index`` then reads. Running them
    apart, or against a directory some earlier invocation left populated, reports a warm
    number for a pass labelled cold.

    The per-check split and the ``_check_ui`` components are taken under ``warm-index``,
    because that is the state the plan's per-increment targets are written against.
    """
    by_state: dict[str, dict[str, float]] = {}
    for state in INDEX_STATES:
        with index.session(book, directory=index_dir, enabled=state != NO_INDEX):
            graph, by_state[state] = _phases_under(book)
            if state == WARM_INDEX:
                warm_shape = shape(book, graph)
                checks = per_check(graph)
                components = ui_components(graph)

    return {
        "book": str(book),
        "python": sys.version.split()[0],
        "index_dir": str(index_dir),
        "cold_warm": "cold is the first call in this process, warm the second; the index "
                     "states are across processes and are the separate axis",
        "shape": warm_shape,
        "phases": by_state[WARM_INDEX],
        "phases_by_index_state": by_state,
        "checks": checks.as_dict(CHECKS),
        "check_ui_components": {
            "_check_ui_file_loop_seconds": round(components.seconds[UI_FILE_LOOP], 6),
            "_check_code_grounding_seconds": round(components.seconds[UI_CODE_GROUNDING], 6),
            "required_bullet_loop_seconds": round(components.seconds[UI_REQUIRED_BULLETS], 6),
            "remainder_seconds": round(components.seconds[UI_REMAINDER], 6),
        },
    }


# ---- the report -------------------------------------------------------------------

def _row(label: str, value: str) -> str:
    return f"  {label:<38}{value:>14}"


def render(report: dict[str, Any]) -> str:
    shape_counts = report["shape"]
    phases = report["phases"]
    lines = [
        f"ostler doctor — {report['book']}",
        "",
        "  book shape",
        _row("markdown files", str(shape_counts["markdown_files"])),
        _row("total bytes", str(shape_counts["total_bytes"])),
        _row("UI nodes", str(shape_counts["ui_nodes"])),
        _row("feature docs", str(shape_counts["feature_docs"])),
        _row("link targets",
             f"{shape_counts['link_targets']} ({shape_counts['link_targets_existing']} exist)"),
        _row("epics", str(shape_counts["epics"])),
        "",
        "  phase, under warm-index                   cold           warm",
        _row("model.load",
             f"{phases['model_load_cold_seconds']:>10.3f}s "
             f"{phases['model_load_warm_seconds']:>9.3f}s"),
        _row("doctor.run",
             f"{phases['doctor_run_cold_seconds']:>10.3f}s "
             f"{phases['doctor_run_warm_seconds']:>9.3f}s"),
        "",
        "  by index state (process caches dropped before each; cold call, then warm)",
    ]
    for state in INDEX_STATES:
        entry = report["phases_by_index_state"][state]
        total_cold = entry["model_load_cold_seconds"] + entry["doctor_run_cold_seconds"]
        lines.append(_row(
            state,
            f"{total_cold:>10.3f}s "
            f"{entry['model_load_warm_seconds'] + entry['doctor_run_warm_seconds']:>9.3f}s",
        ))
    lines += [
        "",
        "  per-check split (one warm doctor.run under warm-index)",
    ]
    for name in CHECKS:
        entry = report["checks"][name]
        lines.append(_row(name, f"{entry['seconds']:>10.3f}s  ×{entry['calls']}"))
    components = report["check_ui_components"]
    lines += [
        "",
        "  inside _check_ui (line-traced, so it carries tracing overhead)",
        _row("_check_ui_file loop", f"{components['_check_ui_file_loop_seconds']:>10.3f}s"),
        _row("_check_code_grounding", f"{components['_check_code_grounding_seconds']:>10.3f}s"),
        _row("required-bullet loop", f"{components['required_bullet_loop_seconds']:>10.3f}s"),
        _row("remainder — links/anchors", f"{components['remainder_seconds']:>10.3f}s"),
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="bench_ostler_doctor.py",
        description="Measure `ostler doctor` against a book: phases, per-check split, "
                    "the components inside _check_ui, and the book's shape.",
        epilog="The book is required and has no default — the measured book lives outside "
               "this repo, and a number taken against an unnamed book places nothing.",
    )
    parser.add_argument("docs", type=Path,
                        help="path to the repo holding the book (DOCS= in `make bench-doctor`)")
    parser.add_argument("--json", action="store_true",
                        help="emit the same measurements as one JSON object, for diffing runs")
    parser.add_argument("--index-dir", type=Path, default=None, dest="index_dir",
                        help="index directory to measure against; the default is a fresh "
                             "temporary one, so a run never fills the operator's real cache")
    args = parser.parse_args(argv)

    book = args.docs.resolve()
    if not book.is_dir():
        parser.error(f"DOCS: {book} is not a directory")

    with tempfile.TemporaryDirectory(prefix="bench-ostler-index-") as scratch:
        index_dir = args.index_dir.resolve() if args.index_dir is not None else Path(scratch)
        # ostler is a library here, not a command, but a stray print from anything it loads
        # would land in the middle of the JSON object. Nothing it writes is a measurement.
        with redirect_stdout(sys.stderr):
            report = measure(book, index_dir)

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(render(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
