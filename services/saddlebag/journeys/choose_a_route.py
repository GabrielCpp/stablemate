from __future__ import annotations

from datetime import date
from typing import Iterable

from ostler.book import Journey

from .. import commands as c
from .. import fixtures as f
from ..events import ChooseDaemon, ChooseKeyring, LeaveVaultToken


class ChooseARoute(Journey):
    """A person's home config prefers the daemon, though none runs, and every verb that reaches the store is refused
    with where it looked. They switch the preference to the keyring and the store answers again. They leave a Vault
    token in their home and doctor warns of it."""

    alone = True

    def steps(self, today: date) -> Iterable[object]:
        return (
            c.Doctor(f.doctor()),
            ChooseDaemon(),
            c.Inventory(f.list_()),
            c.Create(f.acme()),
            c.Doctor(f.doctor()),
            ChooseKeyring(),
            c.Create(f.acme()),
            c.SetValue(f.set_value()),
            c.Doctor(f.doctor()),
            LeaveVaultToken(),
            c.Doctor(f.doctor()),
            c.Doctor(f.doctor(json=True)),
        )
