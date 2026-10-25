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
from collections.abc import Mapping, Sequence
from types import MappingProxyType
from contextlib import AbstractContextManager, nullcontext
from dataclasses import dataclass, field
from pathlib import Path

from paddock import homeconfig, manifest, names, paths, project as project_mod, reap
from paddock.loader import Benchmark
from paddock.names import RunName
from paddock._vendor.stablemate_core.config import CONFIG_PATH_ENV
from paddock.registry import Input, Score, Step, Task

logger = logging.getLogger(__name__)


class RunError(RuntimeError):
    """A task that could not be run, or a result that must not be recorded."""


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
    def repo(self) -> Path:
        """The copy of the benchmark's data the steps mutate."""
        return self.stage

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
    driven = pinned.path if pinned else source

    run = Run(
        task=task,
        name=name,
        stage=stage,
        scratch=scratch,
        workspace=workspace,
        config=config.resolve(),
        data=benchmark.data,
        benchmark=benchmark,
        project=driven,
        pinned=pinned,
        echo=echo,
    )
    try:
        try:
            outcomes = _run_steps(run)
        finally:
            reap.reap(stage)

        score = _score(run, task) if task.score else None

        escaped = project_mod.degraded(pinned, requested=pin_project) + project_mod.escaped(pinned)
        for caveat in escaped:
            logger.warning("%s", caveat)
        failed = [f"step {o.name!r} {o.status}" for o in outcomes if o.status != "ok"]
        caveats = (*failed, *escaped, *(score.caveats if score else ()))
        result = names.result_dir(root, name)
        _write_ledger(run, result / "ledger.json", outcomes, caveats, data_commit, stablemate)
        run.write_json(result / "score.json", score.as_json() if score else None)
        shutil.copyfile(config, result / "config.toml")
        shutil.copytree(stage, result / "stage", symlinks=True)
    finally:
        project_mod.release(pinned)

    return RunResult(
        name=name,
        workspace=workspace,
        stage=stage,
        result=result,
        outcomes=tuple(outcomes),
        score=score,
        caveats=caveats,
    )


def _run_steps(run: Run) -> list[StepOutcome]:
    """Run the steps in order, stopping at the first failure."""
    outcomes: list[StepOutcome] = []
    for item in run.task.steps:
        outcomes.append(_run_step(run, item))
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


def _write_ledger(
    run: Run,
    path: Path,
    outcomes: Sequence[StepOutcome],
    caveats: Sequence[str],
    data_commit: str,
    stablemate: str,
) -> None:
    run.write_json(
        path,
        {
            "name": str(run.name),
            "benchmark": run.name.benchmark,
            "task": run.name.task,
            "data_commit": data_commit,
            "stablemate": stablemate,
            "config": str(run.config),
            "project": run.pinned.as_json() if run.pinned else None,
            "caveats": list(caveats),
            "steps": [
                {
                    "name": outcome.name,
                    "status": outcome.status,
                    "seconds": round(outcome.seconds, 3),
                    "error": outcome.error,
                    "commands": [list(argv) for argv in outcome.commands],
                    "exit_codes": list(outcome.exit_codes),
                }
                for outcome in outcomes
            ],
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
