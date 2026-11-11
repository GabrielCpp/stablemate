"""Why farrier says no. The message is the one it prints, word for word, with
the sandbox written `<sandbox>`. A rule reads the request (`a`) and the
repository (`s`)."""

from __future__ import annotations

from ostler.book import Actor, Exited, Rule

from ..fixtures import LIBRARY, SCAFFOLD, InitArgs, InstallArgs, ScaffoldArgs
from .state import Repo

FAILED = Exited(1)


def _no_directory(a: InitArgs, s: Repo, by: Actor | None) -> bool:
    return not a.here


def _already_configured(a: InitArgs, s: Repo, by: Actor | None) -> bool:
    return "agents.yml" in s.files and not a.force


def _no_library(a: InstallArgs | ScaffoldArgs, s: Repo, by: Actor | None) -> bool:
    return a.library != LIBRARY


def _no_config(a: InstallArgs, s: Repo, by: Actor | None) -> bool:
    return not a.here or "agents.yml" not in s.files


def _unknown_scaffold(a: ScaffoldArgs, s: Repo, by: Actor | None) -> bool:
    return a.name is not None and a.name != SCAFFOLD


def enabled(a: ScaffoldArgs, s: Repo) -> bool:
    """Whether the repository lists the scaffold: it has no agents.yml to refuse it, or the file names it."""
    config = s.files.get("agents.yml") if a.here else None
    return config is None or "- service-gitignore" in config.holds


def _not_enabled(a: ScaffoldArgs, s: Repo, by: Actor | None) -> bool:
    return a.name is not None and not enabled(a, s)


not_a_directory = Rule[InitArgs, Repo]("error: <sandbox>/{repo} is not a directory", _no_directory, FAILED)
already_configured = Rule[InitArgs, Repo](
    "error: <sandbox>/agents.yml already exists — this repo is configured; run `farrier install --repo {typed}` to render it, "
    "or `farrier init --force` to replace the config with a fresh default", _already_configured, FAILED,
    why="init is the one command that runs before a repo is configured, so it never replaces a config unasked.")
no_library_to_install = Rule[InstallArgs, Repo](
    "error: <sandbox>/{library} (from --library) is not a usable library directory — it must contain library/.",
    _no_library, FAILED)
missing_config = Rule[InstallArgs, Repo](
    "Missing config: <sandbox>/{at}agents.yml\n"
    "Run `farrier init` to write a starter agents.yml, then list the packs to install under `packs:`.", _no_config, FAILED)
no_library_to_scaffold = Rule[ScaffoldArgs, Repo](
    "error: <sandbox>/{library} (from --library) is not a usable library directory — it must contain library/.",
    _no_library, FAILED)
unknown_scaffold = Rule[ScaffoldArgs, Repo]("Unknown scaffold: '{name}'. Library defines: service-gitignore", _unknown_scaffold, FAILED)
not_enabled = Rule[ScaffoldArgs, Repo](
    "Scaffold '{name}' is not enabled for this repo — add it to the `scaffolds:` list in <sandbox>/{at}agents.yml "
    "(or select a pack that provides it).", _not_enabled, FAILED)
