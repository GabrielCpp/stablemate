from __future__ import annotations

from datetime import date
from typing import Iterable

from ostler.book import Journey

from .. import commands as c
from .. import fixtures as f


class KeepALogin(Journey):
    """A person registers the acme login with its username, variable, tags and metadata, stores its password,
    reads the inventory, tags and untags it, adds and drops metadata, clears the password and removes the login."""

    alone = True

    def steps(self, today: date) -> Iterable[object]:
        return (
            c.Create(f.acme()),
            c.SetValue(f.set_value()),
            c.Inventory(f.list_()),
            c.Inventory(f.list_(json=True)),
            c.Tags(f.tags()),
            c.TagSecret(f.tag()),
            c.UntagSecret(f.untag()),
            c.Meta(f.meta()),
            c.Unmeta(f.unmeta()),
            c.Unset(f.unset()),
            c.Remove(f.remove()),
            c.Look(f.look()),
        )
