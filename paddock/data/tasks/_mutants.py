"""The mutant round: seed a curated behavior change, run the story's QA, read the pin rate."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

import yaml
import _forensics as fx
import _frozenapp as fz
from _stablemate import TrialError, effective, no_leaks, pin_held, stablemate_checkout, uv_run
from paddock import Run, Score

POOLS = ("A", "B")

VERDICTS = ("killed", "resolved", "survivor", "inconclusive")




def load_manifest(app: Path) -> dict[str, Any]:
    path = app / "mutants.yml"
    if not path.is_file():
        raise TrialError(f"no mutant corpus at {path} — the round has nothing to run")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {
        "mutants": list(data.get("mutants") or []),
        "discards": list(data.get("discards") or []),
    }


def load_mutants(app: Path) -> list[dict[str, Any]]:
    rows = load_manifest(app)["mutants"]
    if not rows:
        raise TrialError(f"{app / 'mutants.yml'} lists no mutants")
    for row in rows:
        pool = str(row.get("pool", ""))
        if pool not in POOLS:
            raise TrialError(
                f"{app / 'mutants.yml'}: mutant {row.get('id')!r} has pool: {pool!r}; "
                f"the pools are {', '.join(POOLS)}"
            )
    return rows


def load_discards(app: Path) -> list[dict[str, Any]]:
    return load_manifest(app)["discards"]


def variant_path(app: Path, row: dict[str, Any]) -> Path:
    return app / "mutants" / str(row["id"]) / str(row["path"])


def validate_mutants(app: Path) -> list[str]:
    """Every way the corpus can be wrong *without* failing a trial, named at once."""
    problems: list[str] = []
    manifest = load_manifest(app)
    stories = {p.name for p in (app / "stories").glob("*") if p.is_dir()}
    diffs: dict[str, set[str]] = {}
    seen: set[str] = set()
    for row in load_mutants(app):
        rid, story, path = str(row.get("id")), str(row.get("story")), str(row.get("path"))
        if rid in seen:
            problems.append(f"{rid}: duplicate mutant id")
        seen.add(rid)
        if not str(row.get("behavior", "")).strip():
            problems.append(f"{rid}: no behavior line — a mutant with no stated delta is unreviewable")
        if str(row.get("pool")) == "A" and not str(row.get("bullet", "")).strip():
            problems.append(f"{rid}: pool A without a bullet: — the pool is defined by the bullet it violates")
        if story not in stories:
            problems.append(f"{rid}: story {story!r} is not one of {', '.join(sorted(stories))}")
            continue
        if story not in diffs:
            diff = fz.story_diff(app, story)
            diffs[story] = {*diff["changed"], *diff["added"]}
        if path not in diffs[story]:
            problems.append(
                f"{rid}: {path} is not in {story}'s diff — the mutant would be committed in "
                "the before tree and no obligation would be minted for it"
            )
        if not variant_path(app, row).is_file():
            problems.append(f"{rid}: no variant at {variant_path(app, row)}")
    for row in manifest["discards"]:
        rid = str(row.get("id"))
        if rid in seen:
            problems.append(f"{rid}: discarded and still listed as a mutant — it is one or the other")
        seen.add(rid)
        if not str(row.get("reason", "")).strip():
            problems.append(f"{rid}: discarded without a reason — a silent discard inflates the kill rate")
        if (app / "mutants" / rid).exists():
            problems.append(f"{rid}: discarded but its variant directory is still in the corpus")
    return problems


def select_mutants(app: Path, wanted: tuple[str, ...]) -> list[dict[str, Any]]:
    rows = load_mutants(app)
    if not wanted:
        return rows
    by_id = {str(row["id"]): row for row in rows}
    unknown = [name for name in wanted if name not in by_id]
    if unknown:
        raise TrialError(
            f"no such mutant(s): {', '.join(unknown)} (have: {', '.join(sorted(by_id))})"
        )
    return [by_id[name] for name in wanted]


def seed_mutant(app: Path, row: dict[str, Any], repo: Path) -> None:
    """Plant one mutant in a materialized tree — the same whole-file overwrite as a defect."""
    variant = variant_path(app, row)
    if not variant.is_file():
        raise TrialError(f"mutant {row['id']}: no variant at {variant}")
    diff = fz.story_diff(app, str(row["story"]))
    if str(row["path"]) not in {*diff["changed"], *diff["added"]}:
        raise TrialError(
            f"mutant {row['id']}: {row['path']} is not in {row['story']}'s diff — seeding it "
            "would plant the mutant in the before tree, outside what the trial is measured on"
        )
    target = repo / str(row["path"])
    if not target.is_file():
        raise TrialError(f"mutant {row['id']}: {row['path']} is not in the materialized tree")
    target.write_bytes(variant.read_bytes())


def mutant_survived(app: Path, row: dict[str, Any], witness: Path) -> bool:
    """Is the seeded file still byte-for-byte the variant at the end of the trial?"""
    target = witness / str(row["path"])
    if not target.is_file():
        return False
    return target.read_bytes() == variant_path(app, row).read_bytes()




def dont_cares(witness: Path) -> dict[str, list[str]]:
    """`{node id: its unspecified: bullets}` from the witness's book, or `{}`."""
    try:
        from ostler import registry
    except ImportError:
        return {}
    if "unspecified" not in getattr(registry, "SHARED_ADVISORY_KEYS", ()):
        return {}
    book = fz.load_book(witness) or {}
    cares: dict[str, list[str]] = {}
    for node in book.get("nodes", []) or []:
        value = node.get("bullets", {}).get("unspecified")
        values = [str(item) for item in (value if isinstance(value, list) else [value]) if item]
        if values:
            cares[str(node["id"])] = values
    return cares




