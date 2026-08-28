"""The book-building round: strip a finished app's book, run okf-builder, grade the rebuild.

The frozen-app rounds measure what a QA lane does *with* a book; this family measures
whether the toolchain can *write* one. The trial tree is a seed capture of a finished
app, the step deletes `docs/features/<service>/` and commits the deletion, and the
builder is pointed at the stripped tree — so the run starts from discovery against real
source, exactly the state a team adopting the toolchain starts from.

The ruler is deliberately deterministic: `ostler doctor` clean, `ostler fmt` canonical,
the builder's own `coverage.json` saying covered == total, and the graph counts a loaded
book yields. None of that needs an agent to judge, so the headline is comparable across
labels the way a detection rate is. The one column that can be absent — the judgment
layer — prints `–` (see `_frozenapp.BLANK`) rather than `0` when the installed ostler
does not know the vocabulary yet: a zero would read as "the builder wrote no concepts"
against a registry that could not have accepted one.

The leading underscore keeps `paddock.loader` from treating this as a task module: it is
the library each book-building task imports, not a second declaration.
"""

from __future__ import annotations

import json
import os
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from _frozenapp import BLANK, TRIALS, capture_witness, trials_dir
from _stablemate import (
    TrialError,
    effective,
    git,
    no_leaks,
    pin_held,
    stablemate_checkout,
    uv_run,
)
from paddock import Run, Score


@dataclass(frozen=True, slots=True)
class Fixture:
    """One book-building round: which service to strip and rebuild, out of which tree.

    `service` names the book directory (`docs/features/<service>/`) and is what the
    builder is asked to build; `source_path` is the source root it reads, which the
    builder defaults to the service name when the two coincide. `budget_s` is generous
    by default — a build is one long run, not a fan of trials — and `--param budget`
    still narrows it for a smoke round.
    """

    service: str
    source_path: str
    repo_dir: str
    budget_s: float = 5400.0
    source_excludes: str = ""


def book_dir(repo: Path, fixture: Fixture) -> Path:
    return repo / "docs" / "features" / fixture.service


def strip_book(run: Run, fixture: Fixture) -> None:
    """Delete the service's book and commit the deletion, so the build starts at HEAD.

    Committed rather than merely deleted: okf-builder converges whatever state it finds,
    and an uncommitted deletion leaves the old book one `git checkout` away — a build
    that "recovered" it from the index would score as a rebuild without performing one.
    The rest of `docs/` stays: decisions and backlog are inputs a real adoption would
    also have on disk.
    """
    book = book_dir(run.repo, fixture)
    if not book.is_dir():
        raise TrialError(f"no book at {book} — nothing to strip means nothing to rebuild")
    if not (run.repo / ".git").exists():
        raise TrialError(f"{run.repo} is not a git checkout — the strip cannot be committed")
    shutil.rmtree(book)
    # Identity on the repo rather than the machine, as `materialize` does: a trial must
    # not depend on the host's global git config, and must not write to it either.
    git("config", "user.email", "benchmark@example.com", cwd=run.repo)
    git("config", "user.name", "stablemate benchmark", cwd=run.repo)
    rel = str(book.relative_to(run.repo))
    git("add", "--all", "--", rel, cwd=run.repo)
    git("commit", "--quiet", "-m", f"strip the {fixture.service} book", cwd=run.repo)


