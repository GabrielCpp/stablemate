"""Run a benchmark's task: copy its data, execute the steps, score the result."""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
import threading
import time
from collections.abc import Iterator, Mapping, Sequence
from types import MappingProxyType
from contextlib import AbstractContextManager, contextmanager, nullcontext
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from paddock import homeconfig, manifest, names, paths, project as project_mod, reap
from paddock.loader import Benchmark
from paddock.names import RunName
from paddock._vendor.stablemate_core.config import ARTIFACTS_DIR_ENV, CONFIG_PATH_ENV, WORKSPACE_ENV
from paddock.registry import Input, Score, Step, Task

logger = logging.getLogger(__name__)


class RunError(RuntimeError):
    """A task that could not be run, or a result that must not be recorded."""


class RoundInterrupted(RunError):
    """A round that stopped before it finished and left its workspace to be resumed."""


ROUND_FILE = "round.json"

STEPS_FILE = "steps.json"


@dataclass(frozen=True, slots=True)
class CommandResult:
    argv: tuple[str, ...]
    returncode: int
    log: Path

    @property
    def ok(self) -> bool:
        return self.returncode == 0

    def check(self) -> CommandResult:
        if not self.ok:
            raise RunError(f"{self.argv[0]} exited {self.returncode}; log: {self.log}")
        return self


@dataclass(frozen=True, slots=True)
class StepOutcome:
    name: str
    status: str
    seconds: float
    error: str = ""
    commands: tuple[tuple[str, ...], ...] = ()
    exit_codes: tuple[int, ...] = ()


class _Echo:
    """Follow a command's log file while it is being written, echoing it to stderr."""

    def __init__(self, path: Path, prefix: str, interval: float = 0.25) -> None:
        self._path = path
        self._prefix = prefix
        self._interval = interval
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._follow, daemon=True)

    def __enter__(self) -> _Echo:
        self._thread.start()
        return self

    def __exit__(self, *_exc: object) -> None:
        self._stop.set()
        self._thread.join(timeout=self._interval * 8)

    def _follow(self) -> None:
        offset = 0
        while True:
            done = self._stop.wait(self._interval)
            offset = self._drain(offset)
            if done:
                return

    def _drain(self, offset: int) -> int:
        """Echo whole lines written since *offset*, and return the new offset."""
        try:
            with self._path.open("rb") as handle:
                handle.seek(offset)
                chunk = handle.read()
        except OSError:
            return offset
        end = chunk.rfind(b"\n")
        if end < 0:
            return offset
        block = chunk[: end + 1]
        for line in block.decode("utf-8", "replace").splitlines():
            print(f"{self._prefix}| {line}", file=sys.stderr, flush=True)
        return offset + len(block)


