from __future__ import annotations

from datetime import date
from typing import Iterable

from ostler.book import Journey

from ..commands import Control, InboxRead, InboxReply, Look, Replay
from ..events import FinishARun, ParkARun
from ..fixtures import (FINISHED, MALFORMED_PARAM, MISSING, UNHELD_PARAM, UNKNOWN_PARAM, UNKNOWN_STATE,
                        UNREADABLE_TURN, control, finish, park, read_inbox, replay, reply, rewind, status)


class WrongTurns(Journey):
    """An operator steers runs and gets it wrong. They look for a run when none exists, name a run that is not there,
    rewind one that ended, rewind to a state that is not there, hand rewind a bad parameter, type a flag after a verb
    that does not take it, resume a run that never launched, and answer a message that is not in the inbox. Each time
    the checkpoint stays as it was."""

    alone = True

    def steps(self, today: date) -> Iterable[object]:
        return (
            Control(status()),
            InboxRead(read_inbox()),
            InboxReply(reply()),
            ParkARun(park()),
            FinishARun(finish()),
            Control(status(run=MISSING)),
            Control(rewind(run=FINISHED)),
            Control(control("resume", run=FINISHED)),
            Control(rewind(to=None)),
            Control(rewind(to=UNKNOWN_STATE)),
            Control(rewind(param=MALFORMED_PARAM)),
            Control(rewind(param=UNKNOWN_PARAM)),
            Control(rewind(param_from_turn=UNREADABLE_TURN)),
            Control(rewind(keep=UNHELD_PARAM)),
            Control(control("status", to="start")),
            Control(control("status", wait=True)),
            Control(control("status", name="x")),
            Control(control("resume")),
            Control(control("switch-cli")),
            Control(control("stop", core=True)),
            InboxReply(reply("m9")),
            InboxReply(reply(text=None)),
            InboxRead(read_inbox(run=MISSING)),
            Replay(replay()),
            Replay(replay(run=MISSING)),
            Look(),
        )