def run_build(run: Run, fixture: Fixture) -> None:
    """Drive `workhorse-okf-builder run` over the stripped tree; keep the witness.

    One trial per round: a build is its own control — there is no defect to seed, and
    the ruler grades the artifact rather than a verdict. The witness is `docs/` plus the
    config files ostler roots on (`capture_witness`), which is exactly what every ruler
    below reads, so a sealed result stays re-scorable on a machine that never ran it.
    """
    checkout = stablemate_checkout(run)
    budget = run.param_float("budget", fixture.budget_s)
    config = effective(run)
    runs_dir = trials_dir(run) / "runs"
    run_id = f"{fixture.repo_dir}-{run.label}-build"

    params: dict[str, Any] = {
        "service": fixture.service,
        "source_path": fixture.source_path,
        "docs_path": str(run.repo),
    }
    excludes = run.param("source_excludes", fixture.source_excludes)
    if excludes:
        params["source_excludes"] = excludes

    with no_leaks(checkout, pinned=pin_held(run.pinned)):
        # farrier regenerates `.agents/agents-context.json`, which is gitignored and so
        # absent from a seed capture; every prompt path in the run would fail to resolve
        # without it. It is also where the unpacked seed's machine-local paths get
        # re-pointed at this machine.
        run.cli(
            *uv_run(checkout, "farrier"),
            "farrier", "install", "--repo", str(run.repo),
            cwd=checkout, log_name=f"{run_id}-farrier", check=True,
        )
        started = time.monotonic()
        result = run.cli(
            *uv_run(checkout, "workhorse-workflows"),
            "workhorse-okf-builder", "run",
            "--runs-dir", str(runs_dir), "--run-id", run_id,
            # Whole-file: the round's models are the tracked config's, not whatever this
            # machine happens to have set.
            "--config", str(config),
            "--params", json.dumps(params),
            cwd=run.repo,
            # Enforced by workhorse between states rather than by killing the process,
            # so an over-budget build stops at a node boundary with its spans intact.
            env={
                **os.environ,
                "WORKHORSE_MAX_RUNTIME_S": str(budget),
                "AGENT_REPO_DIR": str(run.repo),
            },
            log_name=f"{run_id}-build",
        )
        wall = time.monotonic() - started

    witness = capture_witness(run.repo, trials_dir(run) / run_id / "witness")
    run.write_json(trials_dir(run) / "trials.json", [{
        "run_id": run_id,
        "rc": result.returncode,
        "wall": wall,
        "witness": str(witness.relative_to(run.stage)),
    }])


# ── the rulers ────────────────────────────────────────────────────────────────────────
#
# Each one is a pure function of the witness tree, returns `None` when it could not
# measure — a build that died before writing anything leaves a witness some rulers
# cannot read, and `None` renders as `–`, which is not a zero — and imports ostler
# lazily, as `_frozenapp.evidence_statuses` does, so loading a task module stays cheap.
#
# The `docs/` guard is not redundancy: handed a directory with no book at all, ostler
# does not refuse — root discovery settles somewhere and an empty tree reports zero
# findings — so a build that died before writing anything would score `doctor 0e/0w`
# clean. A witness without `docs/` is unreadable, and unreadable is `–`.


def _readable(witness: Path) -> bool:
    return (witness / "docs").is_dir()


def doctor_counts(witness: Path) -> dict[str, Any] | None:
    """`{"errors": int, "warnings": int, "findings": [...]}` — the book's health."""
    from ostler.api import Ostler

    if not _readable(witness):
        return None
    try:
        report = Ostler(witness).doctor().data
    except Exception:  # noqa: BLE001 - an unreadable witness is a `–`, not a crash
        return None
    return {
        "errors": int(report["errors"]),
        "warnings": int(report["warnings"]),
        "findings": report.get("findings", []),
    }


def fmt_check(witness: Path) -> list[str] | None:
    """The files `ostler fmt` would rewrite — empty means the book is canonical."""
    from ostler.api import Ostler

    if not _readable(witness):
        return None
    try:
        return [str(path) for path in Ostler(witness).fmt(check=True)]
    except Exception:  # noqa: BLE001 - an unreadable witness is a `–`, not a crash
        return None


def coverage_counts(witness: Path, fixture: Fixture) -> dict[str, int] | None:
    """The builder's own `coverage.json`: how much of the inventory the book covers.

    Read from the file the build committed rather than recomputed, deliberately: the
    claim under test is the builder's, and recomputing it here would grade this repo's
    coverage code against itself.
    """
    path = book_dir(witness, fixture) / "coverage.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return {"covered": int(data["covered"]), "total": int(data["total"])}
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        return None


def graph_counts(witness: Path) -> dict[str, int] | None:
    """What the loaded book amounts to: nodes, and the obligation ids it can mint.

    The private helpers under `build_context` rather than `build_context` itself, for
    the same reason the app tests use them: minting against a diff needs a git repo and
    a base, and a witness is a copy of `docs/` — the diffless path is the same code
    minus exactly the part a witness cannot answer.
    """
    from ostler.model import load
    from ostler.qa.context import _obligations, _serialized_graph

    if not _readable(witness):
        return None
    try:
        nodes, _edges, _ends, _scopes, _details = _serialized_graph(load(witness))
    except Exception:  # noqa: BLE001 - an unreadable witness is a `–`, not a crash
        return None
    obligations = {
        obligation["id"]
        for node in nodes.values()
        for obligation in _obligations(
            node, [], journey=str(node.get("type", "")) in ("flow", "journey")
        )
    }
    return {"nodes": len(nodes), "obligations": len(obligations)}


