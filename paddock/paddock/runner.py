"""Run a task: unpack the seed, execute the steps, stage the result, score it, seal it.

The staging layout is the contract between a task's steps and everything downstream:

```
<store>/work/<task>/<label>/
  stage/                     <- everything here, and only this, becomes the result zip
    <repo_dir>/              <- the unpacked seed, mutated by the steps
    artifacts/<step>/        <- run dirs, logs, exit codes; one directory per step
    steps.json               <- the ledger: order, outcome, duration, commands run
    score.json               <- written only when the task brought a score function
  scratch/                   <- steps' own working space, deliberately NOT zipped
```

`scratch/` exists because a task may fan out — policy-desk runs a fresh tree per trial —
and a result zip carrying nine copies of a repo is a result nobody will keep. What a step
wants preserved it copies into its artifact directory, which makes that an explicit
decision rather than a side effect of where it happened to work.
"""

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
from contextlib import AbstractContextManager, nullcontext
from dataclasses import dataclass, field
from pathlib import Path

from paddock import archive, paths, project as project_mod, reap, seeds
from paddock.pointer import DIAGNOSTIC_MARKER, Pointer, ResultPointer
from paddock.registry import Score, Step, Task

logger = logging.getLogger(__name__)


class RunError(RuntimeError):
    """A task that could not be run, or a result that must not be sealed."""


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


class _Echo:
    """Follow a command's log file while it is being written, echoing it to stderr.

    A tail, not a pipe: `subprocess.run` keeps owning the child's stdout, so the timeout,
    the exit code and the bytes that land in the log are exactly what they were before the
    echo existed — this thread only ever reads what has already been written.

    Why it exists: a trial that drives an agent CLI for forty minutes writes its only sign
    of life into a log three directories deep, named after a step that has not finished
    yet. Teeing makes `paddock run > run.log` the whole story, for the operator and for
    the agent polling on their behalf.
    """

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
        """Echo whole lines written since *offset*, and return the new offset.

        Bytes rather than text, and never past the last newline: a partial write is left
        in place to be re-read whole, so a line never arrives split across two ticks.
        """
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
    """The handle a step and a score function are given.

    A step reaches the repo through `run.repo`, keeps evidence in `run.artifacts`, works
    in `run.scratch`, and invokes tooling through `run.cli` — which is a subprocess of the
    real command line, never an in-process import of workhorse. That is not purity for its
    own sake: the benchmark measures the surface an operator uses, and an in-process call
    would measure a different one.
    """

    task: Task
    label: str
    stage: Path
    repo: Path
    scratch: Path
    config: Path
    data_dir: Path
    store: Path
    seed: Pointer
    params: Mapping[str, str] = field(default_factory=dict)
    project: Path | None = None
    pinned: project_mod.Project | None = None
    echo: bool = True
    step_name: str = ""
    commands: list[tuple[str, ...]] = field(default_factory=list)
    outcomes: list[StepOutcome] = field(default_factory=list)

    def param(self, name: str, default: str = "") -> str:
        """A `--param name=value` given on the command line, or *default*.

        Params are how a task is run *smaller* than its full self — one defect instead of
        eleven, a shorter budget — without editing the module or growing a second task.
        They are recorded in the ledger and in the result pointer's note, because a round
        run with a param is a different measurement and a result that does not say so is
        the one that gets compared against a full one.
        """
        return str(self.params.get(name, default))

    def param_list(self, name: str) -> tuple[str, ...]:
        """A comma-separated param as a tuple; `()` when it was not given."""
        return tuple(part.strip() for part in self.param(name).split(",") if part.strip())

    def param_float(self, name: str, default: float = 0.0) -> float:
        raw = self.param(name)
        if not raw:
            return default
        try:
            return float(raw)
        except ValueError as exc:
            raise RunError(f"--param {name}={raw!r} is not a number") from exc

    def param_bool(self, name: str, default: bool = False) -> bool:
        raw = self.param(name).strip().lower()
        if not raw:
            return default
        if raw in ("1", "true", "yes", "on"):
            return True
        if raw in ("0", "false", "no", "off"):
            return False
        raise RunError(f"--param {name}={raw!r} is not a boolean")

    @property
    def artifacts(self) -> Path:
        """This step's artifact directory, created on first use."""
        directory = self.stage / "artifacts" / (self.step_name or "run")
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
        """Run a command, tee its output to a log under `artifacts/` and to stderr.

        `PWD` is aligned to *cwd* and `OLDPWD` dropped. An agent CLI that resolves its
        project root from the environment rather than from `getcwd()` will otherwise treat
        the harness's own repo as the project and commit its work there — a failure that
        looks like the benchmark producing no diff at all.
        """
        target = cwd or self.repo
        merged = dict(os.environ if env is None else env)
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
        result = CommandResult(tuple(argv), completed.returncode, log)
        return result.check() if check else result

    def _echo(self, log: Path, name: str) -> AbstractContextManager[object]:
        """The live tee for one command, or a no-op when the run asked for quiet."""
        return _Echo(log, name) if self.echo else nullcontext()

    def read_json(self, path: Path) -> dict:
        return json.loads(path.read_text(encoding="utf-8"))

    def write_json(self, path: Path, data: object) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return path


