from __future__ import annotations

from datetime import date
from typing import Iterable

from ostler.book import Journey

from ..books import CheckBook, DrawBook, ExplainBook, ExplainNothing, SearchUnmovedBook, MoveBook, ExploreBook, IndexBook, ListBookDecisions, ListBookPages, RunBook, SearchBook
from ..commands import Look
from ..fixtures import nothing
from ..graph import EnvAddress, EnvDown, EnvExec, EnvRender, EnvRenderUnknown


class ReadABook(Journey):
    """A reviewer opens a small book. They check it, rewrite its index, search it, explain one endpoint and a name it
    lacks, list its decisions and its book pages, walk its model, draw its state graph and run its journeys against the app."""

    alone = True

    def steps(self, today: date) -> Iterable[object]:
        return (
            CheckBook(nothing()),
            IndexBook(nothing()),
            SearchBook(nothing()),
            ExplainBook(nothing()),
            ExplainNothing(nothing()),
            SearchUnmovedBook(nothing()),
            MoveBook(nothing()),
            ListBookDecisions(nothing()),
            ListBookPages(nothing()),
            ExploreBook(nothing()),
            DrawBook(nothing()),
            RunBook(nothing()),
            EnvDown(nothing()),
            EnvAddress(nothing()),
            EnvRenderUnknown(nothing()),
            EnvRender(nothing()),
            Look(),
            EnvExec(nothing()),
            EnvDown(nothing()),
            Look(),
        )
