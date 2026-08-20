"""The greenfield round: build a repo out of a backlog, then ask what the backlog got.

One round, three workflow phases and a ruler:

    genesis → the skeleton, one invocation per surface
    backlog → the benchmark's input, copied in so every run starts from the same bullets
    author  → epics and stories
    coder   → the implementation
    gates   → the produced repo's own `build` / `test`, run once and recorded

and then a score that traces each bullet to the epic claiming it, has a **pinned** agent
read the repo and rate it 0–3, and reports the machinery's reliability beside the rating —
because "a valid repo appeared" and "the machinery got there on its own" come apart, and
reading only the end state scores a run that needed rescuing as a success.

This module names no app. What distinguishes link-shortener from expense-split is a
`Fixture`: which backlog, which surfaces, which gates, which judge. The round is shared
for the same reason the frozen-app round is — a task module that re-implemented it would
be a second place to fix every change to it.

The leading underscore keeps `paddock.loader` from treating this as a task module.
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import _forensics as fx
from _stablemate import TrialError, effective, git, stablemate_checkout
from ostler import markdown
from paddock import Run, Score
from workhorse.config_run import AgentResilience
from workhorse.runner import caps as wh_caps
from workhorse.runner import extract as wh_extract
from workhorse.runner import failure as wh_failure
from workhorse.runner.backends import AgentBackend
from workhorse.runner.backends.registry import get_backend
from workhorse.runner.clock import SYSTEM_CLOCK, Clock

logger = logging.getLogger(__name__)

# ── the rubric. One definition, used by the prompt, the parser and the report ──────────

LEVELS = {
    0: ("absent", "nothing in the repo claims this bullet"),
    1: ("planned", "a story exists that would deliver it; no implementing code"),
    2: ("built", "implementing code exists on every surface the bullet implies"),
    3: ("verified", "built, and executable evidence exercises it"),
}
MAX_LEVEL = 3


# `- [kebab-id] A person does something observable.` — the benchmark's unit of input. The
# bullet itself is read off `ostler.markdown`; this only says whether the handle it carries
# is one of ours, which is an identifier validator rather than a format parser.
KEBAB_ID = re.compile(r"[a-z0-9][a-z0-9-]*\Z")

#: The heading under which an epic records the backlog bullets it claims.
COVERED_HEADING = "Backlog bullets covered"

#: Where the round's own ledger and run dirs live inside the stage. Named explicitly
#: rather than via `run.artifacts`, because that property is relative to the *current
#: step* and both the later steps and `score` read what the earlier ones wrote.
BUILD = ("artifacts", "build")


# ── the fixture ───────────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class Surface:
    """One service genesis scaffolds: a stack, a root inside the repo, an init command."""

    service: str
    service_root: str
    packs: str = ""
    scaffolds: str = ""
    init_cmd: str = ""
    marker: str = ""
    markers: str = ""


@dataclass(frozen=True, slots=True)
class Check:
    """A gate the produced repo runs on itself. Exit code, nothing more."""

    name: str
    cmd: str
    timeout_s: float = 900.0


@dataclass(frozen=True, slots=True)
class Fixture:
    """Everything that distinguishes one greenfield task from another."""

    #: The tracked backlog, relative to the data directory. Copied in rather than
    #: generated: the whole point is that every run starts from the same bullets, so an
    #: outcome is attributable to the workflows and not to a backlog that drifted.
    backlog: str
    #: Where that backlog lands inside the repo, and the `backlog` param author is given.
    backlog_path: str = "docs/backlog.md"
    #: The surfaces genesis scaffolds, in order. The first one carries the docs scaffold.
    surfaces: tuple[Surface, ...] = ()
    #: Repo-level (process) packs, unioned into every surface's `agents.yml`.
    packs: str = ""
    #: The docs scaffold, which rides along with the first surface so `docs/epics/` exists
    #: before anything reads the graph. Farrier skips files that are already present.
    docs_scaffold: str = ""
    #: The produced repo's own gates. They do not feed the score — a half-built repo
    #: failing its own tests is expected — but a bullet scored `verified` while the suite
    #: that would prove it is red is a finding, and that needs both numbers.
    checks: tuple[Check, ...] = ()
    #: The judge's backend, pinned by the fixture. See `judge_backlog` for why.
    judge_cli: str = ""
    judge_model: str = ""
    judge_effort: str = ""
    #: Wall-clock ceiling per phase, in seconds. Enforced by workhorse *between* states,
    #: so an over-budget phase stops at a node boundary with its checkpoint and telemetry
    #: intact — the difference between a time limit and a `kill`.
    budget_s: dict[str, float] = field(default_factory=dict)

    def params(self, repo: Path, surface: Surface) -> str:
        """The flow params for one `workhorse-coder run genesis` invocation."""
        joined = lambda *xs: ",".join(x for x in xs if x)  # noqa: E731
        return json.dumps({
            "target": str(repo),
            "service": surface.service,
            "service_root": surface.service_root,
            "packs": joined(self.packs, surface.packs),
            "scaffolds": joined(self.docs_scaffold, surface.scaffolds),
            "init_cmd": surface.init_cmd,
            "marker": surface.marker,
            "markers": surface.markers,
            "workflows": "coder,author",
        })


# ── the round, run ────────────────────────────────────────────────────────────────────


def build_dir(run: Run) -> Path:
    directory = run.stage.joinpath(*BUILD)
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def runs_dir(run: Run) -> Path:
    """Where every phase's run dir goes.

    Run artifacts (`events.jsonl`, per-node output) are this benchmark's EVIDENCE, so they
    live in the staged result rather than wherever workhorse would default them — which is
    under the library dir, checked out and reinstalled between runs. A whole round's
    evidence vanished that way once, and the reliability report then cheerfully answered
    "no runs recorded yet" rather than noticing its own history had been erased.
    """
    directory = build_dir(run) / "runs"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def budget_of(run: Run, fixture: Fixture, phase: str) -> float:
    return run.param_float(f"budget_{phase}", float(fixture.budget_s.get(phase) or 0.0))


def phase_env(run: Run, fixture: Fixture, phase: str) -> dict[str, str]:
    """The environment one phase is launched with: which repo, and how long it may take.

    The models are *not* here — they come from `--config`, whole-file, so a round's tier is
    the tracked config's rather than whatever this machine happens to have set.
    """
    env = {**os.environ, "AGENT_REPO_DIR": str(run.repo)}
    budget = budget_of(run, fixture, phase)
    if budget > 0:
        env["WORKHORSE_MAX_RUNTIME_S"] = str(budget)
    return env


def ledger_path(run: Run) -> Path:
    return build_dir(run) / "build.json"


def record(run: Run, phase: str, *, rc: int, wall_s: float) -> None:
    """Append one phase's outcome to the round's ledger, rewritten after each phase.

    Written as it goes rather than at the end: a round that dies in `coder` still has to
    say what genesis and author cost, and the wall-clock is the only number in this report
    that cannot be recovered from the staged tree afterwards.
    """
    path = ledger_path(run)
    phases = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else []
    phases.append({"phase": phase, "rc": rc, "wall_s": round(wall_s, 1)})
    run.write_json(path, phases)


def phases_of(run: Run) -> list[dict[str, Any]]:
    path = ledger_path(run)
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else []


def run_genesis(run: Run, fixture: Fixture) -> None:
    """Scaffold every surface, then seed the backlog into the tree genesis just made."""
    # `--project` rather than an inherited cwd, and `cwd=run.repo` for every phase: the
    # round's processes stand *in the tree under test*, so uv is told where its workspace
    # is instead of finding it underfoot. The same rule the frozen-app round follows.
    checkout = stablemate_checkout(run)
    for surface in fixture.surfaces:
        started = time.monotonic()
        result = run.cli(
            "uv", "run", "--project", str(checkout),
            "workhorse-coder", "run", "genesis",
            "--runs-dir", str(runs_dir(run)),
            "--config", str(effective(run)),
            "--params", fixture.params(run.repo, surface),
            cwd=run.repo,
            env=phase_env(run, fixture, "genesis"),
            log_name=f"genesis-{surface.service}",
        )
        record(run, f"genesis-{surface.service}", rc=result.returncode,
               wall_s=time.monotonic() - started)
        if result.returncode != 0:
            raise TrialError(
                f"genesis failed for surface {surface.service!r} (exit {result.returncode}) "
                f"— see {result.log}"
            )
    seed_backlog(run, fixture)


def seed_backlog(run: Run, fixture: Fixture) -> None:
    """Copy the tracked backlog into the produced repo.

    Read from `run.data_dir`, the copy git tracks and `check_public.py` scans — never from
    the tree the round is about to mutate. Same rule the frozen-app answer key follows: a
    benchmark whose input travels inside the thing being measured measures nothing.
    """
    source = run.data_dir / fixture.backlog
    if not source.is_file():
        raise TrialError(f"no backlog at {source} — is --data-dir the repo's benchmarks/?")
    destination = run.repo / fixture.backlog_path
    if not destination.parent.is_dir():
        raise TrialError(f"no {destination.parent} — genesis did not scaffold the docs tree")
    destination.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")


def run_phase(run: Run, fixture: Fixture, phase: str, *argv: str) -> None:
    """Drive one workflow phase and record what it cost.

    A non-zero exit is recorded rather than raised: the phase left a run dir with a
    checkpoint in it, the evidence is staged, and the score is still readable — a
    budget-exhausted `coder` is a measurement, not an aborted round. What must never
    happen is *silence*, so the rc travels in the ledger and into the score's detail.
    """
    checkout = stablemate_checkout(run)
    started = time.monotonic()
    result = run.cli(
        "uv", "run", "--project", str(checkout),
        *argv,
        "--runs-dir", str(runs_dir(run)),
        "--config", str(effective(run)),
        cwd=run.repo,
        env=phase_env(run, fixture, phase),
        log_name=phase,
    )
    record(run, phase, rc=result.returncode, wall_s=time.monotonic() - started)


def run_author(run: Run, fixture: Fixture) -> None:
    if not (run.repo / fixture.backlog_path).is_file():
        raise TrialError(f"no backlog at {run.repo / fixture.backlog_path} — genesis first")
    run_phase(
        run, fixture, "author",
        "workhorse-author", "run",
        "--params", json.dumps({"backlog": fixture.backlog_path}),
    )


def run_coder(run: Run, fixture: Fixture) -> None:
    if not find_epics(run.repo):
        raise TrialError("no epic queue — author produced no epics to implement")
    run_phase(
        run, fixture, "coder",
        "workhorse-coder", "run",
        "--params", json.dumps({"docs_path": str(run.repo)}),
    )


def run_gates(run: Run, fixture: Fixture) -> None:
    """Run the produced repo's own gates once, and stage the result.

    A step rather than part of the score, because running them mutates the tree — a build
    writes objects, a test writes caches — and `score` is read-only over the stage. Staging
    the exit codes is also what makes a sealed result re-readable: the gate that was red
    stays red in the zip, on a machine that never had the toolchain.
    """
    results: list[dict[str, Any]] = []
    for check in fixture.checks:
        try:
            proc = subprocess.run(
                check.cmd, shell=True, cwd=str(run.repo), capture_output=True,
                text=True, timeout=check.timeout_s, check=False,
            )
            rc: int | None = proc.returncode
            tail = (proc.stdout + proc.stderr).strip().splitlines()[-3:]
        except subprocess.TimeoutExpired:
            rc, tail = None, [f"timed out after {check.timeout_s:.0f}s"]
        except OSError as exc:
            rc, tail = None, [str(exc)]
        results.append({"name": check.name, "cmd": check.cmd, "exit": rc, "tail": tail})
    run.write_json(build_dir(run) / "gates.json", results)


def run_round(run: Run, fixture: Fixture) -> None:
    """The whole build, as one step: genesis, backlog, author, coder, gates.

    One step rather than five, so a round is one entry in the ledger and one thing to
    resume thinking about. The phases are still separately recorded — see `build.json`.
    """
    checkout = stablemate_checkout(run)
    before = git("rev-parse", "HEAD", cwd=checkout).strip()

    run_genesis(run, fixture)
    run_author(run, fixture)
    run_coder(run, fixture)
    run_gates(run, fixture)

    leaked = git("log", "--oneline", f"{before}..HEAD", cwd=checkout).strip()
    if leaked:
        # Not a warning. An agent that resolved its project root to the harness's own
        # checkout committed the round's work there, which means the tree it was measured
        # on is not the tree it wrote to — every number in the report is void.
        # Read against the tree paddock pinned for this round, which nobody else
        # writes to — so a commit here is a leak by construction rather than by
        # heuristic, and an operator committing in their own checkout is invisible.
        raise TrialError(
            f"the round committed into {checkout} instead of its sandbox:\n{leaked}\n"
            f"drop those commits before believing any number here"
        )


# ── evidence: what the round actually produced ────────────────────────────────────────


def parse_backlog(path: Path) -> list[dict[str, Any]]:
    """The `- [kebab-id] text` bullets, in file order. The benchmark's unit of input.

    Parsed rather than matched line by line: a backlog that shows its own grammar in a
    fenced example must not have that example scored as work the round was asked to do.
    """
    if not path.is_file():
        return []
    out: list[dict[str, Any]] = []
    for bullet in markdown.split(path.read_text(encoding="utf-8")).walk_bullets():
        bid, text = bullet.bracketed
        if KEBAB_ID.fullmatch(bid) and text.strip():
            out.append({"id": bid, "text": " ".join(text.split())})
    return out


def find_epics(repo: Path) -> list[Path]:
    return sorted(repo.glob("docs/epics/*/epic.md"))


def frontmatter(md: Path) -> dict[str, str]:
    """The `---`-delimited YAML header, as flat strings. Missing/malformed → empty.

    The fence is located by the same parser the doc graph uses, so a `---` inside a block
    scalar closes nothing and this reads the header the tooling wrote.
    """
    try:
        text = md.read_text(encoding="utf-8")
    except OSError:
        return {}
    data = markdown.split(text).frontmatter
    return {str(k): str(v) for k, v in data.items()} if isinstance(data, dict) else {}


def is_done(status: str) -> bool:
    """Story frontmatter uses prose statuses ('Not started', 'QA passed', 'Done')."""
    return status.strip().lower() in {"done", "qa passed", "complete", "completed", "merged"}


def trace_bullets(run: Run, fixture: Fixture) -> list[dict[str, Any]]:
    """Trace each backlog bullet to the epic that claims it and that epic's stories.

    Author records coverage as a `## Backlog bullets covered` list of `[kebab-id]`s in each
    `epic.md`, so backlog→epic is deterministic. Stories carry no bullet id, so story→bullet
    is not — which is exactly why the judge exists. The stories are handed to the judge as
    *context*, never as a coverage claim in themselves.

    The bullets themselves are read from the tracked backlog rather than from the copy in
    the produced repo: a round that edited its own inputs would otherwise be scored against
    the backlog it decided to have.
    """
    bullets = parse_backlog(run.data_dir / fixture.backlog)

    claims: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for epic_md in find_epics(run.repo):
        doc = markdown.split(epic_md.read_text(encoding="utf-8"))
        stories = [
            {"slug": s.parent.name, "status": frontmatter(s).get("status", "unknown")}
            for s in sorted(epic_md.parent.glob("stories/*/story.md"))
        ]
        info = {"epic": epic_md.parent.name, "stories": stories}
        # The claim is the `## Backlog bullets covered` list, read as a list. An epic that
        # never wrote the section falls back to every IDed bullet in the file, which is
        # what a whole-text scan approximated — minus the prose and fenced mentions it
        # also counted, which is the point of parsing.
        section = doc.find_section(COVERED_HEADING)
        claimed = (
            [b for top in section.bullets for b in top.walk()]
            if section is not None
            else doc.walk_bullets()
        )
        for bid in {b.bracketed[0] for b in claimed}:
            if KEBAB_ID.fullmatch(bid):
                claims[bid].append(info)

    for bullet in bullets:
        owners = claims.get(str(bullet["id"]), [])
        bullet["epics"] = [o["epic"] for o in owners]
        bullet["stories"] = [s for o in owners for s in o["stories"]]
        bullet["stories_done"] = [s for s in bullet["stories"] if is_done(s["status"])]
    return bullets


def git_commits(repo: Path) -> int:
    try:
        out = subprocess.run(["git", "-C", str(repo), "log", "--oneline"],
                             capture_output=True, text=True, timeout=30, check=False)
        return len(out.stdout.splitlines()) if out.returncode == 0 else 0
    except (OSError, subprocess.SubprocessError):
        return 0


# ── the judge ─────────────────────────────────────────────────────────────────────────


def render(template: str, **fields: str) -> str:
    """Fill `{{name}}` placeholders in the rubric.

    Deliberately not `str.format`: the rubric shows the judge a JSON response shape, and
    every brace in that example would have to be doubled to survive `format` — an editing
    hazard in the one file whose whole purpose is to be edited and tuned.
    """
    for key, value in fields.items():
        template = template.replace("{{" + key + "}}", value)
    return template


@dataclass(frozen=True, slots=True)
class Judge:
    """The agent CLI plus the two dependencies its recovery ladder needs.

    `run_turn`, `cap_delay_seconds` and `sleep_with_notice` each take the resilience
    settings and the clock, so the three travel together through every judging call —
    context, not per-call inputs. Built once at the edge (`judge_backlog`) so every judged
    bullet shares one policy.
    """

    backend: AgentBackend
    resilience: AgentResilience
    clock: Clock
    model: str = ""
    effort: str = ""


def call_agent(judge: Judge, prompt: str, *, node_id: str, repo: Path,
               attempts: int = 4) -> str:
    """One agent turn, waiting out usage caps the same way workhorse itself does.

    Reuses workhorse's cap classification and sleep helpers rather than reimplementing
    them, so a benchmark scored overnight behaves like a workflow run overnight instead of
    failing at the first cap. A node sleeping on a cap ceiling is healthy and must never be
    disturbed — the same rule the timing report is built around.
    """
    last = ""
    for attempt in range(attempts):
        try:
            return judge.backend.run_turn(
                prompt, node_id, None,
                model=judge.model or None,
                timeout=judge.resilience.result_timeout_s,
                resilience=judge.resilience,
                cwd=str(repo),
                effort=judge.effort or None,
            )
        except wh_failure.BackendInvocationError as exc:
            last = str(exc)
            if wh_failure.is_cap(last):
                delay, when = wh_caps.cap_delay_seconds(
                    exc, resilience=judge.resilience, clock=judge.clock)
                wh_caps.sleep_with_notice(
                    delay, node_id, when, resilience=judge.resilience, clock=judge.clock)
            elif attempt < attempts - 1:
                time.sleep(5 * (attempt + 1))
            else:
                break
        except Exception as exc:  # noqa: BLE001 - a judge failing must not lose the other 17
            last = str(exc)
            break
    logger.warning("[%s] judge failed: %s", node_id, last[:200])
    return ""


def judge_one(judge: Judge, bullet: dict[str, Any], rubric: str, repo: Path) -> dict[str, Any]:
    """Score one backlog bullet by having an agent read the produced repo.

    One turn per bullet, not one turn for the whole backlog: a focused turn over a
    four-surface repo gives a far more reliable answer than one turn asked to hold eighteen
    judgements at once, and a failure is isolated to the bullet it belongs to.
    """
    prompt = render(
        rubric,
        bullet_id=str(bullet["id"]),
        bullet_text=str(bullet["text"]),
        target=str(repo),
        epics=", ".join(bullet["epics"]) or "(none — no epic claims this bullet)",
        stories="\n".join(f"  - {s['slug']} — {s['status']}" for s in bullet["stories"])
                or "  (none)",
        levels="\n".join(f"  {n} {name} — {desc}" for n, (name, desc) in LEVELS.items()),
    )
    text = call_agent(judge, prompt, node_id=f"judge_{bullet['id']}", repo=repo)
    # Reuse workhorse's own response parser — the tested one that already handles fenced
    # blocks, bare objects and the tolerant repair pass — rather than a second parser that
    # would drift from it.
    parsed = wh_extract.parse_json_from_text(text, ["level", "evidence", "reason"]) or {}

    try:
        level = max(0, min(MAX_LEVEL, int(parsed.get("level", 0))))
    except (TypeError, ValueError):
        level = 0
    evidence = [str(e) for e in (parsed.get("evidence") or []) if str(e).strip()]
    reason = str(parsed.get("reason") or "").strip() or "(judge returned no reason)"

    # The anti-hallucination check. A behavioral claim is only as good as the code it
    # points at, and the judge's most common failure is citing a file that does not exist.
    # Verifying the cited paths is deterministic and cheap, so a level ≥2 whose citations
    # do not resolve is capped at `planned` and flagged rather than believed.
    bad = [e for e in evidence if not (repo / e.split(":", 1)[0].strip()).exists()]
    unverified = bool(bad) or (level >= 2 and not evidence)
    if unverified and level >= 2:
        level = 1
    return {**bullet, "level": level, "evidence": evidence, "reason": reason,
            "unverified_citations": bad, "capped": unverified}


def judge_backlog(run: Run, fixture: Fixture, bullets: list[dict[str, Any]],
                  jobs: int) -> list[dict[str, Any]]:
    rubric_path = run.data_dir / "rubric.md"
    if not rubric_path.is_file():
        raise TrialError(f"no rubric at {rubric_path}")
    # The fixture's CLI outranks `$AGENT_CLI`, and that precedence is the whole point
    # rather than a convenience: `get_backend()` falls back to the environment, so an
    # unpinned judge would switch backends in step with the thing it is grading. Every
    # round would then be scored by a different grader, and a delta between two rounds
    # would carry no information about either — the benchmark measuring its own instrument.
    judge = Judge(
        get_backend(fixture.judge_cli or None), AgentResilience.from_env(), SYSTEM_CLOCK,
        model=fixture.judge_model, effort=fixture.judge_effort,
    )
    rubric = rubric_path.read_text(encoding="utf-8")
    logger.info("judging %d bullet(s) with %s, %d at a time", len(bullets), judge.backend.name, jobs)
    with ThreadPoolExecutor(max_workers=max(1, jobs)) as pool:
        return list(pool.map(lambda b: judge_one(judge, b, rubric, run.repo), bullets))


def structural_only(bullets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The levels a score with no judge is entitled to claim.

    An epic claims it (`planned`) or nothing does (`absent`). Never `built` — that is
    precisely the claim static structure cannot make.
    """
    return [{**b, "level": 1 if b["epics"] else 0, "evidence": [], "capped": False,
             "unverified_citations": [],
             "reason": "claimed by an epic" if b["epics"] else "no epic claims it"}
            for b in bullets]