def judgment_counts(witness: Path) -> dict[str, int] | None:
    """Concepts, and the `detail:` links pointing at them — the judgment layer's size.

    `None` when the installed registry does not declare the judgment vocabulary on
    `concept` (the Track-A degrade): against such a registry the builder could not have
    written a selection rule, so a zero here would blame the build for the toolchain.
    """
    from ostler import registry
    from ostler.model import load
    from ostler.qa.context import _serialized_graph

    if "rule" not in registry.declared_keys("concept") or not _readable(witness):
        return None
    try:
        nodes, _edges, _ends, _scopes, details = _serialized_graph(load(witness))
    except Exception:  # noqa: BLE001 - an unreadable witness is a `–`, not a crash
        return None
    concepts = {
        node_id for node_id, node in nodes.items()
        if str(node.get("type", "")) == "concept"
    }
    inbound = sum(1 for _source, target in details if target in concepts)
    return {"concepts": len(concepts), "detail_links": inbound}


# ── the score ─────────────────────────────────────────────────────────────────────────


def _doctor_cell(doctor: dict[str, Any] | None) -> str:
    return f"{doctor['errors']}e/{doctor['warnings']}w" if doctor else BLANK


def _fmt_cell(unformatted: list[str] | None) -> str:
    if unformatted is None:
        return BLANK
    return "clean" if not unformatted else f"{len(unformatted)} unformatted"


def _coverage_cell(coverage: dict[str, int] | None) -> str:
    return f"{coverage['covered']}/{coverage['total']}" if coverage else BLANK


def _judgment_cell(judgment: dict[str, int] | None) -> str:
    if judgment is None:
        return BLANK
    return f"{judgment['concepts']} concepts, {judgment['detail_links']} detail links"


def score_round(run: Run, fixture: Fixture) -> Score:
    """Grade the witness the build left behind — read-only over the stage.

    Recomputed here rather than recorded by the step, so a sealed result zip can be
    re-scored after a ruler changes without re-running the build.
    """
    ledger = run.stage.joinpath(*TRIALS) / "trials.json"
    if not ledger.is_file():
        return Score(headline="no build recorded — the round did not reach a run", detail=())

    entry = json.loads(ledger.read_text(encoding="utf-8"))[0]
    witness = run.stage / str(entry["witness"])

    doctor = doctor_counts(witness)
    unformatted = fmt_check(witness)
    coverage = coverage_counts(witness, fixture)
    graph = graph_counts(witness)
    judgment = judgment_counts(witness)

    rc = int(entry["rc"])
    minutes = float(entry["wall"]) / 60
    obligations = str(graph["obligations"]) if graph else BLANK
    headline = (
        f"book built: doctor {_doctor_cell(doctor)}  fmt {_fmt_cell(unformatted)}  "
        f"coverage {_coverage_cell(coverage)}  obligations {obligations} "
        f"| rc {rc} in {minutes:.0f}m"
    )

    detail = [
        f"nodes {graph['nodes'] if graph else BLANK}  "
        f"judgment {_judgment_cell(judgment)}",
    ]
    if doctor and doctor["findings"]:
        codes = sorted({str(finding.get("code", "?")) for finding in doctor["findings"]})
        detail.append(f"doctor findings: {', '.join(codes)}")
    if unformatted:
        detail.append(f"unformatted: {', '.join(sorted(unformatted))}")

    caveats: list[str] = []
    if rc != 0:
        caveats.append(
            f"the build exited rc {rc} — the book is whatever state the run stopped in"
        )

    return Score(
        headline=headline,
        detail=tuple(detail),
        data={
            "trial": entry,
            "doctor": doctor,
            "unformatted": unformatted,
            "coverage": coverage,
            "graph": graph,
            "judgment": judgment,
        },
        caveats=tuple(caveats),
    )