@dataclass(frozen=True, slots=True)
class RunResult:
    task: str
    label: str
    stage: Path
    outcomes: tuple[StepOutcome, ...]
    score: Score | None
    zip_path: Path | None
    pointer_path: Path | None

    @property
    def ok(self) -> bool:
        return all(outcome.status == "ok" for outcome in self.outcomes)


def execute(
    task: Task,
    *,
    label: str,
    data_dir: Path,
    store: Path,
    params: Mapping[str, str] | None = None,
    project: Path | None = None,
    pin_project: bool = True,
    seal: bool = True,
    keep: bool = False,
    echo: bool = True,
) -> RunResult:
    work = paths.work_dir(store, task.name, label)
    if work.exists() and not keep:
        shutil.rmtree(work)
    stage = work / "stage"
    scratch = work / "scratch"
    stage.mkdir(parents=True, exist_ok=True)
    scratch.mkdir(parents=True, exist_ok=True)

    # Before anything is unpacked or run: the steps drive a tree of paddock's own, so the
    # round measures one commit of the code and any commit *in* that tree is a leak.
    pinned = project_mod.pin(project, work=work, enabled=pin_project)
    driven = pinned.path if pinned else project

    pointer = Pointer.load(paths.seed_pointer(data_dir, task.seed))
    repo = seeds.unpack(pointer, store=store, dest=stage, project=driven)

    # Relative to the *data* dir, not to the repo root: a config is data, it lives
    # beside the tasks that pin it, and a task that named its own root would break the
    # moment that root moved — which it has.
    config = Path(task.config)
    config = config if config.is_absolute() else data_dir / config
    config = config.resolve()
    if not config.is_file():
        raise RunError(f"task {task.name!r}: config {config} does not exist")

    run = Run(
        task=task,
        label=label,
        stage=stage,
        repo=repo,
        scratch=scratch,
        config=config,
        data_dir=data_dir,
        store=store,
        seed=pointer,
        params=dict(params or {}),
        project=driven,
        pinned=pinned,
        echo=echo,
    )
    try:
        try:
            outcomes = _run_steps(run)
        finally:
            # Before the ledger, the score and the zip — not in the outer `finally`. A
            # server still writing into the stage while `archive.create` walks it is a
            # result nobody can re-derive, and a step that raised is exactly the case
            # most likely to have left one running.
            reap.reap(stage)
        _write_ledger(run, outcomes)

        score = _score(run, task) if task.score else None
        if score is not None:
            run.write_json(stage / "score.json", score.as_json())

        zip_path: Path | None = None
        pointer_path: Path | None = None
        if seal:
            # Asked here rather than after `release`, because the question is about the
            # pinned tree and `release` deletes it.
            escaped = project_mod.escaped(pinned)
            for caveat in escaped:
                logger.warning("%s", caveat)
            zip_path, pointer_path = _seal(
                task, label, stage, data_dir, store, pointer, outcomes, score,
                run.params, escaped,
            )
    finally:
        project_mod.release(pinned)

    return RunResult(
        task=task.name,
        label=label,
        stage=stage,
        outcomes=tuple(outcomes),
        score=score,
        zip_path=zip_path,
        pointer_path=pointer_path,
    )


def _run_steps(run: Run) -> list[StepOutcome]:
    """Run the steps in order, stopping at the first failure.

    Stopping is the point: a later step's meaning is conditional on the earlier ones
    having happened, so continuing past a failure produces a result that scores as
    something rather than as nothing, which is worse than no result at all. What already
    ran stays staged, and the ledger says where it stopped.
    """
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
        )
    return StepOutcome(
        name=item.name,
        status="ok",
        seconds=time.monotonic() - started,
        commands=tuple(run.commands),
    )


