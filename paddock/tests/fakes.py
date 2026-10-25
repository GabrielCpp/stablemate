"""A stand-in for the `Run` handle, carrying only what a task helper reads."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import tomli_w
from smoke import git

from paddock import homeconfig
from paddock.names import RunName
from paddock.registry import Input
from paddock.runner import Run


def fake_run(
    tmp_path: Path,
    *,
    inputs: dict[str, Input] | None = None,
    root: Path | None = None,
    repos: dict[str, Path] | None = None,
) -> Run:
    """A run whose stage is `tmp_path/stage` and whose benchmark folder is *root* (default `tmp_path/bench`)."""
    bench = root or tmp_path / "bench"
    bench.mkdir(parents=True, exist_ok=True)
    stage = tmp_path / "stage"
    stage.mkdir(parents=True, exist_ok=True)
    return cast(Run, SimpleNamespace(
        inputs=inputs or {},
        benchmark=SimpleNamespace(root=bench, name="bench", data=bench / "data"),
        data=bench / "data",
        stage=stage,
        write_json=_write_json,
        scratch=tmp_path / "scratch",
        repo=stage,
        repos=repos if repos is not None else {"bench": stage},
        name=RunName("bench", "task", "a" * 12, "b" * 12, 3),
    ))


PRODUCTS = ("api-service", "web-app")

DOCS = "artifacts"

STORY = "S-1"

EPIC_MD = f"""---
type: epic
id: e-1
title: e1
---
# Epic: e1

## Stories

### {STORY}
- title: First
- covers: (none)
"""

STORY_MD = f"""---
type: story
slug: {STORY}
id: {STORY}
status: Not started
---
# Story: First
"""


def commit_all(repo: Path, message: str) -> str:
    git(repo, "add", "-A")
    git(repo, "commit", "--quiet", "-m", message)
    return git(repo, "rev-parse", "HEAD")


def init_repo(path: Path, files: dict[str, str]) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    for rel, body in files.items():
        (path / rel).parent.mkdir(parents=True, exist_ok=True)
        (path / rel).write_text(body, encoding="utf-8")
    git(path, "init", "--quiet", "--initial-branch", "main")
    git(path, "config", "user.email", "paddock@example.com")
    git(path, "config", "user.name", "paddock")
    commit_all(path, "initial")
    return path


def folder_run(tmp_path: Path) -> Run:
    """A run whose stage is a folder of two product repos and a docs home, with a config naming them as a workspace."""
    bench = tmp_path / "bench"
    data = bench / "data"
    init_repo(data / PRODUCTS[0], {"app.py": "api = 1\n", "agents.yml": "repo: {}\n"})
    init_repo(data / PRODUCTS[1], {"app.py": "web = 1\n", "agents.yml": "repo: {}\n"})
    init_repo(
        data / DOCS,
        {
            "docs/epics/e1/epic.md": EPIC_MD,
            f"docs/epics/e1/stories/{STORY}/story.md": STORY_MD,
            "docs/services/book.md": "# book\n",
            f"specs/{STORY}/qa-plan.yml": "stale\n",
        },
    )
    stage = tmp_path / "stage"
    stage.mkdir(exist_ok=True)
    for name in (*PRODUCTS, DOCS):
        shutil.rmtree(stage / name, ignore_errors=True)
        subprocess.run(
            ["git", "clone", "--quiet", str(data / name), str(stage / name)], check=True, capture_output=True
        )
        git(stage / name, "config", "user.email", "paddock@example.com")
        git(stage / name, "config", "user.name", "paddock")
    base = bench / "home-config.toml"
    base.write_text(
        tomli_w.dumps({"artifacts_dir": DOCS, "workspaces": {"desk": list(PRODUCTS)}}), encoding="utf-8"
    )
    scratch = tmp_path / "scratch"
    scratch.mkdir(exist_ok=True)
    config = homeconfig.materialize(base, {}, tmp_path / "config.toml", stage=stage)
    (scratch / "stablemate-config.toml").write_text(config.read_text(encoding="utf-8"), encoding="utf-8")
    return cast(Run, SimpleNamespace(
        inputs={},
        benchmark=SimpleNamespace(root=bench, name="bench", data=data),
        data=data,
        stage=stage,
        scratch=scratch,
        config=config,
        repos={name: stage / name for name in (*PRODUCTS, DOCS)},
        name=RunName("bench", "task", "a" * 12, "b" * 12, 3),
        workdir=lambda name: _fresh(scratch / name),
        write_json=_write_json,
    ))


def _fresh(path: Path) -> Path:
    shutil.rmtree(path, ignore_errors=True)
    path.mkdir(parents=True)
    return path


def _write_json(path: Path, data: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")
    return path
