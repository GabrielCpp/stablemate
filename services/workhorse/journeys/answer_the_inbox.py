from __future__ import annotations

from datetime import date
from typing import Iterable

from ostler.book import Journey

from ..commands import InboxRead, InboxReply, Look
from ..events import ParkARun
from ..fixtures import park, read_inbox, reply


class AnswerTheInbox(Journey):
    """A run stopped at a gate and left two messages. The operator lists what is outstanding, lists everything, answers
    the open one, and finds nothing outstanding any more. They then answer the message that already had an answer."""

    alone = True

    def steps(self, today: date) -> Iterable[object]:
        return (
            ParkARun(park()),
            InboxRead(read_inbox()),
            InboxRead(read_inbox(all=True)),
            InboxReply(reply()),
            Look(),
            InboxRead(read_inbox()),
            InboxRead(read_inbox(all=True, run="parked")),
            InboxReply(reply("m2")),
            Look(),
        )
