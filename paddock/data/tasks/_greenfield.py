"""The greenfield round: build a repo out of an approved milestone, then ask what the milestone got."""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import _forensics as fx
import _operator_gates as og
from _judge import Judge, call_agent, render
from _stablemate import TrialError, effective, no_leaks, pin_held, stablemate_checkout, uv_run
from ostler import markdown, registry
from ostler.milestones import JOURNEY_LEVEL, SERVICES_LABEL, journey_slug
from paddock import Run, Score
from workhorse.config_run import AgentResilience
from workhorse.runner import extract as wh_extract
from workhorse.runner.backends.registry import get_backend
from workhorse._vendor.stablemate_core.clock import SYSTEM_CLOCK

logger = logging.getLogger(__name__)


LEVELS = {
    0: ("absent", "nothing in the repo claims this journey"),
    1: ("planned", "a story exists that would deliver it; no implementing code"),
    2: ("built", "implementing code exists on every surface the journey implies"),
    3: ("verified", "built, and executable evidence exercises it"),
}
MAX_LEVEL = 3


MILESTONES_DIR = "docs/milestones"

SERVICES_DIR = "docs/services"

MILESTONE_FILE = "milestone.md"

BUILD = ("artifacts", "build")




@dataclass(frozen=True, slots=True)
class Surface:
    """One service genesis scaffolds: a stack, a root inside the repo, an init command."""

    service: str
    service_root: str
    packs: str = ""
    scaffolds: str = ""
    init_cmd: str = ""
    marker: str = ""


@dataclass(frozen=True, slots=True)
class Check:
    """A gate the produced repo runs on itself."""

    name: str
    cmd: str
    timeout_s: float = 900.0


@dataclass(frozen=True, slots=True)
class Fixture:
    """Everything that distinguishes one greenfield task from another."""

    milestone: str
    decision_records: str = ""
    decision_records_path: str = "docs/decisions"
    surfaces: tuple[Surface, ...] = ()
    packs: str = ""
    docs_scaffold: str = ""
    checks: tuple[Check, ...] = ()
    judge_cli: str = ""
    judge_model: str = ""
    judge_effort: str = ""
    budget_s: dict[str, float] = field(default_factory=dict)

    @property
    def slug(self) -> str:
        return Path(self.milestone).name

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
            "workflows": "coder,author",
        })




def build_dir(run: Run) -> Path:
    directory = run.stage.joinpath(*BUILD)
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def runs_dir(run: Run) -> Path:
    """Where every phase's run dir goes."""
    directory = build_dir(run) / "runs"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def budget_of(run: Run, fixture: Fixture, phase: str) -> float:
    return run.param_float(f"budget_{phase}", float(fixture.budget_s.get(phase) or 0.0))


def phase_env(run: Run, fixture: Fixture, phase: str) -> dict[str, str]:
    """The environment one phase is launched with: which repo, and how long it may take."""
    env = {**os.environ, "AGENT_REPO_DIR": str(run.repo)}
    budget = budget_of(run, fixture, phase)
    if budget > 0:
        env["WORKHORSE_MAX_RUNTIME_S"] = str(budget)
    return env


def ledger_path(run: Run) -> Path:
    return build_dir(run) / "build.json"


def record(run: Run, phase: str, *, rc: int, wall_s: float) -> None:
    """Append one phase's outcome to the round's ledger, rewritten after each phase."""
    path = ledger_path(run)
    phases = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else []
    phases.append({"phase": phase, "rc": rc, "wall_s": round(wall_s, 1)})
    run.write_json(path, phases)


def phases_of(run: Run) -> list[dict[str, Any]]:
    path = ledger_path(run)
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else []


