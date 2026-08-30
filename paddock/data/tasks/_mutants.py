"""The mutant round: seed a curated behavior change, run the story's QA, read the pin rate.

A mutant is a defect nobody wrote an answer-key row for — a behavior change generated
against the *code*, so the corpus can ask questions the book never answered. The round
machinery is therefore `_frozenapp`'s with the answer key swapped out: same materialize,
same seeding overwrite, same witness, same evidence map. What changes is the verdict
vocabulary — a mutant is `killed`, `resolved-by-design`, a `survivor` or `inconclusive`,
never caught or missed, because there is no expectation to miss — and the headline, which
is the **pin-rate gap**: how much detection exists only where the book already speaks
(`docs/plans/qa-mutation-negative-space.md`, phase 4).

The corpus lives beside the answer key — `mutants/<id>/<path>` variants under a
`mutants.yml` manifest — and is **curated once, then frozen**: no mutation operators run
at trial time, ever. A row carries:

  - `id`, `story` (the diff scope its trial runs), `path` (the file the variant
    overwrites), `symbols` (where the change lands, for the corpus tests to hold against
    the story's owed obligations), and a one-line `behavior` delta;
  - `pool: A` — the mutant violates a normative bullet the story owes, named in
    `bullet:` as the obligation id. **This is the relaxed pool-A rule**: the plan defines
    pool A by "violates a bullet that compiles into a probe", but the bullet→probe
    compiler does not exist yet, so membership is "violates a bullet whose obligation the
    mutant's story owes" — verifiable today with the app's own book machinery — and this
    header is where that relaxation is recorded;
  - `pool: B` — curated from the code with the book deliberately closed; no `bullet:`,
    because the pool exists to find behavior no bullet covers;
  - `unspecified:` — empty at curation, filled at triage with the node id whose grounded
    `unspecified:` bullet answers the survivor. The scorer believes it only if the
    witness's book actually carries that don't-care (`dont_cares`).

The manifest also logs `discards:` — candidates the equivalence gate threw out because no
battery run distinguished them from control. Logged rather than deleted, because silent
filtering would quietly inflate kill rates; a discard has a `reason` and **no** variant
directory.

The leading underscore keeps `paddock.loader` from treating this as a task module: it is
the library each mutant task module imports, not a second declaration.
"""

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

#: The two pools the gap is read across. Membership is stamped at curation time and never
#: recomputed: pool A is the health check on the plans (its kill rate should be near
#: ceiling), pool B is the plan's reason to exist.
POOLS = ("A", "B")

#: The verdicts a mutant trial can land on. `killed` — some check contradicted, the
#: auditor refuted, or the flow repaired the seeded file; `resolved` — the diff lands
#: inside a grounded don't-care the witness's book carries; `survivor` — ran clean, and
#: the book has no answer for it yet; `inconclusive` — the harness failed before the
#: question was asked.
VERDICTS = ("killed", "resolved", "survivor", "inconclusive")


# ── the corpus ────────────────────────────────────────────────────────────────────────


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
    """Every way the corpus can be wrong *without* failing a trial, named at once.

    The same trap `validate_defects` guards: a mutant whose `path` is outside its story's
    diff is seeded into the *before* tree, nothing in the run under measurement is asked
    about it, and the row scores as a survivor against QA for a fixture bug. The discard
    rules live here too — a discard with a variant directory is a mutant someone half
    removed, and the next reader cannot tell whether the row or the directory is the lie.
    """
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
    """Is the seeded file still byte-for-byte the variant at the end of the trial?

    The same witness `defect_survived` reads, for the same reason: a flow that triaged the
    mutant as a code failure and repaired it ends with every obligation `covered`, and only
    the seeded file distinguishes that loudest possible kill from a run that never noticed.
    """
    target = witness / str(row["path"])
    if not target.is_file():
        return False
    return target.read_bytes() == variant_path(app, row).read_bytes()


# ── the don't-care vocabulary ─────────────────────────────────────────────────────────


def dont_cares(witness: Path) -> dict[str, list[str]]:
    """`{node id: its unspecified: bullets}` from the witness's book, or `{}`.

    The one function that touches the `unspecified:` vocabulary, so the dependency on it
    is isolated here: an ostler without `SHARED_ADVISORY_KEYS` (or no ostler at all)
    returns `{}`, and every triage citation then reads as a survivor rather than a crash.
    An empty map is honest either way — a book with no don't-cares has answered nothing
    by design, and doctor's `ungrounded-unspecified` gate is what keeps the bullets this
    reads grounded rather than decorative.
    """
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


# ── classification ────────────────────────────────────────────────────────────────────


