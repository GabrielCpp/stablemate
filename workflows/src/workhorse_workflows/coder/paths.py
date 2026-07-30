"""Where things are: repo-root resolution, and the derived artifact paths.

Both kinds of thing here are here for the same reason `author/paths.py` gives — they were
duplicated verbatim across the YAML workflow's 71 scripts, once per file, and a
derivation copied dozens of times is a derivation nobody can change.

**Three repo-root resolvers, deliberately.** The scripts did not agree on how to find the
consuming repo, and the disagreement is behavioral, not cosmetic: a run launched from a
subdirectory, or from a repo whose `docs/epics/` exists but whose `.git` does not, lands
on a *different* root under each. So each is kept, named for what it actually does, and
each ported node calls the one its script called:

* `workhorse.scriptutil.find_repo_root` — `AGENT_REPO_DIR`, else the first of
  `[cwd, *cwd.parents]` carrying `agents.yml` or `.git`. Four scripts
  (`check-sentinel-ids.py`, `detect-regression-platform.py`, `flush-root-screenshots.py`,
  `verify_qa_evidence.py`) had re-typed this function *character for character* rather
  than importing it; those nodes now call the engine's copy, which is not a narrowing —
  the bodies were identical.
* `epics_repo_root()` — the same walk, but marked by `agents.yml` or a `docs/epics/`
  **directory** rather than `.git`. `prune-epic.py` alone resolves this way, and the
  difference matters exactly where it is used: a docs checkout with no `.git` (a
  bind-mounted clone) still has its epic queue popped.
* `launch_repo_root()` — `AGENT_REPO_DIR`, else `cwd` *if* it looks like a project root
  (`docs/epics/`, `agents.yml` or `.git`), else the first ancestor with `agents.yml` or
  `.git`, else `cwd`. The operator-gate scripts (`await_operator.py`,
  `await-ci-operator.py`, `await-merge-operator.py`) and `check_feedback.py` resolve this
  way. Its `cwd`-first probe is what lets a test harness point the gate at a sandbox by
  chdir alone, which the plain upward walk does not do.

The `await-*` scripts carried a fourth rung after all of that — a walk upward from
`__file__` — reached only when nothing above matched. Under the driver `__file__` is this
installed package, never the consuming repo, so that rung could only ever have returned
something wrong. It is dropped, and it is the one narrowing in this module; it is
recorded as a finding rather than passed over.

**The derived paths are repo-relative strings** wherever the YAML's scripts emitted them
that way, so a checkpoint survives a machine change. A node joins one onto a freshly
resolved root; only an `Await`'s context file needs an absolute `Path`, and the workflow
makes that join at the call site.
"""
from __future__ import annotations

import os
from pathlib import Path

#: Where a run's operator gates leave the file a human answers in. Repo-relative, one
#: file per gate kind, so two gates open in the same story do not overwrite each other.
OPERATOR_DIR = ".agents/operator"

#: The epic queue: an ostler-managed OKF index whose front entry is the current epic.
EPICS_INDEX = "docs/epics/index.md"

#: Where `dream` drains its proposals from, and the durable ledger it drains into.
DREAM_INBOX = "docs/.dream-improvements.inbox.json"
DREAM_LEDGER = "docs/workflow-improvements"


def epics_repo_root() -> Path:
    """`prune-epic.py`'s resolution: `agents.yml` or a `docs/epics/` **directory**.

    Not `.git`, which is the difference from `find_repo_root` and the whole point of
    keeping it separate — the epic queue lives in the docs checkout, and a bind-mounted
    docs clone has no `.git` of its own to be found by.
    """
    env_root = os.environ.get("AGENT_REPO_DIR")
    if env_root:
        return Path(env_root).resolve()
    here = Path.cwd().resolve()
    for candidate in [here, *here.parents]:
        if (candidate / "agents.yml").exists() or (candidate / "docs" / "epics").is_dir():
            return candidate
    return here


def launch_repo_root() -> Path:
    """The operator gates' resolution: prefer `cwd` when it already looks like a root.

    The upward walk only starts at `cwd.parents`, so a `cwd` that carries `docs/epics/`
    but neither `agents.yml` nor `.git` still wins — which is what a test harness relies
    on when it chdirs into a sandbox, and what `find_repo_root` would walk straight past.
    """
    env_root = os.environ.get("AGENT_REPO_DIR")
    if env_root:
        return Path(env_root).resolve()
    cwd = Path.cwd()
    if (cwd / "docs" / "epics").is_dir() or (cwd / "agents.yml").exists() or (cwd / ".git").exists():
        return cwd
    for candidate in cwd.parents:
        if (candidate / "agents.yml").exists() or (candidate / ".git").exists():
            return candidate
    return cwd


def operator_context_path(root: Path, gate: str) -> Path:
    """The absolute file an `Await` writes its questions into, for `gate`.

    Absolute because `Await` takes a real path to poll, unlike everything else here.
    """
    return root / OPERATOR_DIR / f"{gate}.md"


__all__ = [
    "DREAM_INBOX",
    "DREAM_LEDGER",
    "EPICS_INDEX",
    "OPERATOR_DIR",
    "epics_repo_root",
    "launch_repo_root",
    "operator_context_path",
]
