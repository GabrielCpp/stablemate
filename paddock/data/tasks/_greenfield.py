"""The greenfield round: build a repo out of a backlog, then ask what the backlog got."""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import threading
import tomllib
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import _forensics as fx
from _stablemate import TrialError, effective, no_leaks, pin_held, stablemate_checkout, uv_run
from ostler import markdown
from paddock import Run, Score
from workhorse.cli.run import library_dirs as wh_library_dirs
from workhorse.config_run import AgentResilience
from workhorse.pyflow.driver import answered as gate_answered
from workhorse.runner import caps as wh_caps
from workhorse.runner import extract as wh_extract
from workhorse.runner import failure as wh_failure
from workhorse.runner.backends import AgentBackend
from workhorse.runner.backends.registry import get_backend
from workhorse._vendor.stablemate_core.clock import SYSTEM_CLOCK, Clock

logger = logging.getLogger(__name__)


LEVELS = {
    0: ("absent", "nothing in the repo claims this bullet"),
    1: ("planned", "a story exists that would deliver it; no implementing code"),
    2: ("built", "implementing code exists on every surface the bullet implies"),
    3: ("verified", "built, and executable evidence exercises it"),
}
MAX_LEVEL = 3


KEBAB_ID = re.compile(r"[a-z0-9][a-z0-9-]*\Z")

COVERED_HEADING = "Backlog bullets covered"

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
    markers: str = ""


@dataclass(frozen=True, slots=True)
class Check:
    """A gate the produced repo runs on itself."""

    name: str
    cmd: str
    timeout_s: float = 900.0


@dataclass(frozen=True, slots=True)
class Fixture:
    """Everything that distinguishes one greenfield task from another."""

    backlog: str
    backlog_path: str = "docs/backlog.md"
    decision_records: str = ""
    grill_capture: str = ""
    decision_records_path: str = "docs/decisions"
    surfaces: tuple[Surface, ...] = ()
    packs: str = ""
    docs_scaffold: str = ""
    checks: tuple[Check, ...] = ()
    judge_cli: str = ""
    judge_model: str = ""
    judge_effort: str = ""
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
    """Scaffold every surface, then seed the backlog into the tree genesis just made."""
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
    seed_backlog(run, fixture)
    seed_decision_records(run, fixture)
    ignore_agent_runtime(run)
    commit_baseline(run)
    seed_grill_capture(run, fixture)


def seed_backlog(run: Run, fixture: Fixture) -> None:
    """Copy the tracked backlog into the produced repo."""
    source = run.data_dir / fixture.backlog
    if not source.is_file():
        raise TrialError(f"no backlog at {source} — is --data-dir the repo's paddock/data/?")
    destination = run.repo / fixture.backlog_path
    if not destination.parent.is_dir():
        raise TrialError(f"no {destination.parent} — genesis did not scaffold the docs tree")
    destination.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")


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


AUTHOR_RUN_ID = "grill"

GRILL_GATE = "_author-context.md"


def seed_grill_capture(run: Run, fixture: Fixture) -> None:
    """Put the frozen operator turn — the answered grill gate — into the round."""
    if not fixture.grill_capture:
        return
    source = run.data_dir / fixture.grill_capture
    if not (source / "checkpoint.json").is_file():
        raise TrialError(f"no frozen grill capture at {source} — is --data-dir the repo's paddock/data/?")

    frozen = json.loads((source / "checkpoint.json").read_text(encoding="utf-8"))
    branch = str(frozen["ctx"].get("author_branch") or "")
    if branch:
        git(run.repo, "checkout", "-B", branch)

    gate = run.repo / str(frozen["waiting_on"])
    if not gate.parent.is_dir():
        raise TrialError(f"no {gate.parent} — genesis did not scaffold the docs tree")
    gate.write_text((source / GRILL_GATE).read_text(encoding="utf-8"), encoding="utf-8")

    cfg = tomllib.loads(effective(run).read_text(encoding="utf-8"))
    frozen["run_id"] = AUTHOR_RUN_ID
    frozen["waiting_on"] = str(gate)
    frozen["inputs"] = {**frozen["inputs"], "repo_dir": str(run.repo),
                        "library_dirs": wh_library_dirs(cfg)}
    frozen["ctx"] = {**frozen["ctx"], "repo_root": str(run.repo)}

    destination = runs_dir(run) / f"author-{AUTHOR_RUN_ID}"
    destination.mkdir(parents=True, exist_ok=True)
    run.write_json(destination / "checkpoint.json", frozen)


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


GATE_POLL_S = 5.0

GATE_GRACE_S = 120.0


def operator_gates_path(run: Run) -> Path:
    return build_dir(run) / "operator-gates.json"


