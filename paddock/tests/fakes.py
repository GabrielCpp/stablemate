"""A stand-in for the `Run` handle, carrying only what a task helper reads."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import cast

from paddock.names import RunName
from paddock.registry import Input
from paddock.runner import Run


def fake_run(tmp_path: Path, *, inputs: dict[str, Input] | None = None, root: Path | None = None) -> Run:
    """A run whose stage is `tmp_path/stage` and whose benchmark folder is *root* (default `tmp_path/bench`)."""
    bench = root or tmp_path / "bench"
    bench.mkdir(parents=True, exist_ok=True)
    stage = tmp_path / "stage"
    stage.mkdir(parents=True, exist_ok=True)
    return cast(Run, SimpleNamespace(
        inputs=inputs or {},
        benchmark=SimpleNamespace(root=bench, name="bench", data=bench / "data"),
        stage=stage,
        repo=stage,
        name=RunName("bench", "task", "a" * 12, "b" * 12, 3),
    ))