def classify_mutant(
    row: dict[str, Any],
    statuses: dict[str, str] | None,
    audit: dict[str, Any],
    *,
    survived: bool,
    cares: dict[str, list[str]],
) -> tuple[str, str]:
    """Score one mutant trial."""
    contradicted = sorted(k for k, v in (statuses or {}).items() if v == "contradicted")
    if contradicted:
        return "killed", contradicted[0]
    if str(audit.get("verdict", "")) == "refuted":
        return "killed", "audit refutation"
    if not survived:
        return "killed", "mutant repaired"
    if statuses is None:
        return "inconclusive", "no evidence map"
    cited = str(row.get("unspecified", "") or "").strip()
    if cited and cited in cares:
        return "resolved", f"don't-care on {cited}"
    if cited:
        return "survivor", f"cites {cited}, which carries no unspecified: bullet in this book"
    return "survivor", "ran clean"


def pin_rates(trials: list[dict[str, Any]]) -> dict[str, Any]:
    """Per-pool counts and the gap."""
    pools: dict[str, dict[str, Any]] = {}
    for pool in POOLS:
        rows = [trial for trial in trials if str(trial.get("pool")) == pool]
        counts = {verdict: sum(1 for t in rows if t["verdict"] == verdict) for verdict in VERDICTS}
        denominator = len(rows) - counts["resolved"]
        rate = (
            None
            if not rows or denominator <= 0 or counts["inconclusive"]
            else counts["killed"] / denominator
        )
        pools[pool] = {**counts, "total": len(rows), "denominator": denominator, "rate": rate}
    a, b = pools["A"]["rate"], pools["B"]["rate"]
    return {"pools": pools, "gap": a - b if a is not None and b is not None else None}


def headline(trials: list[dict[str, Any]]) -> str:
    rates = pin_rates(trials)

    def shown(pool: str) -> str:
        counts = rates["pools"][pool]
        if not counts["total"]:
            return f"{pool} {fz.BLANK}"
        return f"{pool} {counts['killed']}/{counts['denominator']}"

    gap = rates["gap"]
    survivors = sum(1 for trial in trials if trial["verdict"] == "survivor")
    resolved = sum(1 for trial in trials if trial["verdict"] == "resolved")
    unknown = sum(1 for trial in trials if trial["verdict"] == "inconclusive")
    line = (
        f"pin-gap {gap:+.2f}" if gap is not None else f"pin-gap {fz.BLANK}"
    ) + (
        f"  ({shown('A')} killed, {shown('B')}, "
        f"{survivors} survivors, {resolved} resolved-by-design)"
    )
    if unknown:
        line += f"  inconclusive {unknown}"
    return line




LEDGER = "mutants.json"


def corpus_dir(run: Run, fixture: fz.Fixture) -> Path:
    """The tracked app tree, keyed on `mutants.yml` — `key_dir` with this round's key."""
    directory = run.data_dir / fixture.app
    if not (directory / "mutants.yml").is_file():
        raise TrialError(f"no mutant corpus under {directory} — is --data-dir the repo's paddock/data/?")
    return directory


