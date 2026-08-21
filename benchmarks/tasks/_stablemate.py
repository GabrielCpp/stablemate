"""The process boundary a paddock task drives stablemate across.

Three things every task family needs and none of them owns: the checkout `workhorse-coder`
is run out of, the effective config that run sees, and a `git` that raises with the command
in the message instead of returning a code nobody checked. They live apart from
`_frozenapp.py` because a greenfield build needs exactly the same three and shares none of
the round around them.

The leading underscore keeps `paddock.loader` from treating this as a task module.
"""

from __future__ import annotations

import subprocess
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from paddock import Run
from stablemate_core import config as core_config


class TrialError(RuntimeError):
    """A fixture or trial precondition that fails before anything has been measured."""


def git(*args: str, cwd: Path) -> str:
    proc = subprocess.run(
        ["git", *args], cwd=str(cwd), capture_output=True, text=True, check=False
    )
    if proc.returncode != 0:
        raise TrialError(f"git {' '.join(args)} in {cwd}: {proc.stderr.strip()}")
    return proc.stdout


@contextmanager
def no_leaks(checkout: Path) -> Iterator[None]:
    """Fail the round if anything it ran committed into *checkout* instead of its sandbox.

    Not a warning. An agent that resolved its project root to the harness's own checkout
    committed the work there, which means the tree the round was measured on is not the
    tree it wrote to — every number it produced is void.

    Read against the tree paddock pinned for this round, which nobody else writes to, so a
    commit here is a leak by construction rather than by heuristic and an operator
    committing in their own checkout is invisible. Raising rather than returning a flag is
    deliberate: the caller that forgot to look is exactly the caller this exists for.
    """
    before = git("rev-parse", "HEAD", cwd=checkout).strip()
    yield
    leaked = git("log", "--oneline", f"{before}..HEAD", cwd=checkout).strip()
    if leaked:
        raise TrialError(
            f"the round committed into {checkout} instead of its sandboxes:\n{leaked}\n"
            f"drop those commits before believing any number here"
        )


def stablemate_dir() -> Path:
    """The stablemate checkout the trials drive `workhorse-coder` out of.

    Read from the machine's own stablemate config rather than from anything tracked: it is
    an absolute path on this disk, it differs on every machine, and in a public repo it is
    also somebody's directory name.
    """
    resolved = core_config.resolve_stablemate_dir()
    if resolved is None or not (resolved / "pyproject.toml").is_file():
        raise TrialError(
            "no `stablemate_dir` in the machine's stablemate config — the trials need a "
            "checkout to run `workhorse-coder` out of (set it with `farrier config`)"
        )
    return resolved


def stablemate_checkout(run: Run) -> Path:
    """The checkout *this run* drives, which is not always the operator's.

    paddock pins the project to a detached worktree at the checkout's HEAD, so a round
    measures one commit of the code even while the operator keeps editing theirs. When it
    is pinned, `run.project` is that worktree and everything the round reads about the
    code — the workflow source it dates itself against, the git log the leak check reads —
    has to come from there, or the trial is measured against a tree it never ran.

    Falls back to the machine's configured checkout when the run was given no project (a
    task invoked outside `paddock run`, or `--no-pin-project` on a source git could not
    make a worktree of).
    """
    project = run.project
    if project is not None and (project / "pyproject.toml").is_file():
        return project
    return stablemate_dir()


def uv_run(checkout: Path, package: str) -> list[str]:
    """The `uv run` prefix that runs *checkout*'s own code, not this machine's.

    `--project` alone does not do that: the workspace root is an anchor with no
    dependencies, so the checkout's environment contains none of the tools, and a
    command uv cannot find in the project environment silently falls back to `$PATH` —
    where an editable install resolves every workflow module to the operator's live
    tree, straight through paddock's pin. `--package` names the workspace member whose
    environment the command runs in, which installs that member and its workspace
    dependencies editable *from the checkout* into the checkout's own `.venv`.
    """
    return ["uv", "run", "--project", str(checkout), "--package", package]


def effective(run: Run) -> Path:
    return run.scratch / "stablemate-config.toml"


def pin_config(run: Run) -> None:
    """Write the effective stablemate config the trials run under, into `scratch/`.

    `--config` is whole-file replacement, not a merge, so the file handed to workhorse must
    carry the machine-local roots (`library_dir`, `stablemate_dir`, …) as well as the model
    tables. The tracked config carries only the models, deliberately: an absolute path baked
    into it is wrong on every other machine, and in this repo it is also a private name in a
    public tree.

    So the two halves are joined here, at run time, and the join lands in `scratch/` — which
    is not sealed into the result. A rendered config is the one artifact of a run that is
    guaranteed to contain somebody's home directory.
    """
    machine = core_config.load_config()
    local = {
        name: str(value)
        for name in ("library_dir", "base_dir", "stablemate_dir", "worktree_dir")
        if isinstance(value := core_config.get_config_value(name, machine), str) and value
    }
    # The pin has to reach the config too: `stablemate_dir` names "the checkout", and
    # for a pinned run that is the round's worktree, not the operator's live tree —
    # anything a trial derives from the checkout (base-library discovery, farrier's
    # launcher) must read the tree the round is measured on, or an edit the operator
    # makes mid-round leaks into the trials through the config.
    local["stablemate_dir"] = str(stablemate_checkout(run))
    if "library_dir" not in local:
        raise TrialError(
            "no `library_dir` in the machine's stablemate config — a run given --config "
            "inherits nothing from the machine's, so the library root has to come from here"
        )
    header = (
        "# Generated by a paddock task. The model tables come from the tracked\n"
        "# config; the paths below are this machine's and are why this file is not tracked.\n"
    )
    rendered = "\n".join(f'{name} = "{path}"' for name, path in sorted(local.items()))
    effective(run).write_text(
        f"{header}{rendered}\n\n{run.config.read_text(encoding='utf-8')}", encoding="utf-8"
    )
