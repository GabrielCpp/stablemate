"""Load a benchmark from the root's `gold/` folder and freeze the task it declared."""

from __future__ import annotations

import importlib.util
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

from paddock import paths
from paddock.registry import REGISTRY, Task, TaskError, collect


@dataclass(frozen=True, slots=True)
class Benchmark:
    """One folder under `gold/`: the repository under measurement, its base config and its tasks."""

    name: str
    directory: Path
    tasks: tuple[Task, ...]

    def task(self, name: str) -> Task:
        for item in self.tasks:
            if item.name == name:
                return item
        known = ", ".join(item.name for item in self.tasks) or "(none)"
        raise TaskError(f"benchmark {self.name!r} declares no task named {name!r}. Known: {known}")

    @property
    def root(self) -> Path:
        return self.directory

    @property
    def home_config(self) -> Path:
        return self.directory / paths.HOME_CONFIG

    @property
    def data(self) -> Path:
        return self.directory / paths.DATA


def load_path(path: Path) -> tuple[Task, ...]:
    """Import one tasks module and return the `Task`s it declared."""
    module_name = f"paddock._benchmark_{path.parent.name}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise TaskError(f"{path}: not an importable Python module")
    module: ModuleType = importlib.util.module_from_spec(spec)
    REGISTRY.reset()
    sys.modules[module_name] = module
    directory = str(path.parent)
    sys.path.insert(0, directory)
    try:
        try:
            spec.loader.exec_module(module)
        finally:
            sys.path.remove(directory)
        return collect(str(path), (module.__doc__ or "").strip())
    finally:
        sys.modules.pop(module_name, None)
        _forget_helpers(path.parent)
        REGISTRY.reset()


def _forget_helpers(directory: Path) -> None:
    """Drop the modules imported from *directory*, so a same-named helper in another benchmark is its own."""
    for name, loaded in list(sys.modules.items()):
        origin = getattr(loaded, "__file__", None)
        if origin and Path(origin).parent == directory:
            del sys.modules[name]


def benchmark_names(root: Path) -> list[str]:
    gold = paths.gold_dir(root)
    if not gold.is_dir():
        return []
    return sorted(entry.name for entry in gold.iterdir() if entry.is_dir() and not entry.name.startswith("."))


def load_benchmark(root: Path, name: str) -> Benchmark:
    directory = paths.benchmark_dir(root, name)
    if not directory.is_dir():
        known = ", ".join(benchmark_names(root)) or "(none)"
        raise TaskError(f"no benchmark named {name!r} in {paths.gold_dir(root)}. Known: {known}")
    missing = [
        part
        for part in (paths.HOME_CONFIG, paths.TASKS, paths.DATA)
        if not (directory / part).exists()
    ]
    if missing:
        raise TaskError(f"benchmark {name!r} lacks {', '.join(missing)} in {directory}")
    return Benchmark(name=name, directory=directory, tasks=load_path(directory / paths.TASKS))


def load_all(root: Path) -> list[Benchmark]:
    return [load_benchmark(root, name) for name in benchmark_names(root)]


def load_task(root: Path, benchmark: str, task: str) -> tuple[Benchmark, Task]:
    """The benchmark *benchmark* and its task called *task*."""
    loaded = load_benchmark(root, benchmark)
    return loaded, loaded.task(task)