def run_round(run: Run, fixture: fz.Fixture) -> None:
    """Run the corpus: materialize the mutant's story, seed it, drive QA, keep the witness."""
    app = corpus_dir(run, fixture)
    problems = validate_mutants(app)
    if problems:
        raise TrialError(f"{app / 'mutants.yml'} cannot be scored:\n  " + "\n  ".join(problems))
    rows = select_mutants(app, run.param_list("mutants") or fixture.defects)
    checkout = stablemate_checkout(run)
    budget = run.param_float("budget", fixture.budget_s)
    config = effective(run)
    runs_dir = fz.trials_dir(run) / "runs"

    with no_leaks(checkout, pinned=pin_held(run.pinned)):
        ledger: list[dict[str, Any]] = []
        for index, row in enumerate(rows, start=1):
            story, mutant = str(row["story"]), str(row["id"])
            run_id = f"{fixture.repo_dir}-{run.label}-mut-{story}-{mutant}-{index}"

            def install(repo: Path, run_id: str = run_id) -> None:
                run.cli(
                    *uv_run(checkout, "farrier"),
                    "farrier", "install", "--repo", str(repo),
                    cwd=checkout, log_name=f"{run_id}-farrier", check=True,
                )

            repo = fz.materialize(run.repo, story, run.workdir(run_id) / fixture.repo_dir, install)
            seed_mutant(app, row, repo)
            fz.reset_stack_state(repo)

            started, since = time.monotonic(), time.time()
            result = run.cli(
                *uv_run(checkout, "workhorse-workflows"),
                "workhorse-coder", "run", "qa",
                "--runs-dir", str(runs_dir), "--run-id", run_id,
                "--config", str(config),
                "--params", json.dumps(
                    {
                        "story": story, "docs_path": str(repo),
                        "stop_at_first_verdict": fixture.first_verdict,
                    }
                ),
                cwd=repo,
                env={**os.environ, "WORKHORSE_MAX_RUNTIME_S": str(budget), "AGENT_REPO_DIR": str(repo)},
                log_name=f"{run_id}-qa",
            )
            wall = time.monotonic() - started

            witness = fz.capture_witness(
                repo, fz.trials_dir(run) / run_id / "witness", extra=(str(row["path"]),)
            )
            ledger.append({
                "run_id": run_id, "story": story, "mutant": mutant,
                "pool": str(row["pool"]),
                "bullet": str(row.get("bullet", "") or ""),
                "path": str(row["path"]),
                "rc": result.returncode,
                "audit_turn": not fixture.first_verdict,
                "witness": str(witness.relative_to(run.stage)),
                "timing": fx.timing_of(run_id, wall, since),
                "laps": fx.laps_of(run_id, since),
            })
            run.write_json(fz.trials_dir(run) / LEDGER, ledger)


def score_round(run: Run, fixture: fz.Fixture) -> Score:
    """The pin-rate gap beside the leverage scorecard — read entirely from the stage."""
    ledger = run.stage.joinpath(*fz.TRIALS) / LEDGER
    if not ledger.is_file():
        return Score(headline="no mutants recorded — the round did not reach a run", detail=())

    app = corpus_dir(run, fixture)
    by_id = {str(row["id"]): row for row in load_mutants(app)}
    trials: list[dict[str, Any]] = []
    for entry in json.loads(ledger.read_text(encoding="utf-8")):
        row = by_id[str(entry["mutant"])]
        witness = run.stage / str(entry["witness"])
        statuses = fz.evidence_statuses(witness, str(entry["story"]))
        audit = fz.audit_result(run.stage.joinpath(*fz.TRIALS) / "runs", str(entry["run_id"]))
        verdict, because = classify_mutant(
            row,
            statuses,
            audit,
            survived=mutant_survived(app, row, witness),
            cares=dont_cares(witness),
        )
        trials.append({
            **entry,
            "verdict": verdict,
            "because": because,
            "defect": f"{entry['mutant']}:{entry['pool']}",
            "obligation": str(row.get("bullet", "") or "") or f"pool B · {entry['path']}",
            "leverage": fz.leverage(witness, str(entry["story"]), statuses),
        })

    return Score(
        headline=headline(trials),
        detail=tuple(fz.detail(trials, fixture.leverage)),
        data={"trials": trials, "pin": pin_rates(trials), "leverage": fz.pool_leverage(trials)},
    )