def operator_gates_of(run: Run) -> list[dict[str, Any]]:
    path = operator_gates_path(run)
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else []


def record_gate(run: Run, entry: dict[str, Any]) -> None:
    """Append one operator-gate outcome to its own ledger."""
    entries = operator_gates_of(run)
    entries.append(entry)
    run.write_json(operator_gates_path(run), entries)


def record_hand_answer(run: Run, gate: str, note: str, commit: str = "") -> None:
    """Record that a *person* answered a gate on this round, outside the harness."""
    entry: dict[str, Any] = {"gate": gate, "action": "hand", "note": note}
    if commit:
        entry["commit"] = commit
    record_gate(run, entry)


GATE_GLOBS = ("*context*.md", "docs/**/*context*.md")


def parked_gates(repo: Path) -> list[Path]:
    """Every context file currently sitting on `STATUS: AWAITING_OPERATOR`."""
    found = {path for glob in GATE_GLOBS for path in repo.glob(glob)}
    return sorted(p for p in found if p.is_file() and not gate_answered(p))


def watch_operator_gates(run: Run, fixture: Fixture, stop: threading.Event) -> None:
    """Watch the produced repo for a stalled gate and park the round on it."""
    del fixture
    parked = {str(e["gate"]) for e in operator_gates_of(run)}
    first_seen: dict[str, float] = {}

    while not stop.wait(GATE_POLL_S):
        awaiting = set()
        for path in parked_gates(run.repo):
            gate = str(path.relative_to(run.repo))
            awaiting.add(gate)
            if gate in parked:
                continue
            since = first_seen.setdefault(gate, time.monotonic())
            if time.monotonic() - since < GATE_GRACE_S:
                continue
            parked.add(gate)
            record_gate(run, {"gate": gate, "action": "parked",
                              "reason": "still awaiting an operator "
                                        f"{GATE_GRACE_S / 60:.0f} minutes after it opened, "
                                        "and this round has no operator"})
            logger.warning("operator gate parked: %s", gate)
        for gate in set(first_seen) - awaiting:
            logger.info(
                "operator gate cleared after %.0fs of the %.0fs grace: %s",
                time.monotonic() - first_seen[gate], GATE_GRACE_S, gate,
            )
            del first_seen[gate]


def gates_watched(
    run: Run, fixture: Fixture, phase: str
) -> tuple[threading.Event, threading.Thread]:
    """Run `phase` with the gate watcher alive, and make sure it dies with the phase."""
    stop = threading.Event()
    thread = threading.Thread(
        target=watch_operator_gates, args=(run, fixture, stop),
        name=f"gate-watcher-{phase}", daemon=True,
    )
    return stop, thread


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
    """Split the backlog into epics and stories, resuming past the grill gate."""
    if not (run.repo / fixture.backlog_path).is_file():
        raise TrialError(f"no backlog at {run.repo / fixture.backlog_path} — genesis first")
    resume = ["--run-id", AUTHOR_RUN_ID] if fixture.grill_capture else []
    stop, thread = gates_watched(run, fixture, "author")
    thread.start()
    try:
        run_phase(
            run, fixture, "author",
            "workhorse-author", "run", *resume,
            "--params", json.dumps({"backlog": fixture.backlog_path}),
        )
    finally:
        stop.set()
        thread.join(timeout=GATE_POLL_S * 2)


def run_coder(run: Run, fixture: Fixture) -> None:
    """Implement the epic queue, watching for gates without answering them."""
    if not find_epics(run.repo):
        raise TrialError("no epic queue — author produced no epics to implement")
    stop, thread = gates_watched(run, fixture, "coder")
    thread.start()
    try:
        run_phase(
            run, fixture, "coder",
            "workhorse-coder", "run",
            "--params", json.dumps({"docs_path": str(run.repo)}),
        )
    finally:
        stop.set()
        thread.join(timeout=GATE_POLL_S * 2)


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
    """The whole build, as one step: genesis, backlog, author, coder, gates."""
    with no_leaks(stablemate_checkout(run), pinned=pin_held(run.pinned)):
        run_genesis(run, fixture)
        run_author(run, fixture)
        run_coder(run, fixture)
        run_gates(run, fixture)




def parse_backlog(path: Path) -> list[dict[str, Any]]:
    """The `- [kebab-id] text` bullets, in file order."""
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