@dataclass
class Run:
    """The handle a step and a score function are given."""

    task: Task
    name: RunName
    stage: Path
    scratch: Path
    workspace: Path
    config: Path
    data: Path
    benchmark: Benchmark
    project: Path | None = None
    pinned: project_mod.Project | None = None
    echo: bool = True
    step_name: str = ""
    commands: list[tuple[str, ...]] = field(default_factory=list)
    exit_codes: list[int] = field(default_factory=list)
    outcomes: list[StepOutcome] = field(default_factory=list)

    @property
    def inputs(self) -> Mapping[str, Input]:
        """What the task declared for its steps to read."""
        return MappingProxyType(dict(self.task.inputs))

    @property
    def repos(self) -> Mapping[str, Path]:
        """Each staged repository by name: the benchmark's own name for a single repo, else one per child of `data/`."""
        if (self.data / ".git").exists():
            return MappingProxyType({self.benchmark.name: self.stage})
        return MappingProxyType(
            {child.name: self.stage / child.name for child in names.repo_children(self.data)}
        )

    @property
    def repo(self) -> Path:
        """The copy of a single-repo benchmark's data the steps mutate."""
        if (self.data / ".git").exists():
            return self.stage
        listed = ", ".join(self.repos)
        raise RunError(
            f"benchmark {self.benchmark.name!r} stages several repos ({listed}); "
            'reach one as run.repos["<name>"] and pass cwd= to run.cli'
        )

    @property
    def artifacts(self) -> Path:
        """This step's artifact directory, created on first use."""
        directory = self.workspace / "artifacts" / (self.step_name or "run")
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    def workdir(self, name: str) -> Path:
        """A fresh empty directory under `scratch/` — a per-trial tree, a temp checkout."""
        directory = self.scratch / name
        if directory.exists():
            shutil.rmtree(directory)
        directory.mkdir(parents=True)
        return directory

    def cli(
        self,
        *argv: str,
        cwd: Path | None = None,
        env: Mapping[str, str] | None = None,
        timeout: float | None = None,
        log_name: str = "",
        check: bool = False,
    ) -> CommandResult:
        """Run a command, tee its output to a log under `artifacts/` and to stderr."""
        target = cwd or self.repo
        merged = dict(os.environ if env is None else env)
        merged[CONFIG_PATH_ENV] = str(self.config)
        merged["PWD"] = str(target)
        merged.pop("OLDPWD", None)
        name = log_name or f"{len(self.commands):02d}-{Path(argv[0]).name}"
        log = self.artifacts / f"{name}.log"
        self.commands.append(tuple(argv))
        logger.info("$ %s", " ".join(argv))
        with log.open("w", encoding="utf-8") as handle, self._echo(log, name):
            handle.write(f"$ {' '.join(argv)}\n(cwd {target})\n\n")
            handle.flush()
            try:
                completed = subprocess.run(
                    list(argv),
                    cwd=str(target),
                    env=merged,
                    stdout=handle,
                    stderr=subprocess.STDOUT,
                    text=True,
                    check=False,
                    timeout=timeout,
                )
            except subprocess.TimeoutExpired:
                handle.write(f"\n[paddock] timed out after {timeout}s\n")
                raise RunError(f"{argv[0]} timed out after {timeout}s; log: {log}") from None
            except FileNotFoundError as exc:
                raise RunError(f"{argv[0]}: not on PATH") from exc
        self.exit_codes.append(completed.returncode)
        result = CommandResult(tuple(argv), completed.returncode, log)
        return result.check() if check else result

    def _echo(self, log: Path, name: str) -> AbstractContextManager[object]:
        """The live tee for one command, or a no-op when the run asked for quiet."""
        return _Echo(log, name) if self.echo else nullcontext()

    def read_json(self, path: Path) -> dict:
        return json.loads(path.read_text(encoding="utf-8"))

    def write_json(self, path: Path, data: object) -> Path:
        """Write *data* to *path* as JSON, atomically."""
        path.parent.mkdir(parents=True, exist_ok=True)
        staged = path.with_name(f"{path.name}.{os.getpid()}.writing")
        staged.write_text(json.dumps(data, indent=2), encoding="utf-8")
        os.replace(staged, path)
        return path


@dataclass(frozen=True, slots=True)
class RunResult:
    name: RunName
    workspace: Path
    stage: Path
    result: Path
    outcomes: tuple[StepOutcome, ...]
    score: Score | None
    caveats: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return all(outcome.status == "ok" for outcome in self.outcomes)


def _git(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True, check=False)


def _clone_repo(data: Path, stage: Path) -> None:
    """Clone the repository *data* into *stage* at its HEAD, with no remote to push the round's work to."""
    if _git("status", "--porcelain", cwd=data).stdout.strip():
        logger.warning("%s has uncommitted changes; the run copies its HEAD and will not see them", data)
    cloned = _git("clone", "--quiet", "--no-hardlinks", str(data), str(stage), cwd=data.parent)
    if cloned.returncode != 0:
        raise RunError(f"could not copy {data} to {stage}: {cloned.stderr.strip()}")
    for remote in _git("remote", cwd=stage).stdout.split():
        if _git("remote", "remove", remote, cwd=stage).returncode != 0:
            raise RunError(f"could not strip remote {remote!r} from the copy of {data}")


def _copy_data(data: Path, stage: Path) -> None:
    """Clone *data* into *stage*: one repository as is, a folder of repositories one per name."""
    if (data / ".git").exists():
        _clone_repo(data, stage)
        return
    children = names.repo_children(data)
    stage.mkdir(parents=True)
    for child in children:
        _clone_repo(child, stage / child.name)


