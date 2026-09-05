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
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import _forensics as fx
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
    source_paths: tuple[str, ...] = ()
    budget_s: float = 5400.0
    source_excludes: str = ""
    #: The judge's own backend, pinned apart from the builder under test — the same
    #: precedence rule as `_greenfield.judge_backlog`: an unpinned grader would switch
    #: backends in step with the thing it grades, and a delta between two labels would
    #: then carry no information about either.
    judge_cli: str = ""
    judge_model: str = ""
    judge_effort: str = ""


def book_dir(repo: Path, fixture: Fixture) -> Path:
    return repo / "docs" / "features" / fixture.service


def capture_build_witness(repo: Path, dest: Path, fixture: Fixture) -> Path:
    """Seal every source root participating in the build, once and by relative path."""
    sources = tuple(dict.fromkeys((fixture.source_path, *fixture.source_paths)))
    return capture_witness(repo, dest, extra=sources)


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
    # `--no-verify` because the seed's own hooks run otherwise, and they reject this
    # commit: a capture excludes `.claude/`, so the app's farrier pre-commit hook finds
    # its generated files missing and exits non-zero. The hooks belong to the app under
    # test; this commit is fixture surgery performed by the harness, not agent work the
    # hooks exist to gate.
    message = f"strip the {fixture.service} book"
    git("commit", "--quiet", "--no-verify", "-m", message, cwd=run.repo)


def run_build(run: Run, fixture: Fixture) -> None:
    """Drive `workhorse-okf-builder run` over the stripped tree; keep the witness.

    One trial per round: a build is its own control — there is no defect to seed, and
    the ruler grades the artifact rather than a verdict. The witness is `docs/` plus the
    config files ostler roots on (`capture_witness`) *plus the source root the book
    cites* — doctor grades code grounding by resolving every `code:` ref, so a witness
    without the source scores a converged book as a wall of `dangling-code-ref` errors.
    Sealing the source keeps the result re-scorable on a machine that never ran it.
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

    witness = capture_build_witness(
        run.repo, trials_dir(run) / run_id / "witness", fixture
    )
    run.write_json(trials_dir(run) / "trials.json", [{
        "run_id": run_id,
        "rc": result.returncode,
        "wall": wall,
        "witness": str(witness.relative_to(run.stage)),
    }])


def clone_build_repo(run: Run, fixture: Fixture, profile: str) -> Path:
    """Clone the stripped baseline into one profile's isolated scratch tree."""
    destination = run.workdir(f"book-{profile}") / fixture.repo_dir
    git("clone", "--quiet", str(run.repo), str(destination), cwd=run.scratch)
    return destination


def _build_telemetry(run_id: str, wall: float, since: float) -> dict[str, Any]:
    """Snapshot telemetry while the machine-wide store still holds this trial."""
    from groom import store

    profile = store.run_profile(run_id) or {}
    return {
        "work": profile.get("work") or {},
        "timing": fx.timing_of(run_id, wall, since),
        "laps": fx.laps_of(run_id, since),
    }


def run_paired_build(
    run: Run, fixture: Fixture, profiles: tuple[str, ...] = ("luna", "terra")
) -> None:
    """Build the same stripped book once per model profile from isolated clones."""
    if not profiles or len(set(profiles)) != len(profiles):
        raise TrialError("paired build profiles must be non-empty and unique")

    checkout = stablemate_checkout(run)
    budget = run.param_float("budget", fixture.budget_s)
    config = effective(run)
    runs_dir = trials_dir(run) / "runs"
    baseline_head = git("rev-parse", "HEAD", cwd=run.repo)
    ledger: list[dict[str, Any]] = []

    with no_leaks(checkout, pinned=pin_held(run.pinned)):
        for profile in profiles:
            repo = clone_build_repo(run, fixture, profile)
            run_id = f"{fixture.repo_dir}-{run.label}-book-{profile}"
            run.cli(
                *uv_run(checkout, "farrier"),
                "farrier", "install", "--repo", str(repo),
                cwd=checkout, log_name=f"{run_id}-farrier", check=True,
            )
            params: dict[str, Any] = {
                "service": fixture.service,
                "source_path": fixture.source_path,
                "docs_path": str(repo),
            }
            excludes = run.param("source_excludes", fixture.source_excludes)
            if excludes:
                params["source_excludes"] = excludes

            started, since = time.monotonic(), time.time()
            result = run.cli(
                *uv_run(checkout, "workhorse-workflows"),
                "workhorse-okf-builder", "run",
                "--runs-dir", str(runs_dir), "--run-id", run_id,
                "--config", str(config), "--profile", profile,
                "--params", json.dumps(params),
                cwd=repo,
                env={
                    **os.environ,
                    "WORKHORSE_MAX_RUNTIME_S": str(budget),
                    "AGENT_REPO_DIR": str(repo),
                },
                log_name=f"{run_id}-build",
            )
            wall = time.monotonic() - started
            witness = capture_build_witness(
                repo, trials_dir(run) / run_id / "witness", fixture
            )
            ledger.append({
                "profile": profile,
                "run_id": run_id,
                "baseline_head": baseline_head,
                "rc": result.returncode,
                "wall": wall,
                "witness": str(witness.relative_to(run.stage)),
                "telemetry": _build_telemetry(run_id, wall, since),
            })
            run.write_json(trials_dir(run) / "trials.json", ledger)


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