# ── the report ────────────────────────────────────────────────────────────────────────


def bullet_table(bullets: list[dict[str, Any]]) -> list[str]:
    lines = [
        f"  {'bullet':<28}{'level':<12}{'epic ✓/n':>9}  why",
        f"  {'-' * 86}",
    ]
    for b in sorted(bullets, key=lambda x: -int(x["level"])):
        name = LEVELS[int(b["level"])][0]
        flag = " ⚠" if b.get("capped") else ""
        done = f"{len(b['stories_done'])}/{len(b['stories'])}"
        lines.append(f"  {b['id']:<28}{b['level']} {name:<10}{done:>9}  {str(b['reason'])[:44]}{flag}")
    lines.append(f"  {'-' * 86}")
    # Stories are counted per *epic*, not per bullet — author records coverage on the epic,
    # so every bullet in one epic shares its story tally. It is context for reading the
    # level, never an input to it.
    lines.append("  epic ✓/n = done stories / all stories in the epic(s) claiming the bullet")
    return lines


def satisfaction(bullets: list[dict[str, Any]]) -> float:
    if not bullets:
        return 0.0
    return 100.0 * sum(int(b["level"]) for b in bullets) / (MAX_LEVEL * len(bullets))


def warnings(bullets: list[dict[str, Any]], checks: list[dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    capped = [b for b in bullets if b.get("capped")]
    if capped:
        lines.append(f"  ⚠ {len(capped)} bullet(s) capped at `planned`: the judge claimed "
                     "built/verified but cited repo paths that do not exist. Treat these as")
        lines.append("    unproven, not as near-misses:")
        for b in capped:
            missing = ", ".join(b["unverified_citations"]) or "(no citation at all)"
            lines.append(f"      - {b['id']}: {missing}")

    red = [c for c in checks if c["exit"] != 0]
    verified = [b for b in bullets if int(b["level"]) == MAX_LEVEL]
    if red and verified:
        lines.append(f"  ⚠ {len(verified)} bullet(s) scored `verified` while {len(red)} repo "
                     f"gate(s) are red ({', '.join(str(c['name']) for c in red)}).")
        lines.append("    Executable evidence that does not execute is not evidence.")
    return lines


def gate_lines(checks: list[dict[str, Any]]) -> list[str]:
    lines = ["", "  repo gates"]
    if not checks:
        lines.append("  (none declared)")
        return lines
    for c in checks:
        mark = "✓" if c["exit"] == 0 else "✗"
        lines.append(f"  {mark} {str(c['name']):<10} exit={c['exit']}")
        if c["exit"] != 0:
            lines.extend(f"      {line}" for line in c["tail"])
    return lines


def phase_lines(phases: list[dict[str, Any]]) -> list[str]:
    lines = ["", "  phases"]
    if not phases:
        return [*lines, "  (nothing recorded — the round did not reach a workflow)"]
    for p in phases:
        mark = "✓" if p["rc"] == 0 else "✗"
        lines.append(f"  {mark} {str(p['phase']):<20}{fx.minutes(float(p['wall_s'])):>8}  exit={p['rc']}")
    total = sum(float(p["wall_s"]) for p in phases)
    lines.append(f"    {'total':<20}{fx.minutes(total):>8}")
    return lines


def headline(bullets: list[dict[str, Any]], checks: list[dict[str, Any]]) -> str:
    pct = satisfaction(bullets)
    total = sum(int(b["level"]) for b in bullets)
    green = sum(1 for c in checks if c["exit"] == 0)
    gates = f"{green}/{len(checks)} gates green" if checks else "no gates declared"
    return (f"backlog satisfaction {pct:.0f}% ({total}/{MAX_LEVEL * max(1, len(bullets))} "
            f"across {len(bullets)} bullets) — {gates}")


def score_round(run: Run, fixture: Fixture) -> Score:
    """The rating beside what it cost and beside whether the machinery got there alone.

    Read-only over the stage. The judge reads the produced repo and the rubric; everything
    else is recomputed from what the round staged, so a sealed result can be re-scored
    after the rubric changes without rebuilding the repo.
    """
    bullets = trace_bullets(run, fixture)
    only = set(run.param_list("only"))
    if only:
        bullets = [b for b in bullets if b["id"] in only]
    if not bullets:
        return Score(headline=f"no backlog bullets found in {fixture.backlog}")

    gates = build_dir(run) / "gates.json"
    checks: list[dict[str, Any]] = (
        json.loads(gates.read_text(encoding="utf-8")) if gates.is_file() else []
    )

    bullets = (
        judge_backlog(run, fixture, bullets, int(run.param_float("jobs", 4.0)))
        if run.param_bool("judge", True)
        else structural_only(bullets)
    )

    tally: dict[int, int] = defaultdict(int)
    for b in bullets:
        tally[int(b["level"])] += 1
    runs = fx.read_runs(runs_dir(run), stablemate_checkout(run))
    nodes = fx.hang_candidates(runs_dir(run), run.stage / "artifacts")
    detail = [
        *bullet_table(bullets),
        "  " + "   ".join(f"{LEVELS[n][0]}: {tally[n]}" for n in sorted(LEVELS, reverse=True)),
        *(["", *warnings(bullets, checks)] if warnings(bullets, checks) else []),
        *gate_lines(checks),
        *phase_lines(phases_of(run)),
        *fx.reliability_lines(runs),
        *fx.timing_lines(nodes),
    ]
    return Score(
        headline=headline(bullets, checks),
        detail=tuple(detail),
        data={
            "satisfaction_pct": round(satisfaction(bullets), 1),
            "max_level": MAX_LEVEL,
            "levels": {n: name for n, (name, _) in LEVELS.items()},
            "judged": run.param_bool("judge", True),
            "judge": {"cli": fixture.judge_cli, "model": fixture.judge_model,
                      "effort": fixture.judge_effort},
            "bullets": [{k: b[k] for k in
                         ("id", "text", "level", "reason", "evidence", "epics",
                          "capped", "unverified_citations")} for b in bullets],
            "checks": checks,
            "phases": phases_of(run),
            "runs": runs,
            "churn": fx.churn_candidates(runs_dir(run)),
            "nodes": nodes,
            "commits": git_commits(run.repo),
        },
    )