def _check_data(benchmark: Benchmark) -> None:
    """Refuse a `data/` that is neither a repository nor a folder of them."""
    data = benchmark.data
    if (data / ".git").exists():
        return
    for child in names.repo_children(data):
        if not (child / ".git").exists():
            raise RunError(f"benchmark {benchmark.name!r}: {child} is not a git repository")


@contextmanager
def _without_operator_env() -> Iterator[None]:
    """Drop the operator's workspace and artifacts dir from the environment for the run, then restore them."""
    saved = {name: os.environ.pop(name) for name in (WORKSPACE_ENV, ARTIFACTS_DIR_ENV) if name in os.environ}
    try:
        yield
    finally:
        os.environ.update(saved)


def execute(
    benchmark: Benchmark,
    task: Task,
    *,
    root: Path,
    checkout: Path | None = None,
    pin_project: bool = True,
    echo: bool = True,
) -> RunResult:
    source = checkout or paths.checkout_root()
    _check_data(benchmark)
    data_commit = names.data_commit(benchmark.data)
    if not data_commit:
        raise RunError(f"benchmark {benchmark.name!r}: {benchmark.data} is not a git repository with a commit")
    stablemate = names.git_head(source)
    if not stablemate:
        raise RunError(f"{source} is not a git checkout, so the run cannot name the stablemate commit it measures")

    name = names.reserve(root, RunName(benchmark.name, task.name, data_commit, stablemate, 0))
    workspace = names.workspace_dir(root, name)
    stage = workspace / "stage"
    scratch = workspace / "scratch"
    scratch.mkdir(parents=True, exist_ok=True)
    logger.info("run %s", name)

    config = homeconfig.materialize(benchmark.home_config, task.config, workspace / "config.toml", stage=stage)
    _copy_data(benchmark.data, stage)

    pinned = project_mod.pin(source, work=workspace, enabled=pin_project)
    run = _new_run(benchmark, task, name, config, pinned, source, echo)
    state: dict[str, Any] = {
        "benchmark": name.benchmark,
        "task": name.task,
        "data_commit": name.data_commit,
        "stablemate": name.stablemate,
        "n": name.n,
        "pin_requested": pin_project,
        "project": pinned.as_json() if pinned else None,
        "repos": {repo: names.git_head(path) for repo, path in run.repos.items()},
        "caveats": [],
        "segments": [_open_segment()],
    }
    return _drive(run, state, root=root, pin_requested=pin_project, done=())


def resume(
    benchmark: Benchmark,
    task: Task,
    *,
    root: Path,
    n: int | None = None,
    checkout: Path | None = None,
    echo: bool = True,
) -> RunResult:
    """Continue an interrupted round on the stablemate sha it started on."""
    workspace = _unfinished_workspace(root, benchmark.name, task.name, n)
    state: dict[str, Any] = json.loads((workspace / ROUND_FILE).read_text(encoding="utf-8"))
    name = RunName(state["benchmark"], state["task"], state["data_commit"], state["stablemate"], int(state["n"]))
    pin_requested = bool(state["pin_requested"])
    source = (checkout or paths.checkout_root()).resolve()
    if pin_requested:
        if _git("cat-file", "-e", f"{name.stablemate}^{{commit}}", cwd=source).returncode != 0:
            raise RunError(
                f"{source} does not have commit {name.stablemate}, so round {name} cannot resume on the code it started on"
            )
    elif names.git_head(source) != name.stablemate:
        raise RunError(
            f"round {name} was not pinned and drove {source} at {name.stablemate[:12]}; "
            f"it is at {names.git_head(source)[:12]} now, so the round cannot resume on the same code"
        )
    logger.info("resume %s", name)

    pinned = project_mod.pin(
        source, work=workspace, enabled=pin_requested, at=name.stablemate if pin_requested else None
    )
    if pin_requested and (pinned is None or not pinned.pinned):
        raise RunError(f"could not pin {source} at {name.stablemate}, so round {name} cannot resume")
    run = _new_run(benchmark, task, name, workspace / "config.toml", pinned, source, echo)
    steps_path = workspace / STEPS_FILE
    done = (
        tuple(_outcome_of(item) for item in json.loads(steps_path.read_text(encoding="utf-8")))
        if steps_path.is_file()
        else ()
    )
    state["segments"] = [*state["segments"], _open_segment()]
    return _drive(run, state, root=root, pin_requested=pin_requested, done=done)