def classify_mutant(
    row: dict[str, Any],
    statuses: dict[str, str] | None,
    audit: dict[str, Any],
    *,
    survived: bool,
    cares: dict[str, list[str]],
) -> tuple[str, str]:
    """Score one mutant trial. Returns `(verdict, the thing that decided it)`.

    A kill has the same three routes as a catch, because the flow has the same three
    places a behavior change can surface: an obligation `contradicted` in the evidence
    map, an auditor refutation, or the seeded file repaired out from under the trial.
    Which one fired is recorded, because phase 3's triage reads it — a kill names the
    bullet or turn that did the work.

    `resolved` is believed only against the witness: the row's `unspecified:` citation
    names a node, and the verdict requires that node to actually carry a don't-care in
    the book the trial ran under. A citation the book does not back is a survivor with
    its staleness named, not a resolution — otherwise editing the manifest would be a
    way to make survivors green without writing anything.

    `inconclusive` is the harness failing, exactly as in `classify`: no evidence map
    means the question was never asked, and averaging that into a kill rate would report
    an outage as detection data.
    """
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
    """Per-pool counts and the gap. `kill(X) = killed / (|X| − resolved)`, equivalents
    already filtered by the curation gate.

    A pool's rate is None — never a number — when it is empty, when resolutions consume
    it whole, or when any of its trials came back inconclusive: a rate computed over an
    outage says something about this machine, and the headline prints `–` for it instead.
    """
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
        # Loudly, and never folded into a rate: an inconclusive trial is the harness
        # failing, and it already blanked its pool's rate above.
        line += f"  inconclusive {unknown}"
    return line


# ── the round, run ────────────────────────────────────────────────────────────────────


#: The mutant round's own ledger, beside `_frozenapp`'s `trials.json` rather than in it:
#: the two rounds score with different classifiers, and a shared file would need every
#: reader to re-derive which machinery wrote each entry.
LEDGER = "mutants.json"


def corpus_dir(run: Run, fixture: fz.Fixture) -> Path:
    """The tracked app tree, keyed on `mutants.yml` — `key_dir` with this round's key.

    The same ruler-outside-the-measurement rule as `key_dir`: the corpus is read from the
    copy git tracks, never from the unpacked seed. It cannot *be* `key_dir`, because that
    one insists on `defects.yml`, and an app curated for mutants before its answer key
    exists (or vice versa) is a legitimate tree.
    """
    directory = run.data_dir / fixture.app
    if not (directory / "mutants.yml").is_file():
        raise TrialError(f"no mutant corpus under {directory} — is --data-dir the repo's paddock/data/?")
    return directory


def run_round(run: Run, fixture: fz.Fixture) -> None:
    """Run the corpus: materialize the mutant's story, seed it, drive QA, keep the witness.

    `_frozenapp.run_round` with the answer key swapped for the manifest, and two deliberate
    absences: no clean control — the false-alarm baseline is the `-qa` task's job, and a
    control per mutant story would re-buy it every round — and no `expect`, because a
    mutant is a question, not an expectation. The diff scoping the plan asks for is the
    manifest's `story:` field: curation already recorded which story's obligations touch
    the mutated symbols, so the trial runs exactly that story's QA and nothing else.
    """
    app = corpus_dir(run, fixture)
    problems = validate_mutants(app)
    if problems:
        raise TrialError(f"{app / 'mutants.yml'} cannot be scored:\n  " + "\n  ".join(problems))
    # `fixture.defects` is the fixture's standing scope for the round — the same field the
    # defect round narrows on, holding mutant ids here — and `--param mutants=…` overrides
    # it, because narrowing a run is the operator's call.
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
    """The pin-rate gap beside the leverage scorecard — read entirely from the stage.

    Recomputed rather than recorded, for the same reason `_frozenapp.score_round` is: a
    sealed result stays re-scorable after the classifier changes. The leverage line rides
    along because a corpus killed entirely by URL fetches and one killed by walking the
    product are the same gap and different books.
    """
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
            # What `_frozenapp.detail` prints in its first two columns, so the mutant
            # table and the defect table read the same way in a round's scrollback.
            "defect": f"{entry['mutant']}:{entry['pool']}",
            "obligation": str(row.get("bullet", "") or "") or f"pool B · {entry['path']}",
            "leverage": fz.leverage(witness, str(entry["story"]), statuses),
        })

    return Score(
        headline=headline(trials),
        detail=tuple(fz.detail(trials, fixture.leverage)),
        data={"trials": trials, "pin": pin_rates(trials), "leverage": fz.pool_leverage(trials)},
    )
