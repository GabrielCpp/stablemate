"""The lifecycle matrix of a repository: how far it has come, and what each
command does to it there."""

from __future__ import annotations

from datetime import date
from typing import Callable

from ostler.book import Axes, Scene

from ..commands import Init, Install, Look, Scaffold
from ..events import HandWriteConfig, ListWhatIsWanted
from ..fixtures import init, install, scaffold
from .state import Repo, stage

TODAY = date(2026, 11, 4)

SCENES = (
    Scene("bare", "the repository holds no agents.yml", lambda today: ()),
    Scene("hand-configured", "a person wrote agents.yml by hand", lambda today: (HandWriteConfig(),)),
    Scene("initialized", "init wrote the starter agents.yml", lambda today: (Init(init()),)),
    Scene("installed", "the starter lists the demo skill and the scaffold, and install has run",
          lambda today: (Init(init()), ListWhatIsWanted(), Install(install()))),
)

ACTIONS: dict[str, Callable[[Repo], object]] = {
    "init": lambda m: Init(init()),
    "init --force": lambda m: Init(init(force=True)),
    "init elsewhere": lambda m: Init(init(repo="no-such-dir")),
    "install": lambda m: Install(install()),
    "scaffold list": lambda m: Scaffold(scaffold(None)),
    "scaffold create": lambda m: Scaffold(scaffold()),
    "scaffold unknown": lambda m: Scaffold(scaffold("nonesuch")),
    "look": lambda m: Look(),
}

MATRICES = (Axes[Repo]("repo", TODAY, SCENES, ACTIONS, stage, state_of=lambda m, _: stage(m)),)