def _unfinished_workspace(root: Path, benchmark: str, task: str, n: int | None) -> Path:
    """The workspace of the round `resume` continues: the given number, else the highest one without a result."""
    base = root / paths.WORKSPACE / benchmark / task
    found = sorted(
        (int(path.name), path)
        for path in base.glob("*/*")
        if path.name.isdigit() and (path / ROUND_FILE).is_file()
    )
    if n is not None:
        found = [(number, path) for number, path in found if number == n]
    if not found:
        which = f"round {n} of " if n is not None else "an interrupted round of "
        raise RunError(f"no workspace holds {which}{benchmark}/{task} to resume")
    open_ones = [(number, path) for number, path in found if not (root / paths.RESULTS / path.relative_to(root / paths.WORKSPACE)).exists()]
    if not open_ones:
        raise RunError(f"round {found[-1][0]} of {benchmark}/{task} already finished: its result exists")
    highest = max(number for number, _ in open_ones)
    tied = [path for number, path in open_ones if number == highest]
    if len(tied) > 1:
        listed = ", ".join(path.parent.name for path in tied)
        raise RunError(f"round {highest} of {benchmark}/{task} is open under several names ({listed}); remove the ones to leave")
    return tied[0]


def _new_run(
    benchmark: Benchmark,
    task: Task,
    name: RunName,
    config: Path,
    pinned: project_mod.Project | None,
    source: Path,
    echo: bool,
) -> Run:
    workspace = config.parent
    return Run(
        task=task,
        name=name,
        stage=workspace / "stage",
        scratch=workspace / "scratch",
        workspace=workspace,
        config=config.resolve(),
        data=benchmark.data,
        benchmark=benchmark,
        project=pinned.path if pinned else source,
        pinned=pinned,
        echo=echo,
    )


def _open_segment() -> dict[str, Any]:
    return {"started": _now(), "ended": None, "outcome": None}


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _drive(
    run: Run,
    state: dict[str, Any],
    *,
    root: Path,
    pin_requested: bool,
    done: Sequence[StepOutcome],
) -> RunResult:
    """Run the steps and the score of one segment, then either write the result or leave the workspace resumable."""
    name = run.name
    task = run.task
    pinned = run.pinned
    try:
        run.write_json(run.workspace / ROUND_FILE, state)
        try:
            with _without_operator_env():
                try:
                    outcomes = _run_steps(run, done)
                finally:
                    reap.reap(run.stage)

                score = _score(run, task) if task.score else None
        except (RoundInterrupted, KeyboardInterrupt) as stopped:
            _interrupt(run, state, pin_requested)
            command = f"paddock resume {name.benchmark} {name.task} {name.n}"
            raise RoundInterrupted(f"round {name} was interrupted; resume it with `{command}`") from stopped

        escaped = project_mod.degraded(pinned, requested=pin_requested) + project_mod.escaped(pinned)
        for caveat in escaped:
            logger.warning("%s", caveat)
        failed = [f"step {o.name!r} {o.status}" for o in outcomes if o.status != "ok"]
        caveats = (*state["caveats"], *failed, *escaped, *(score.caveats if score else ()))
        _end_segment(state, "finished")
        result = names.result_dir(root, name)
        _write_ledger(run, result / "ledger.json", outcomes, caveats, state)
        run.write_json(result / "score.json", score.as_json() if score else None)
        shutil.copyfile(run.config, result / "config.toml")
        shutil.copytree(run.stage, result / "stage", symlinks=True)
    finally:
        project_mod.release(pinned)

    return RunResult(
        name=name,
        workspace=run.workspace,
        stage=run.stage,
        result=result,
        outcomes=tuple(outcomes),
        score=score,
        caveats=caveats,
    )