def run_genesis(run: Run, fixture: Fixture) -> None:
    """Scaffold every surface, then seed the milestone into the tree genesis just made."""
    checkout = stablemate_checkout(run)
    for surface in fixture.surfaces:
        started = time.monotonic()
        result = run.cli(
            *uv_run(checkout, "workhorse-workflows"),
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
    seed_milestone(run, fixture)
    seed_decision_records(run, fixture)
    ignore_agent_runtime(run)
    commit_baseline(run)


def seed_milestone(run: Run, fixture: Fixture) -> None:
    """Copy the approved milestone into the produced repo, and open an empty book per surface.

    The milestone's journeys name the books under `docs/services/`, the author's ready gate
    requires each named book to exist, and genesis makes none, so the round opens an empty
    book per surface for the author to fill.
    """
    source = run.data_dir / fixture.milestone
    if not (source / MILESTONE_FILE).is_file():
        raise TrialError(f"no milestone at {source} — is --data-dir the repo's paddock/data/?")
    if not (run.repo / "docs").is_dir():
        raise TrialError(f"no {run.repo / 'docs'} — genesis did not scaffold the docs tree")
    shutil.copytree(source, run.repo / MILESTONES_DIR / fixture.slug, dirs_exist_ok=True)
    for surface in fixture.surfaces:
        (run.repo / SERVICES_DIR / surface.service).mkdir(parents=True, exist_ok=True)


def seed_decision_records(run: Run, fixture: Fixture) -> None:
    """Copy the fixture's standing decision records into the produced repo."""
    if not fixture.decision_records:
        return
    source = run.data_dir / fixture.decision_records
    if not source.is_dir():
        raise TrialError(f"no decision records at {source} — is --data-dir the repo's paddock/data/?")
    destination = run.repo / fixture.decision_records_path
    destination.mkdir(parents=True, exist_ok=True)
    for record in sorted(source.glob("*.md")):
        (destination / record.name).write_text(record.read_text(encoding="utf-8"), encoding="utf-8")


def git(repo: Path, *argv: str) -> None:
    result = subprocess.run(["git", "-C", str(repo), *argv],
                            capture_output=True, text=True, timeout=120, check=False)
    if result.returncode != 0:
        raise TrialError(f"`git {argv[0]}` failed in {repo}: "
                         f"{result.stderr.strip() or result.stdout.strip()}")


def commit_baseline(run: Run) -> None:
    """Commit everything genesis scaffolded, before the first story runs."""
    for argv in (["add", "-A"],
                 ["commit", "-m", "chore: scaffold the project", "--no-verify"]):
        result = subprocess.run(["git", "-C", str(run.repo), *argv],
                                capture_output=True, text=True, timeout=120, check=False)
        if result.returncode != 0 and "nothing to commit" not in result.stdout:
            raise TrialError(f"baseline `git {argv[0]}` failed in {run.repo}: "
                             f"{result.stderr.strip() or result.stdout.strip()}")


RUNTIME_IGNORES = (".opencode/", "**/qa/**/*.log")

IGNORE_HEADER = "# benchmark harness: agent runtime state, not deliverables"


def ignore_agent_runtime(run: Run) -> None:
    """Teach the produced repo to ignore the runtime of the agent building it."""
    path = run.repo / ".gitignore"
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    if IGNORE_HEADER in text:
        return
    prefix = text if text.endswith("\n") or not text else text + "\n"
    path.write_text(
        prefix + f"\n{IGNORE_HEADER}\n" + "".join(f"{line}\n" for line in RUNTIME_IGNORES),
        encoding="utf-8",
    )


def run_phase(run: Run, fixture: Fixture, phase: str, *argv: str) -> None:
    """Drive one workflow phase and record what it cost."""
    checkout = stablemate_checkout(run)
    started = time.monotonic()
    result = run.cli(
        *uv_run(checkout, "workhorse-workflows"),
        *argv,
        "--runs-dir", str(runs_dir(run)),
        "--config", str(effective(run)),
        cwd=run.repo,
        env=phase_env(run, fixture, phase),
        log_name=phase,
    )
    record(run, phase, rc=result.returncode, wall_s=time.monotonic() - started)


def run_author(run: Run, fixture: Fixture) -> None:
    """Split the approved milestone into epics and stories."""
    milestone = run.repo / MILESTONES_DIR / fixture.slug / MILESTONE_FILE
    if not milestone.is_file():
        raise TrialError(f"no milestone at {milestone} — genesis first")
    stop, thread = og.gates_watched(run, "author")
    thread.start()
    try:
        run_phase(run, fixture, "author", "workhorse-author", "run")
    finally:
        stop.set()
        thread.join(timeout=og.GATE_POLL_S * 2)


def run_coder(run: Run, fixture: Fixture) -> None:
    """Implement the epic queue, watching for gates without answering them."""
    if not find_epics(run.repo):
        raise TrialError("no epic queue — author produced no epics to implement")
    stop, thread = og.gates_watched(run, "coder")
    thread.start()
    try:
        run_phase(
            run, fixture, "coder",
            "workhorse-coder", "run",
            "--params", json.dumps({"repo_dir": str(run.repo)}),
        )
    finally:
        stop.set()
        thread.join(timeout=og.GATE_POLL_S * 2)


def run_gates(run: Run, fixture: Fixture) -> None:
    """Run the produced repo's own gates once, and stage the result."""
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
    """The whole build, as one step: genesis, milestone, author, coder, gates."""
    with no_leaks(stablemate_checkout(run), pinned=pin_held(run.pinned)):
        run_genesis(run, fixture)
        run_author(run, fixture)
        run_coder(run, fixture)
        run_gates(run, fixture)




def books_of(value: str) -> list[str]:
    return [b for b in (part.strip().strip("`").strip() for part in value.split(",")) if b]


def milestone_journeys(path: Path) -> list[dict[str, Any]]:
    """The `###` journeys under a milestone's `## User Journeys`, in file order."""
    if not path.is_file():
        return []
    section = markdown.split(path.read_text(encoding="utf-8")).find_section(
        registry.MILESTONE_JOURNEYS_HEADING)
    if section is None:
        return []
    out: list[dict[str, Any]] = []
    for child in section.children:
        if child.level != JOURNEY_LEVEL:
            continue
        title = child.title.strip()
        ident = journey_slug(title)
        if not ident:
            continue
        bullet = child.labelled(SERVICES_LABEL)
        prose = [line for line in child.body.splitlines()
                 if not line.strip().lower().lstrip("-*").strip().startswith(f"{SERVICES_LABEL}:")]
        out.append({
            "id": ident,
            "title": title,
            "text": " ".join(" ".join(prose).split()),
            "services": books_of(bullet.value) if bullet is not None else [],
        })
    return out


def milestone_epics(path: Path) -> list[str]:
    """The `epics` frontmatter of a milestone, as stripped names."""
    if not path.is_file():
        return []
    data = markdown.split(path.read_text(encoding="utf-8")).frontmatter
    value = data.get("epics") if isinstance(data, dict) else None
    items = [value] if isinstance(value, str) else value if isinstance(value, list) else []
    return [str(i).strip() for i in items if str(i).strip()]


def find_epics(repo: Path) -> list[Path]:
    return sorted(repo.glob("docs/epics/*/epic.md"))


def frontmatter(md: Path) -> dict[str, str]:
    """The `---`-delimited YAML header, as flat strings."""
    try:
        text = md.read_text(encoding="utf-8")
    except OSError:
        return {}
    data = markdown.split(text).frontmatter
    return {str(k): str(v) for k, v in data.items()} if isinstance(data, dict) else {}


def is_done(status: str) -> bool:
    """Story frontmatter uses prose statuses ('Not started', 'QA passed', 'Done')."""
    return status.strip().lower() in {"done", "qa passed", "complete", "completed", "merged"}


def produced_milestone(run: Run, fixture: Fixture) -> Path:
    return run.repo / MILESTONES_DIR / fixture.slug / MILESTONE_FILE


def listed_epics(run: Run, fixture: Fixture) -> set[str]:
    return {registry.epic_slug(e) for e in milestone_epics(produced_milestone(run, fixture))}


def unlisted_epics(run: Run, fixture: Fixture) -> list[str]:
    """The epic directories the milestone's `epics` list does not name."""
    listed = listed_epics(run, fixture)
    return [e.parent.name for e in find_epics(run.repo)
            if registry.epic_slug(e.parent.name) not in listed]


def trace_journeys(run: Run, fixture: Fixture) -> list[dict[str, Any]]:
    """Trace each milestone journey to the listed epic that claims it and that epic's stories."""
    journeys = milestone_journeys(run.data_dir / fixture.milestone / MILESTONE_FILE)
    listed = listed_epics(run, fixture)

    owned: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for epic_md in find_epics(run.repo):
        if registry.epic_slug(epic_md.parent.name) not in listed:
            continue
        doc = markdown.split(epic_md.read_text(encoding="utf-8"))
        section = doc.find_section(registry.MILESTONE_JOURNEYS_HEADING)
        if section is None:
            continue
        stories = [
            {"slug": s.parent.name, "status": frontmatter(s).get("status", "unknown")}
            for s in sorted(epic_md.parent.glob("stories/*/story.md"))
        ]
        info = {"epic": epic_md.parent.name, "stories": stories}
        named = {journey_slug(s.title) for s in section.walk() if s.level > section.level}
        haystack = " ".join(section.text.split()).lower()
        for journey in journeys:
            title = " ".join(str(journey["title"]).split()).lower()
            if journey["id"] in named or title in haystack:
                owned[str(journey["id"])].append(info)

    for journey in journeys:
        owners = owned.get(str(journey["id"]), [])
        journey["epics"] = [o["epic"] for o in owners]
        journey["stories"] = [s for o in owners for s in o["stories"]]
        journey["stories_done"] = [s for s in journey["stories"] if is_done(s["status"])]
    return journeys


def git_commits(repo: Path) -> int:
    try:
        out = subprocess.run(["git", "-C", str(repo), "log", "--oneline"],
                             capture_output=True, text=True, timeout=30, check=False)
        return len(out.stdout.splitlines()) if out.returncode == 0 else 0
    except (OSError, subprocess.SubprocessError):
        return 0




def judge_one(judge: Judge, journey: dict[str, Any], rubric: str, repo: Path) -> dict[str, Any]:
    """Score one milestone journey by having an agent read the produced repo."""
    prompt = render(
        rubric,
        journey_id=str(journey["id"]),
        journey_title=str(journey["title"]),
        journey_text=str(journey["text"]),
        target=str(repo),
        epics=", ".join(journey["epics"]) or "(none — no epic claims this journey)",
        stories="\n".join(f"  - {s['slug']} — {s['status']}" for s in journey["stories"])
                or "  (none)",
        levels="\n".join(f"  {n} {name} — {desc}" for n, (name, desc) in LEVELS.items()),
    )
    text = call_agent(judge, prompt, node_id=f"judge_{journey['id']}", repo=repo)
    parsed = wh_extract.parse_json_from_text(text, ["level", "evidence", "reason"]) or {}

    try:
        level = max(0, min(MAX_LEVEL, int(parsed.get("level", 0))))
    except (TypeError, ValueError):
        level = 0
    evidence = [str(e) for e in (parsed.get("evidence") or []) if str(e).strip()]
    reason = str(parsed.get("reason") or "").strip() or "(judge returned no reason)"

    bad = [e for e in evidence if not (repo / e.split(":", 1)[0].strip()).exists()]
    unverified = bool(bad) or (level >= 2 and not evidence)
    if unverified and level >= 2:
        level = 1
    return {**journey, "level": level, "evidence": evidence, "reason": reason,
            "unverified_citations": bad, "capped": unverified}


def judge_journeys(run: Run, fixture: Fixture, journeys: list[dict[str, Any]],
                   jobs: int) -> list[dict[str, Any]]:
    rubric_path = run.data_dir / "rubric.md"
    if not rubric_path.is_file():
        raise TrialError(f"no rubric at {rubric_path}")
    judge = Judge(
        get_backend(fixture.judge_cli or None), AgentResilience.from_env(), SYSTEM_CLOCK,
        model=fixture.judge_model, effort=fixture.judge_effort,
    )
    rubric = rubric_path.read_text(encoding="utf-8")
    arena = run.workdir("judge")
    repo = arena / run.repo.name
    shutil.copytree(run.repo, repo, symlinks=True)
    logger.info("judging %d journey(s) with %s, %d at a time", len(journeys), judge.backend.name, jobs)
    with ThreadPoolExecutor(max_workers=max(1, jobs)) as pool:
        return list(pool.map(lambda j: judge_one(judge, j, rubric, repo), journeys))


def structural_only(journeys: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The levels a score with no judge is entitled to claim."""
    return [{**b, "level": 1 if b["epics"] else 0, "evidence": [], "capped": False,
             "unverified_citations": [],
             "reason": "claimed by an epic" if b["epics"] else "no epic claims it"}
            for b in journeys]




def journey_table(journeys: list[dict[str, Any]]) -> list[str]:
    lines = [
        f"  {'journey':<28}{'level':<12}{'epic ✓/n':>9}  why",
        f"  {'-' * 86}",
    ]
    for b in sorted(journeys, key=lambda x: -int(x["level"])):
        name = LEVELS[int(b["level"])][0]
        flag = " ⚠" if b.get("capped") else ""
        done = f"{len(b['stories_done'])}/{len(b['stories'])}"
        lines.append(f"  {b['id']:<28}{b['level']} {name:<10}{done:>9}  {str(b['reason'])[:44]}{flag}")
    lines.append(f"  {'-' * 86}")
    lines.append("  epic ✓/n = done stories / all stories in the epic(s) claiming the journey")
    return lines


def satisfaction(journeys: list[dict[str, Any]]) -> float:
    if not journeys:
        return 0.0
    return 100.0 * sum(int(b["level"]) for b in journeys) / (MAX_LEVEL * len(journeys))


def warnings(journeys: list[dict[str, Any]], checks: list[dict[str, Any]],
             gates: list[dict[str, Any]], unlisted: list[str] | None = None) -> list[str]:
    lines: list[str] = []
    capped = [b for b in journeys if b.get("capped")]
    if capped:
        lines.append(f"  ⚠ {len(capped)} journey(s) capped at `planned`: the judge claimed "
                     "built/verified but cited repo paths that do not exist. Treat these as")
        lines.append("    unproven, not as near-misses:")
        for b in capped:
            missing = ", ".join(b["unverified_citations"]) or "(no citation at all)"
            lines.append(f"      - {b['id']}: {missing}")

    hand = [g for g in gates if g["action"] == "hand"]
    if hand:
        lines.append(f"  ⚠ {len(hand)} operator gate(s) were answered BY HAND. This round is not "
                     "an unattended capture, and")
        lines.append("    it is not repeatable as it stands — a person is part of its result. "
                     "Fix the harness or the")
        lines.append("    standing decision records so the next round reaches the same "
                     "place alone:")
        for g in hand:
            lines.append(f"      - {g['gate']}: {g['note']}")

    parked = [g for g in gates if g["action"] == "parked"]
    if parked:
        lines.append(f"  ⚠ {len(parked)} operator gate(s) stayed parked — the round stopped on a "
                     "question nothing answered,")
        lines.append("    so this score covers a partial round and is a diagnostic, not a "
                     "baseline. Read the gate file:")
        lines.append("    a question a standing decision record should have settled is fixture "
                     "debt; anything else is a")
        lines.append("    finding about the loop. Answering it by hand makes the round "
                     "unrepeatable — record it as `hand` if you do.")

    red = [c for c in checks if c["exit"] != 0]
    verified = [b for b in journeys if int(b["level"]) == MAX_LEVEL]
    if red and verified:
        lines.append(f"  ⚠ {len(verified)} journey(s) scored `verified` while {len(red)} repo "
                     f"gate(s) are red ({', '.join(str(c['name']) for c in red)}).")
        lines.append("    Executable evidence that does not execute is not evidence.")

    if unlisted:
        lines.append(f"  ⚠ {len(unlisted)} epic(s) the milestone does not list: "
                     f"{', '.join(unlisted)}")
    return lines


def operator_gate_lines(gates: list[dict[str, Any]]) -> list[str]:
    """Every operator gate this round stalled on, and every one a person reached into."""
    if not gates:
        return []
    lines = ["", "  operator gates"]
    for g in gates:
        if g["action"] == "hand":
            lines.append(f"  ✋ {g['gate']}")
            where = f" (commit {g['commit']})" if g.get("commit") else ""
            lines.append(f"      ANSWERED BY HAND — {g['note']}{where}")
        else:
            lines.append(f"  ⚠ {g['gate']}")
            lines.append(f"      PARKED — {g['reason']}")
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


def headline(journeys: list[dict[str, Any]], checks: list[dict[str, Any]]) -> str:
    pct = satisfaction(journeys)
    total = sum(int(b["level"]) for b in journeys)
    green = sum(1 for c in checks if c["exit"] == 0)
    gates = f"{green}/{len(checks)} gates green" if checks else "no gates declared"
    return (f"milestone satisfaction {pct:.0f}% ({total}/{MAX_LEVEL * max(1, len(journeys))} "
            f"across {len(journeys)} journeys) — {gates}")


def score_round(run: Run, fixture: Fixture) -> Score:
    """The rating beside what it cost and beside whether the machinery got there alone."""
    journeys = trace_journeys(run, fixture)
    only = set(run.param_list("only"))
    if only:
        journeys = [j for j in journeys if j["id"] in only]
    if not journeys:
        return Score(headline=f"no journeys found in {fixture.milestone}")

    gates = build_dir(run) / "gates.json"
    checks: list[dict[str, Any]] = (
        json.loads(gates.read_text(encoding="utf-8")) if gates.is_file() else []
    )

    journeys = (
        judge_journeys(run, fixture, journeys, int(run.param_float("jobs", 4.0)))
        if run.param_bool("judge", True)
        else structural_only(journeys)
    )

    tally: dict[int, int] = defaultdict(int)
    for b in journeys:
        tally[int(b["level"])] += 1
    operator_gates = og.operator_gates_of(run)
    flags = warnings(journeys, checks, operator_gates, unlisted_epics(run, fixture))
    runs = fx.read_runs(runs_dir(run), stablemate_checkout(run))
    nodes = fx.hang_candidates(runs_dir(run), run.stage / "artifacts")
    detail = [
        *journey_table(journeys),
        "  " + "   ".join(f"{LEVELS[n][0]}: {tally[n]}" for n in sorted(LEVELS, reverse=True)),
        *(["", *flags] if flags else []),
        *operator_gate_lines(operator_gates),
        *gate_lines(checks),
        *phase_lines(phases_of(run)),
        *fx.reliability_lines(runs),
        *fx.timing_lines(nodes),
    ]
    return Score(
        headline=headline(journeys, checks),
        detail=tuple(detail),
        caveats=tuple(
            f"operator gate {g['action']}: {g['gate']}" for g in operator_gates
        ),
        data={
            "satisfaction_pct": round(satisfaction(journeys), 1),
            "max_level": MAX_LEVEL,
            "levels": {n: name for n, (name, _) in LEVELS.items()},
            "judged": run.param_bool("judge", True),
            "judge": {"cli": fixture.judge_cli, "model": fixture.judge_model,
                      "effort": fixture.judge_effort},
            "journeys": [{k: j[k] for k in
                          ("id", "title", "text", "level", "reason", "evidence", "epics",
                           "capped", "unverified_citations")} for j in journeys],
            "checks": checks,
            "operator_gates": operator_gates,
            "phases": phases_of(run),
            "runs": runs,
            "churn": fx.churn_candidates(runs_dir(run)),
            "nodes": nodes,
            "commits": git_commits(run.repo),
        },
    )
