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

from paddock import Run, project
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


def _describe(checkout: Path) -> list[str]:
    """What the toolchain looks like right now: its `git status --porcelain` lines, and
    the commit it is sitting on.

    Read through the git directory paddock stashed beside the pin, because the pin itself
    is fenced off from git: a bare `git -C` there fails with the fence's error, which is
    the right answer to a write and the wrong one to a question. Falls back to reading the
    tree directly for an unpinned run, where the fence does not exist.

    HEAD is in the description rather than only in `escaped`'s round-level check because
    committing is how an edit stops showing up in `status`: patch, commit, and the tree is
    clean again. Asking per trial is what names *which* trial did it, which is the whole
    reason a trial-level check exists next to a round-level one.
    """
    stashed = project.stashed_git_dir(checkout)
    where = ["--git-dir", str(stashed), "--work-tree", str(checkout)] if stashed.is_dir() else []
    lines = [line for line in git(*where, "status", "--porcelain", cwd=checkout).splitlines() if line]
    head = git(*where, "rev-parse", "HEAD", cwd=checkout).strip()
    return [*lines, f"committed — HEAD is now {head}"]


def pin_held(pin: project.Project | None) -> bool:
    """Whether a round got the pin it was configured for — not merely asked for one.

    `run.pinned` is `None` for a task driving no project at all, and a `Project` with
    `pinned=False` both for a deliberate `--no-pin-project` and for a pin that was asked
    for and could not be made. All three share the one property the leak check turns on:
    the tree it reads is somebody else's working checkout, not a clone nobody else can
    reach. Taking the pin rather than the `Run` is so the three cases can be stated in a
    test without standing up a round to say them.
    """
    return pin is not None and pin.pinned


@contextmanager
def no_leaks(checkout: Path, *, pinned: bool) -> Iterator[None]:
    """Fail the round if the toolchain checkout changed while it ran.

    Not a warning. An agent that resolved its project root to the harness's own checkout
    wrote the work there, which means the tree the round was measured on is not the tree
    it ran — every number it produced is void.

    Written state *and* the commit the toolchain sits on, because each covers the other's
    blind spot. A check keyed only on `git log` calls the round that patched the toolchain
    and never committed clean, and that round spent its remaining hours running the patch.
    A check keyed only on `status` calls the round that patched and then committed clean,
    because committing is what makes an edit stop showing up there — and the pin is fenced
    but the git directory paddock stashed beside it is one `ls ..` from the sandbox, so
    that commit is available to a round that goes looking.

    *pinned* is what buys the accusation. Read against the tree paddock pinned for this
    round, nobody else writes there, so a change is a leak by construction rather than by
    heuristic and an operator editing their own checkout is invisible. Read against a
    shared checkout — `--no-pin-project`, or a pin that was asked for and could not be
    made — that premise is simply false, and the identical evidence supports only the
    weaker claim: the tree moved under the round. A teammate landing a commit mid-round
    produces it, and a report that says "the round wrote into X" there is an accusation
    the check cannot back, which somebody then has to disprove by hand.

    So the evidence is reported either way and the round still stops either way — an
    unpinned round is the only one where this is the sole tripwire, and a tripwire that
    only logs is not one. What changes is the finding. Attribution is earned by the pin.

    Raising rather than returning a flag is deliberate: the caller that forgot to look is
    exactly the caller this exists for.
    """
    before = set(_describe(checkout))
    yield
    leaked = sorted(set(_describe(checkout)) - before)
    if not leaked:
        return
    if pinned:
        raise TrialError(
            f"the round wrote into {checkout} instead of its sandboxes:\n"
            + "\n".join(leaked)
            + "\nrevert that before believing any number here"
        )
    raise TrialError(
        f"{checkout} changed while the round ran, and this round was not pinned — so "
        f"whether the round wrote this or somebody else did is not knowable from here:\n"
        + "\n".join(leaked)
        + "\nre-run pinned before believing any number here"
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