def _write_ledger(run: Run, outcomes: Sequence[StepOutcome]) -> None:
    run.write_json(
        run.stage / "steps.json",
        {
            "task": run.task.name,
            "label": run.label,
            "seed": {"name": run.seed.name, "sha256": run.seed.sha256, "head": run.seed.head},
            "config": str(run.config),
            "project": run.pinned.as_json() if run.pinned else None,
            "params": dict(run.params),
            "steps": [
                {
                    "name": outcome.name,
                    "status": outcome.status,
                    "seconds": round(outcome.seconds, 3),
                    "error": outcome.error,
                    "commands": [list(argv) for argv in outcome.commands],
                }
                for outcome in outcomes
            ],
        },
    )


def _score_owned(path: str) -> bool:
    return path == "artifacts" or path == "artifacts/score" or path.startswith("artifacts/score/")


def _score(run: Run, task: Task) -> Score | None:
    """Call the task's score function with the staged tree guarded as read-only.

    Decision 14 of the design, enforced rather than documented: a scored and an unscored
    run must produce byte-identical results apart from `score.json`. A score function that
    edits what it measures makes the result zip a record of the scoring rather than of the
    run, and every later comparison against it is comparing the wrong thing.
    """
    if task.score is None:
        return None
    run.step_name = "score"
    run.commands = []
    before = archive.manifest(run.stage)
    score = task.score(run)
    # The score's own log output is the one thing it is allowed to add — which also moves
    # the mtime of the `artifacts/` directory holding it.
    changes = [
        line
        for line in archive.diff_manifests(before, archive.manifest(run.stage))
        if not _score_owned(line.split(" ", 1)[1])
    ]
    if changes:
        listed = "\n  ".join(changes[:20])
        raise RunError(
            f"task {task.name!r}: score() mutated the result, which must be read-only:\n  {listed}"
        )
    if not isinstance(score, Score):
        raise RunError(f"task {task.name!r}: score() returned {type(score).__name__}, expected Score")
    return score


def _seal(
    task: Task,
    label: str,
    stage: Path,
    data_dir: Path,
    store: Path,
    seed: Pointer,
    outcomes: Sequence[StepOutcome],
    score: Score | None,
    params: Mapping[str, str],
    escaped: Sequence[str] = (),
) -> tuple[Path, Path]:
    zip_path = paths.result_zip(store, task.name, label)
    archive.create(stage, zip_path, prefix=label)
    # The note is what a human reads in the tracked pointer without fetching the zip, so
    # a run narrowed by `--param` says so there: the same task under a smaller selection
    # is a different measurement, and one that does not announce it invites a comparison
    # against a full run that nobody would have made on purpose.
    given = ", ".join(f"{key}={value}" for key, value in sorted(params.items()))
    # A step that did not succeed is a caveat the runner can see without asking the task,
    # and it is the one that catches what a ruler cannot: a pin that drifted, or a build
    # that aborted, both of which fail a step *before* score() gets a turn. The task's own
    # caveats come from the other side — a parked gate is a fine round mechanically.
    # Named by their real status rather than all called "failed": the step that raised
    # and the ones skipped behind it are different facts, and a caveat that blurs them
    # sends the next reader looking for three defects where there was one.
    failed = [f"step {o.name!r} {o.status}" for o in outcomes if o.status != "ok"]
    caveats = [*failed, *escaped, *(score.caveats if score else ())]
    headline = score.headline if score else ""
    if caveats:
        headline = DIAGNOSTIC_MARKER + (headline or "unscored round")
    note = " ".join(part for part in (headline, f"[{given}]" if given else "") if part)
    pointer = ResultPointer(
        name=f"{task.name}/{label}",
        # A result zip roots at the label, not at the repo: the tree inside it is one
        # member of the staging area, beside the artifacts and the ledger.
        repo_dir=label,
        sha256=archive.digest(zip_path),
        bytes=zip_path.stat().st_size,
        head=seed.head,
        note=note,
        caveats=caveats,
        task=task.name,
        label=label,
        steps=sum(1 for outcome in outcomes if outcome.status == "ok"),
        scored=score is not None,
    )
    pointer_path = paths.result_pointer(data_dir, task.name, label)
    pointer.write(pointer_path)
    return zip_path, pointer_path
