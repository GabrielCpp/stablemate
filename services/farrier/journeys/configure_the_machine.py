from __future__ import annotations

from datetime import date
from typing import Iterable

from ostler.book import Journey

from .. import commands as c
from .. import fixtures as f
from ..events import ListUserLibrary, ListWhatIsWanted


class ConfigureTheMachine(Journey):
    """A person reads the home config, which sets nothing but its version, and asks for a key it defaults. They set the default CLI, read it back from the file, and are refused a name with no equals sign, a key the config does not have and a key nothing sets. They read the reference for a key, record the worktree, stablemate and base directories, are refused a directory that holds no library, and record the library. The listing then shows every key in the order the schema gives."""

    alone = True

    def steps(self, today: date) -> Iterable[object]:
        return (
            c.ConfigShow(f.config_show()),
            c.ConfigGet(f.config_get()),
            c.ConfigSet(f.config_set()),
            c.ConfigGet(f.config_get()),
            c.ConfigShow(f.config_show("default_cli")),
            c.ConfigSet(f.config_set("bogus")),
            c.ConfigSet(f.config_set("bogus=1")),
            c.ConfigGet(f.config_get("nonesuch")),
            c.ConfigGet(f.config_get("library_dir")),
            c.ConfigShow(f.config_show("stablemate_dir")),
            c.ConfigReference(f.config_reference()),
            c.ConfigReference(f.config_reference("nonesuch")),
            c.ConfigSetWorktree(f.set_worktree()),
            c.ConfigSetStablemate(f.set_stablemate()),
            c.ConfigSetBase(f.set_base("nolib")),
            c.ConfigSetBase(f.set_base()),
            c.ConfigSetLibrary(f.set_library("nolib")),
            c.ConfigSetLibrary(f.set_library()),
            c.ConfigShow(f.config_show()),
            c.ConfigGet(f.config_get("library_dir")),
            c.Look(),
        )