# ── the judge ─────────────────────────────────────────────────────────────────────────
#
# Opt-in (`--param judge=true`), and never the headline: an agent grading prose is a
# different kind of instrument from the rulers above — useful, but not comparable across
# labels the way a doctor count is. It answers the one question the rulers cannot:
# whether a normative bullet *earns* its citation, or merely sounds like it does.

BOOK_LEVELS: dict[int, tuple[str, str]] = {
    0: ("ungrounded", "the cited code shows something else, or the citation is missing"),
    1: ("asserted", "grounded but generic — the prose adds nothing the citation lacked"),
    2: ("earned", "the cited code shows the specific behavior the bullet claims"),
}
BOOK_MAX_LEVEL = max(BOOK_LEVELS)


def sample_bullets(witness: Path, fixture: Fixture, limit: int) -> list[dict[str, Any]]:
    """A deterministic sample of the book's per-bullet obligations, ready to judge.

    The node-level `contract`/`journey` obligations are excluded — they restate a title,
    which is not a claim a judge can hold against source — and so is anything minted
    outside the rebuilt book (the surviving epics and specs are inputs, not product).
    The sample is even-spaced over the sorted ids rather than random, so two scorings of
    one witness judge the same bullets and their delta is the judge's noise, not the
    draw's.
    """
    from ostler.model import load
    from ostler.qa.context import _obligations, _serialized_graph

    if not _readable(witness):
        return []
    try:
        nodes, _edges, _ends, _scopes, _details = _serialized_graph(load(witness))
    except Exception:  # noqa: BLE001 - an unreadable witness has nothing to judge
        return []
    prefix = f"docs/features/{fixture.service}/"
    pool: dict[str, dict[str, Any]] = {}
    for node in nodes.values():
        for obligation in _obligations(
            node, [], journey=str(node.get("type", "")) in ("flow", "journey")
        ):
            if obligation["kind"] in ("contract", "journey"):
                continue
            if not str(obligation["source"]).startswith(prefix):
                continue
            pool[str(obligation["id"])] = {
                "id": str(obligation["id"]),
                "page": str(obligation["source"]),
                "kind": str(obligation["kind"]),
                "claim": str(obligation["requirement"]),
            }
    ordered = [pool[key] for key in sorted(pool)]
    if limit <= 0 or len(ordered) <= limit:
        return ordered
    return [ordered[index * len(ordered) // limit] for index in range(limit)]


def _appraise(text: str, repo: Path) -> dict[str, Any]:
    """Parse one judge response and apply the citation cap — pure, so tests need no agent.

    The cap mirrors `_greenfield.judge_one`: an `earned` whose cited paths do not resolve
    in the repo, or that cites nothing at all, drops to `asserted` and is flagged — the
    judge's most common failure is a confident level resting on a path it invented.
    """
    from workhorse.runner import extract as wh_extract

    parsed = wh_extract.parse_json_from_text(text, ["level", "evidence", "reason"]) or {}
    try:
        level = max(0, min(BOOK_MAX_LEVEL, int(parsed.get("level", 0))))
    except (TypeError, ValueError):
        level = 0
    evidence = [str(e) for e in (parsed.get("evidence") or []) if str(e).strip()]
    reason = str(parsed.get("reason") or "").strip() or "(judge returned no reason)"
    bad = [e for e in evidence if not (repo / e.split(":", 1)[0].strip()).exists()]
    capped = bool(bad) or (level >= BOOK_MAX_LEVEL and not evidence)
    if capped and level >= BOOK_MAX_LEVEL:
        level = 1
    return {"level": level, "evidence": evidence, "reason": reason,
            "unverified_citations": bad, "capped": capped}


def judge_book(run: Run, fixture: Fixture, witness: Path) -> dict[str, Any] | None:
    """Have an agent grade a sample of the rebuilt book's bullets against the source.

    Judged over a scratch copy of the staged repo, never `run.repo` itself — the
    read-only-guard lesson from `_greenfield.judge_backlog`: the judge only reads, but
    the agent CLI it reads through writes its session transcripts into whatever tree it
    is pointed at, and a scored run must leave the stage byte-identical to an unscored
    one. Returns `None` when the witness minted nothing gradeable.
    """
    # Lazily, like the ostler imports above: the judge drags workhorse in, and every
    # book task pays that import at load time otherwise, judge or no judge.
    import _greenfield as gf

    limit = int(run.param_float("judge_sample", 12.0))
    bullets = sample_bullets(witness, fixture, limit)
    if not bullets:
        return None

    rubric_path = run.data_dir / "rubric-book.md"
    if not rubric_path.is_file():
        raise TrialError(f"no rubric at {rubric_path}")
    rubric = rubric_path.read_text(encoding="utf-8")

    judge = gf.Judge(
        gf.get_backend(fixture.judge_cli or None),
        gf.AgentResilience.from_env(), gf.SYSTEM_CLOCK,
        model=fixture.judge_model, effort=fixture.judge_effort,
    )
    repo = run.workdir("judge") / run.repo.name
    shutil.copytree(run.repo, repo, symlinks=True)
    scale = "\n".join(
        f"  {number} {name} — {description}"
        for number, (name, description) in BOOK_LEVELS.items()
    )

    def one(bullet: dict[str, Any]) -> dict[str, Any]:
        prompt = gf.render(
            rubric, page=bullet["page"], kind=bullet["kind"],
            claim=bullet["claim"], repo=str(repo), scale=scale,
        )
        text = gf.call_agent(judge, prompt, node_id=f"judge_{bullet['id']}", repo=repo)
        return {**bullet, **_appraise(text, repo)}

    jobs = max(1, int(run.param_float("judge_jobs", 4.0)))
    with ThreadPoolExecutor(max_workers=jobs) as pool:
        judged = list(pool.map(one, bullets))
    return {
        "sample": len(judged),
        "levels": {
            name: sum(1 for b in judged if int(b["level"]) == number)
            for number, (name, _description) in BOOK_LEVELS.items()
        },
        "capped": sum(1 for b in judged if b["capped"]),
        "bullets": judged,
    }


def _judge_line(book_judge: dict[str, Any]) -> str:
    levels = book_judge["levels"]
    sample = book_judge["sample"]
    parts = [f"earned {levels['earned']}/{sample}",
             f"asserted {levels['asserted']}", f"ungrounded {levels['ungrounded']}"]
    if book_judge["capped"]:
        parts.append(f"{book_judge['capped']} capped")
    return f"book judge: {', '.join(parts)} (sample of {sample})"


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


def _measure_build(run: Run, fixture: Fixture, entry: dict[str, Any]) -> dict[str, Any]:
    witness = run.stage / str(entry["witness"])
    doctor = doctor_counts(witness)
    unformatted = fmt_check(witness)
    coverage = coverage_counts(witness, fixture)
    graph = graph_counts(witness)
    judgment = judgment_counts(witness)
    accepted = bool(
        int(entry["rc"]) == 0
        and doctor is not None
        and doctor["errors"] == 0
        and doctor["warnings"] == 0
        and unformatted == []
        and coverage is not None
        and coverage["covered"] == coverage["total"]
    )
    return {
        "accepted": accepted,
        "trial": entry,
        "doctor": doctor,
        "unformatted": unformatted,
        "coverage": coverage,
        "graph": graph,
        "judgment": judgment,
    }


def _arm_line(profile: str, measured: dict[str, Any]) -> str:
    entry = measured["trial"]
    graph = measured["graph"]
    obligations = str(graph["obligations"]) if graph else BLANK
    return (
        f"{profile}: doctor {_doctor_cell(measured['doctor'])} "
        f"fmt {_fmt_cell(measured['unformatted'])} "
        f"coverage {_coverage_cell(measured['coverage'])} "
        f"obligations {obligations} | rc {int(entry['rc'])} "
        f"in {float(entry['wall']) / 60:.0f}m"
    )


def _paired_delta(
    arms: dict[str, dict[str, Any]], profiles: tuple[str, str]
) -> dict[str, Any]:
    first, second = profiles
    left_entry = arms[first]["trial"]
    right_entry = arms[second]["trial"]
    left_work = (left_entry.get("telemetry") or {}).get("work") or {}
    right_work = (right_entry.get("telemetry") or {}).get("work") or {}
    delta: dict[str, Any] = {"direction": f"{second}-minus-{first}"}
    values = {
        "wall_s": (left_entry.get("wall"), right_entry.get("wall")),
        "turns": (left_work.get("turns"), right_work.get("turns")),
        "backend_retries": (
            left_work.get("backend_retries"), right_work.get("backend_retries")
        ),
        "input_tokens": (left_work.get("input_tokens"), right_work.get("input_tokens")),
        "output_tokens": (left_work.get("output_tokens"), right_work.get("output_tokens")),
        "cost_usd": (left_work.get("cost_usd"), right_work.get("cost_usd")),
        "est_cost_usd": (
            left_work.get("est_cost_usd"), right_work.get("est_cost_usd")
        ),
    }
    for name, (left, right) in values.items():
        if (
            isinstance(left, (int, float))
            and not isinstance(left, bool)
            and isinstance(right, (int, float))
            and not isinstance(right, bool)
        ):
            delta[name] = round(float(right) - float(left), 6)
    return delta


def score_paired_round(
    run: Run, fixture: Fixture, profiles: tuple[str, str] = ("luna", "terra")
) -> Score:
    """Compare two isolated builds without collapsing quality and cost into a winner."""
    ledger = run.stage.joinpath(*TRIALS) / "trials.json"
    if not ledger.is_file():
        return Score(headline="no paired builds recorded — the round did not reach a run")

    entries = json.loads(ledger.read_text(encoding="utf-8"))
    by_profile = {str(entry.get("profile", "")): entry for entry in entries}
    missing = [profile for profile in profiles if profile not in by_profile]
    if missing:
        return Score(
            headline=f"paired build incomplete — missing {', '.join(missing)}",
            data={"trials": entries},
            caveats=("not every configured model arm ran",),
        )

    arms = {
        profile: _measure_build(run, fixture, by_profile[profile])
        for profile in profiles
    }
    caveats = tuple(
        f"{profile} exited rc {int(arms[profile]['trial']['rc'])}"
        for profile in profiles
        if int(arms[profile]["trial"]["rc"]) != 0
    )
    detail = tuple(
        f"{profile}: turns {work.get('turns', BLANK)}, "
        f"retries {work.get('backend_retries', BLANK)}, "
        f"output tokens {work.get('output_tokens', BLANK)}, "
        f"estimated cost {work.get('est_cost_usd', BLANK)}"
        for profile in profiles
        for work in [
            (arms[profile]["trial"].get("telemetry") or {}).get("work") or {}
        ]
    )
    return Score(
        headline="book comparison: " + " || ".join(
            _arm_line(profile, arms[profile]) for profile in profiles
        ),
        detail=detail,
        data={
            "arms": arms,
            "delta": _paired_delta(arms, profiles),
        },
        caveats=caveats,
    )


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

    book_judge: dict[str, Any] | None = None
    if run.param_bool("judge"):
        if not run.repo.is_dir():
            caveats.append("judge requested but the staged repo is gone — skipped")
        else:
            book_judge = judge_book(run, fixture, witness)
            if book_judge is None:
                caveats.append("judge requested but the witness minted no gradeable bullets")
            else:
                detail.append(_judge_line(book_judge))

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
            "book_judge": book_judge,
        },
        caveats=tuple(caveats),
    )
