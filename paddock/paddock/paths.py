"""Where paddock reads its data and where it keeps the bytes.

Two roots, deliberately apart:

* the **data root** — `paddock/data/` in this repo — is tracked and small: task modules,
  config TOMLs, pointer TOMLs, and the reference material a score function reads.
* the **store** is untracked and large: the seed and result zips themselves, plus the
  work directory a run stages into.

The split is not tidiness. `scripts/check_public.py` scans a binary file by path only
(a NUL byte in the first 8 kB stops the content scan), so a tracked zip ships its
contents past the guard that exists to stop exactly that. The pointer is what travels
in git; the zip travels beside it, verified by sha256.
"""

from __future__ import annotations

from pathlib import Path

#: The tracked data directory this repo keeps its tasks in, relative to the repo root.
#: Beside the package rather than inside it: `[tool.hatch.build]` names the inner
#: `paddock` directory, so a sibling `data/` ships in no wheel and no sdist — which is
#: what keeps a hundred-odd fixture files out of every install of the tool.
DATA_DIRNAME = "paddock/data"

#: Off `/tmp`, which does not survive a reboot. A fixture that evaporates is not a
#: fixture — the same reason the retired replay harness kept its bundles here.
STORE = Path.home() / ".local" / "share" / "stablemate" / "paddock"


def repo_root(start: Path | None = None) -> Path:
    """The nearest ancestor of *start* holding a `.git`, or *start* itself if none does.

    Tolerant rather than fatal: paddock is usable against a data directory named
    explicitly with `--data-dir`, and only the *default* needs a repo to hang off.
    """
    here = (start or Path.cwd()).resolve()
    for candidate in (here, *here.parents):
        if (candidate / ".git").exists():
            return candidate
    return here


def default_data_dir(start: Path | None = None) -> Path:
    return repo_root(start) / DATA_DIRNAME


def seed_zip(store: Path, name: str) -> Path:
    return store / "seeds" / f"{name}.zip"


def result_zip(store: Path, task: str, label: str) -> Path:
    return store / "results" / task / f"{label}.zip"


def work_dir(store: Path, task: str, label: str) -> Path:
    return store / "work" / task / label


def seed_pointer(data_dir: Path, name: str) -> Path:
    return data_dir / "seeds" / f"{name}.toml"


def result_pointer(data_dir: Path, task: str, label: str) -> Path:
    return data_dir / "results" / task / f"{label}.toml"


def tasks_dir(data_dir: Path) -> Path:
    return data_dir / "tasks"
