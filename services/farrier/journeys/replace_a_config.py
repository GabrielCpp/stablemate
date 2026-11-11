from __future__ import annotations

from datetime import date
from typing import Iterable

from ostler.book import Journey

from ..commands import Init, Install
from ..events import HandWriteConfig, ListWhatIsWanted
from ..fixtures import init, install


class ReplaceAConfig(Journey):
    """A person has an agents.yml they wrote by hand. init refuses to replace it. With --force it writes the starter
    in its place. They list the demo skill again and install, then force a fresh starter, which drops the
    selection, and install once more: the skill the config no longer selects is removed."""

    alone = True

    def steps(self, today: date) -> Iterable[object]:
        return (
            HandWriteConfig(),
            Init(init()),
            Init(init(force=True)),
            ListWhatIsWanted(),
            Install(install()),
            Init(init(force=True)),
            Install(install()),
        )
