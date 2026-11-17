"""The lifecycle matrix of a repository: how far it has come, and what each
command does to it there."""

from __future__ import annotations

from datetime import date
from typing import Callable

from ostler.book import Axes, Scene

from .. import commands as c
from ..commands import Init, Install, Look, Scaffold
from ..events import HandWriteConfig, ListUserLibrary, ListWhatIsWanted
from .. import fixtures as f
from ..fixtures import init, install, scaffold
from .state import Repo, stage

TODAY = date(2026, 11, 4)

SCENES = (
    Scene("bare", "the repository holds no agents.yml", lambda today: ()),
    Scene("user-library", "the home config lists a user library and the repository holds no agents.yml",
          lambda today: (ListUserLibrary(),)),
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
    "version": lambda m: c.Version(f.version()),
    "doctor": lambda m: c.Doctor(f.doctor()),
    "doctor elsewhere": lambda m: c.Doctor(f.doctor(repo="no-such-dir")),
    "config show": lambda m: c.ConfigShow(f.config_show()),
    "config show a key": lambda m: c.ConfigShow(f.config_show("default_cli")),
    "config show unset": lambda m: c.ConfigShow(f.config_show("stablemate_dir")),
    "config get": lambda m: c.ConfigGet(f.config_get()),
    "config get unset": lambda m: c.ConfigGet(f.config_get("library_dir")),
    "config get unknown": lambda m: c.ConfigGet(f.config_get("nonesuch")),
    "config set": lambda m: c.ConfigSet(f.config_set()),
    "config set no equals": lambda m: c.ConfigSet(f.config_set("bogus")),
    "config set unknown": lambda m: c.ConfigSet(f.config_set("bogus=1")),
    "config reference": lambda m: c.ConfigReference(f.config_reference()),
    "config reference unknown": lambda m: c.ConfigReference(f.config_reference("nonesuch")),
    "set-worktree": lambda m: c.ConfigSetWorktree(f.set_worktree()),
    "set-stablemate": lambda m: c.ConfigSetStablemate(f.set_stablemate()),
    "set-library": lambda m: c.ConfigSetLibrary(f.set_library()),
    "set-library unusable": lambda m: c.ConfigSetLibrary(f.set_library("nolib")),
    "set-base": lambda m: c.ConfigSetBase(f.set_base()),
    "set-base unusable": lambda m: c.ConfigSetBase(f.set_base("nolib")),
    "library list": lambda m: c.LibraryList(f.library_list()),
    "library show": lambda m: c.LibraryShow(f.library_show()),
    "library show unknown": lambda m: c.LibraryShow(f.library_show("nonesuch")),
    "library show none": lambda m: c.LibraryShow(f.library_show(None)),
    "library check": lambda m: c.LibraryCheck(f.library_check()),
    "source generated": lambda m: c.Source(f.source()),
    "source hand-written": lambda m: c.Source(f.source("agents.yml")),
    "source missing": lambda m: c.Source(f.source("nonesuch")),
    "eject": lambda m: c.Eject(f.eject()),
    "eject other": lambda m: c.Eject(f.eject("demo")),
    "hooks list": lambda m: c.HooksList(f.hooks_list()),
    "hooks list elsewhere": lambda m: c.HooksList(f.hooks_list(repo="no-such-dir")),
    "hooks install": lambda m: c.HooksInstall(f.hooks_install()),
    "hooks install dry run": lambda m: c.HooksInstall(f.hooks_install(dry_run=True)),
    "checks": lambda m: c.Checks(f.ChecksArgs()),
    "sync": lambda m: c.Sync(f.SyncArgs()),
    "install user": lambda m: c.InstallUser(f.install_user()),
    "workflows": lambda m: c.Workflows(f.WorkflowsArgs()),
    "workflow names": lambda m: c.WorkflowNames(f.WorkflowNamesArgs()),
    "worktrees": lambda m: c.Worktrees(f.WorktreesArgs()),
    "look": lambda m: Look(),
}

MATRICES = (Axes[Repo]("repo", TODAY, SCENES, ACTIONS, stage, state_of=lambda m, _: stage(m)),)