def trace_bullets(run: Run, fixture: Fixture) -> list[dict[str, Any]]:
    """Trace each backlog bullet to the epic that claims it and that epic's stories."""
    bullets = parse_backlog(run.data_dir / fixture.backlog)

    claims: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for epic_md in find_epics(run.repo):
        doc = markdown.split(epic_md.read_text(encoding="utf-8"))
        stories = [
            {"slug": s.parent.name, "status": frontmatter(s).get("status", "unknown")}
            for s in sorted(epic_md.parent.glob("stories/*/story.md"))
        ]
        info = {"epic": epic_md.parent.name, "stories": stories}
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




def render(template: str, **fields: str) -> str:
    """Fill `{{name}}` placeholders in the rubric."""
    for key, value in fields.items():
        template = template.replace("{{" + key + "}}", value)
    return template


@dataclass(frozen=True, slots=True)
class Judge:
    """The agent CLI plus the two dependencies its recovery ladder needs."""

    backend: AgentBackend
    resilience: AgentResilience
    clock: Clock
    model: str = ""
    effort: str = ""


def call_agent(judge: Judge, prompt: str, *, node_id: str, repo: Path,
               attempts: int = 4) -> str:
    """One agent turn, waiting out usage caps the same way workhorse itself does."""
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
    """Score one backlog bullet by having an agent read the produced repo."""
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
    return {**bullet, "level": level, "evidence": evidence, "reason": reason,
            "unverified_citations": bad, "capped": unverified}


def judge_backlog(run: Run, fixture: Fixture, bullets: list[dict[str, Any]],
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
    logger.info("judging %d bullet(s) with %s, %d at a time", len(bullets), judge.backend.name, jobs)
    with ThreadPoolExecutor(max_workers=max(1, jobs)) as pool:
        return list(pool.map(lambda b: judge_one(judge, b, rubric, repo), bullets))


def structural_only(bullets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The levels a score with no judge is entitled to claim."""
    return [{**b, "level": 1 if b["epics"] else 0, "evidence": [], "capped": False,
             "unverified_citations": [],
             "reason": "claimed by an epic" if b["epics"] else "no epic claims it"}
            for b in bullets]




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
    lines.append("  epic ✓/n = done stories / all stories in the epic(s) claiming the bullet")
    return lines


def satisfaction(bullets: list[dict[str, Any]]) -> float:
    if not bullets:
        return 0.0
    return 100.0 * sum(int(b["level"]) for b in bullets) / (MAX_LEVEL * len(bullets))


def warnings(bullets: list[dict[str, Any]], checks: list[dict[str, Any]],
             gates: list[dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    capped = [b for b in bullets if b.get("capped")]
    if capped:
        lines.append(f"  ⚠ {len(capped)} bullet(s) capped at `planned`: the judge claimed "
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
    verified = [b for b in bullets if int(b["level"]) == MAX_LEVEL]
    if red and verified:
        lines.append(f"  ⚠ {len(verified)} bullet(s) scored `verified` while {len(red)} repo "
                     f"gate(s) are red ({', '.join(str(c['name']) for c in red)}).")
        lines.append("    Executable evidence that does not execute is not evidence.")
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


def headline(bullets: list[dict[str, Any]], checks: list[dict[str, Any]]) -> str:
    pct = satisfaction(bullets)
    total = sum(int(b["level"]) for b in bullets)
    green = sum(1 for c in checks if c["exit"] == 0)
    gates = f"{green}/{len(checks)} gates green" if checks else "no gates declared"
    return (f"backlog satisfaction {pct:.0f}% ({total}/{MAX_LEVEL * max(1, len(bullets))} "
            f"across {len(bullets)} bullets) — {gates}")


def score_round(run: Run, fixture: Fixture) -> Score:
    """The rating beside what it cost and beside whether the machinery got there alone."""
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
    operator_gates = operator_gates_of(run)
    flags = warnings(bullets, checks, operator_gates)
    runs = fx.read_runs(runs_dir(run), stablemate_checkout(run))
    nodes = fx.hang_candidates(runs_dir(run), run.stage / "artifacts")
    detail = [
        *bullet_table(bullets),
        "  " + "   ".join(f"{LEVELS[n][0]}: {tally[n]}" for n in sorted(LEVELS, reverse=True)),
        *(["", *flags] if flags else []),
        *operator_gate_lines(operator_gates),
        *gate_lines(checks),
        *phase_lines(phases_of(run)),
        *fx.reliability_lines(runs),
        *fx.timing_lines(nodes),
    ]
    return Score(
        headline=headline(bullets, checks),
        detail=tuple(detail),
        caveats=tuple(
            f"operator gate {g['action']}: {g['gate']}" for g in operator_gates
        ),
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
            "operator_gates": operator_gates,
            "phases": phases_of(run),
            "runs": runs,
            "churn": fx.churn_candidates(runs_dir(run)),
            "nodes": nodes,
            "commits": git_commits(run.repo),
        },
    )