def _interrupt(run: Run, state: dict[str, Any], pin_requested: bool) -> None:
    """Record an interrupted segment, and what it did to its pin, before the pin is released."""
    pinned = run.pinned
    state["caveats"] = [
        *state["caveats"],
        *project_mod.degraded(pinned, requested=pin_requested),
        *project_mod.escaped(pinned),
    ]
    _end_segment(state, "interrupted")
    run.write_json(run.workspace / ROUND_FILE, state)


def _end_segment(state: dict[str, Any], outcome: str) -> None:
    segments = state["segments"]
    segments[-1] = {**segments[-1], "ended": _now(), "outcome": outcome}


def _run_steps(run: Run, done: Sequence[StepOutcome] = ()) -> list[StepOutcome]:
    """Run the steps in order, stopping at the first failure, and keep the ones already finished."""
    finished = {outcome.name: outcome for outcome in done if outcome.status == "ok"}
    outcomes: list[StepOutcome] = []
    for item in run.task.steps:
        if item.name in finished:
            outcomes.append(finished[item.name])
            continue
        outcomes.append(_run_step(run, item))
        run.write_json(run.workspace / STEPS_FILE, [_step_json(outcome) for outcome in outcomes])
        if outcomes[-1].status != "ok":
            skipped = [
                StepOutcome(name=later.name, status="skipped", seconds=0.0)
                for later in run.task.steps[len(outcomes):]
            ]
            return outcomes + skipped
    return outcomes


def _run_step(run: Run, item: Step) -> StepOutcome:
    run.step_name = item.name
    run.commands = []
    run.exit_codes = []
    logger.info("step %s", item.name)
    started = time.monotonic()
    try:
        item.fn(run)
    except RoundInterrupted:
        raise
    except Exception as exc:  # noqa: BLE001 - a step is task-supplied code; the ledger is the report
        logger.error("step %s failed: %s", item.name, exc)
        return StepOutcome(
            name=item.name,
            status="failed",
            seconds=time.monotonic() - started,
            error=f"{type(exc).__name__}: {exc}",
            commands=tuple(run.commands),
            exit_codes=tuple(run.exit_codes),
        )
    return StepOutcome(
        name=item.name,
        status="ok",
        seconds=time.monotonic() - started,
        commands=tuple(run.commands),
        exit_codes=tuple(run.exit_codes),
    )


def _step_json(outcome: StepOutcome) -> dict[str, Any]:
    return {
        "name": outcome.name,
        "status": outcome.status,
        "seconds": round(outcome.seconds, 3),
        "error": outcome.error,
        "commands": [list(argv) for argv in outcome.commands],
        "exit_codes": list(outcome.exit_codes),
    }


def _outcome_of(item: Mapping[str, Any]) -> StepOutcome:
    return StepOutcome(
        name=item["name"],
        status=item["status"],
        seconds=float(item["seconds"]),
        error=item.get("error", ""),
        commands=tuple(tuple(argv) for argv in item.get("commands", ())),
        exit_codes=tuple(item.get("exit_codes", ())),
    )


def _write_ledger(
    run: Run,
    path: Path,
    outcomes: Sequence[StepOutcome],
    caveats: Sequence[str],
    state: Mapping[str, Any],
) -> None:
    run.write_json(
        path,
        {
            "name": str(run.name),
            "benchmark": run.name.benchmark,
            "task": run.name.task,
            "data_commit": run.name.data_commit,
            "repos": dict(state["repos"]),
            "stablemate": run.name.stablemate,
            "config": str(run.config),
            "project": state["project"],
            "caveats": list(caveats),
            "segments": list(state["segments"]),
            "steps": [_step_json(outcome) for outcome in outcomes],
        },
    )


def _score(run: Run, task: Task) -> Score | None:
    """Call the task's score function with the staged tree guarded as read-only."""
    if task.score is None:
        return None
    run.step_name = "score"
    run.commands = []
    run.exit_codes = []
    before = manifest.manifest(run.stage)
    score = task.score(run)
    changes = manifest.diff_manifests(before, manifest.manifest(run.stage))
    if changes:
        listed = "\n  ".join(changes[:20])
        raise RunError(
            f"task {task.name!r}: score() mutated the result, which must be read-only:\n  {listed}"
        )
    if not isinstance(score, Score):
        raise RunError(f"task {task.name!r}: score() returned {type(score).__name__}, expected Score")
    return score
