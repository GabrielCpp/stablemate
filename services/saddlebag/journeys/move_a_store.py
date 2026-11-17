from __future__ import annotations

from datetime import date
from typing import Iterable

from ostler.book import Journey

from .. import commands as c
from .. import fixtures as f


class MoveAStore(Journey):
    """A person loads an export from another machine into the store and is refused a file that is missing, is not
    JSON or is no export. The second load is refused because its secret is already there, and succeeds with --replace.
    Export is refused for a name that does not end in .saddlebag.json, and from any command run without a terminal."""

    alone = True

    def steps(self, today: date) -> Iterable[object]:
        return (
            c.Import(f.import_("missing.json")),
            c.Import(f.import_("broken.saddlebag.json")),
            c.Import(f.import_("foreign.json")),
            c.Import(f.import_()),
            c.Inventory(f.list_()),
            c.Import(f.import_()),
            c.Meta(f.meta("imported")),
            c.Import(f.import_(replace=True, json=True)),
            c.Inventory(f.list_(json=True)),
            c.Export(f.export("out.json")),
            c.Export(f.export()),
        )
