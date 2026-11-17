from __future__ import annotations

from datetime import date
from typing import Iterable

from ostler.book import Journey

from .. import commands as c
from .. import fixtures as f
from ..events import ListUserLibrary, ListWhatIsWanted


class ReadTheLibrary(Journey):
    """A person reads the library the layer stack resolves: the catalog, one skill as written, a skill the library lacks, a show with no kind named, and the check of its front matter. A library that does not exist is refused. They also ask what workflows this machine has, none, the version, and the worktrees of a folder that holds no checkout."""

    alone = True

    def steps(self, today: date) -> Iterable[object]:
        return (
            c.LibraryList(f.library_list()),
            c.LibraryShow(f.library_show()),
            c.LibraryShow(f.library_show("nonesuch")),
            c.LibraryShow(f.library_show(None)),
            c.LibraryCheck(f.library_check()),
            c.LibraryList(f.library_list(library="no-such-lib")),
            c.Workflows(f.WorkflowsArgs()),
            c.WorkflowNames(f.WorkflowNamesArgs()),
            c.Worktrees(f.WorktreesArgs()),
            c.Version(f.version()),
        )
