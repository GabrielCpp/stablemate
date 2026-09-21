"""Import a task module and freeze what it declared."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

from paddock import paths
from paddock.registry import REGISTRY, ScoreFn, Task, TaskError, collect


def _put_script_dir_on_path(directory: Path) -> None:
    entry = str(directory)
    if entry not in sys.path:
        sys.path.insert(0, entry)


def task_paths(data_dir: Path) -> list[Path]:
    directory = paths.tasks_dir(data_dir)
    if not directory.is_dir():
        return []
    return sorted(p for p in directory.glob("*.py") if not p.name.startswith("_"))


def load_path(path: Path) -> Task:
    """Import one task module and return the `Task` it declared."""
    module_name = f"paddock._task_{path.stem}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise TaskError(f"{path}: not an importable Python module")
    module: ModuleType = importlib.util.module_from_spec(spec)
    REGISTRY.reset()
    sys.modules[module_name] = module
    try:
        _put_script_dir_on_path(path.parent)
        spec.loader.exec_module(module)
        score: ScoreFn | None = getattr(module, "score", None)
        if score is not None and not callable(score):
            raise TaskError(f"{path}: `score` is defined but is not callable")
        return collect(str(path), score, (module.__doc__ or "").strip())
    finally:
        sys.modules.pop(module_name, None)
        REGISTRY.reset()


def load_all(data_dir: Path) -> list[Task]:
    """Every task in the data directory, each import isolated from the others' failures."""
    tasks = [load_path(path) for path in task_paths(data_dir)]
    seen: dict[str, str] = {}
    for item in tasks:
        if item.name in seen:
            raise TaskError(f"task {item.name!r} is declared twice: {seen[item.name]} and {item.module}")
        seen[item.name] = item.module
    return tasks


def load_named(data_dir: Path, name: str) -> Task:
    for path in task_paths(data_dir):
        candidate = load_path(path)
        if candidate.name == name:
            return candidate
    known = ", ".join(item.name for item in load_all(data_dir)) or "(none)"
    raise TaskError(f"no task named {name!r} in {paths.tasks_dir(data_dir)} — known: {known}")
