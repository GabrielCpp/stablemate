"""A trial tree that is one repo or a folder of repos, and what a workflow needs to run in it."""

from __future__ import annotations

import os
import tomllib
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import tomli_w

from paddock import names
from paddock._vendor.stablemate_core import config as core_config
from paddock.runner import Run
from paddock.tasks import stablemate as sm
from paddock.tasks.stablemate import TrialError


def members(source: Path) -> tuple[str, ...]:
    """The member names of *source*: none for one repo, else one per child repo."""
    if (source / ".git").exists():
        return ()
    return tuple(child.name for child in names.repo_children(source))


def stage_members(run: Run) -> tuple[str, ...]:
    """The member names of the run's data, which are the child names of its stage."""
    return members(run.data)


def repos_at(root: Path, member_names: tuple[str, ...]) -> dict[str, Path]:
    """Each repo of the tree at *root* by member name; the one repo of a single-repo tree is keyed `""`."""
    if not member_names:
        return {"": root}
    return {name: root / name for name in member_names}


def _config_of(path: Path) -> dict[str, Any]:
    return tomllib.loads(path.read_text(encoding="utf-8"))


def _entry_path(entry: object) -> str | None:
    if isinstance(entry, str):
        return entry
    if isinstance(entry, dict):
        value = cast(dict[str, object], entry).get("path")
        return value if isinstance(value, str) else None
    return None


def _inside(value: str, stage: Path) -> Path | None:
    """The path *value* relative to *stage*, or None when it names somewhere else."""
    try:
        return Path(value).expanduser().resolve().relative_to(stage.resolve())
    except ValueError:
        return None


def staged_workspace(run: Run) -> str:
    """The name of the one `[workspaces]` entry whose members all sit in the stage, or `""` for one repo."""
    if not stage_members(run):
        return ""
    table = _config_of(run.config).get(core_config.WORKSPACES_KEY)
    entries = cast(dict[str, object], table) if isinstance(table, dict) else {}
    found = sorted(
        name
        for name, listed in entries.items()
        if isinstance(listed, list)
        and listed
        and all(
            (path := _entry_path(entry)) is not None and _inside(path, run.stage) is not None
            for entry in cast(list[object], listed)
        )
    )
    if len(found) != 1:
        known = ", ".join(sorted(entries)) or "(none)"
        raise TrialError(
            f"{run.config} needs exactly one [workspaces] entry whose repos are all inside the "
            f"stage; found {', '.join(found) or 'none'} (entries: {known})"
        )
    return found[0]


def _reroot(value: object, stage: Path, root: Path) -> object:
    if not isinstance(value, str):
        return value
    relative = _inside(value, stage)
    return value if relative is None else str(root / relative)


def trial_config(run: Run, root: Path) -> Path:
    """The effective config for the tree at *root*: its artifacts dir and workspace repos re-rooted from the stage."""
    source = sm.effective(run)
    if not stage_members(run):
        return source
    config = _config_of(source)
    if "artifacts_dir" in config:
        config["artifacts_dir"] = _reroot(config["artifacts_dir"], run.stage, root)
    table = config.get(core_config.WORKSPACES_KEY)
    if isinstance(table, dict):
        for listed in cast(dict[str, object], table).values():
            if not isinstance(listed, list):
                continue
            entries = cast(list[object], listed)
            for index, entry in enumerate(entries):
                if isinstance(entry, dict):
                    row = cast(dict[str, object], entry)
                    row["path"] = _reroot(row.get("path"), run.stage, root)
                else:
                    entries[index] = _reroot(entry, run.stage, root)
    target = root.with_name(f"{root.name}.stablemate-config.toml")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(tomli_w.dumps(config), encoding="utf-8")
    return target


def docs_home(run: Run, root: Path) -> Path:
    """Where the docs and specs of the tree at *root* live: the re-rooted artifacts dir, or the single repo's trial artifacts."""
    if not stage_members(run):
        return sm.trial_artifacts(root)
    configured = _config_of(sm.effective(run)).get("artifacts_dir")
    if not isinstance(configured, str) or _inside(configured, run.stage) is None:
        raise TrialError(
            f"{sm.effective(run)} has no `artifacts_dir` inside the stage; a multi-repo "
            "benchmark keeps its docs in one of its repos"
        )
    return Path(cast(str, _reroot(configured, run.stage, root)))


def witness_docs(run: Run, root: Path) -> Path:
    """The folder of *root* that holds the book: the root itself for one repo, else the docs home."""
    return docs_home(run, root) if stage_members(run) else root


@contextmanager
def _workspace_env(home: Path, config: Path) -> Iterator[None]:
    keys = (core_config.ARTIFACTS_DIR_ENV, core_config.CONFIG_PATH_ENV)
    previous = {key: os.environ.get(key) for key in keys}
    os.environ[core_config.ARTIFACTS_DIR_ENV] = str(home)
    os.environ[core_config.CONFIG_PATH_ENV] = str(config)
    try:
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def spec_dir(run: Run, root: Path, story: str) -> Path:
    """The story's spec folder in the tree at *root*, as ostler resolves it."""
    if not stage_members(run):
        return sm.spec_dir(root, story)
    from ostler.api import Ostler  # noqa: PLC0415 - a heavy import only a trial needs

    home = docs_home(run, root)
    with _workspace_env(home, trial_config(run, root)):
        return Path(Ostler(home).spec_path(story))


@dataclass(frozen=True, slots=True)
class Launch:
    """What one workflow invocation in a trial tree is started with."""

    config: Path
    workspace: str
    repo_dir: Path
    env: dict[str, str]

    def flags(self) -> list[str]:
        flags = ["--config", str(self.config)]
        if self.workspace:
            flags += ["--workspace", self.workspace]
        return flags


def launch(run: Run, root: Path) -> Launch:
    """The config, workspace, working repo and environment for a workflow in the tree at *root*."""
    if not stage_members(run):
        return Launch(sm.effective(run), "", root, sm.trial_env(root))
    home = docs_home(run, root)
    config = trial_config(run, root)
    return Launch(
        config,
        staged_workspace(run),
        home,
        {**os.environ, core_config.ARTIFACTS_DIR_ENV: str(home), core_config.CONFIG_PATH_ENV: str(config)},
    )
