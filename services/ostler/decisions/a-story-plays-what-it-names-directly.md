story: none
date: 2026-11-21
elements: RunBook
sources: ostler/ostler/book/affected.py, ostler/ostler/book/bookdiff.py

The selection of `ostler book affected` answers two questions. What the change might affect is complete and unbounded.
What a story plays is bounded by construction.

A story plays three ranks. Rank 1 is the journeys whose own class the change added or edited. Rank 2 is the calls whose
own class the change added or edited, and the calls of an edited action or screen class. Rank 3 is the calls of the
elements whose `source=` names a changed file or symbol with no hop in between, and of the elements a hunk with no
definition line widens to. A journey is never rank 3, because a journey reaches a change only through the book.

One changed helper followed by name through the call graph reaches nearly every endpoint of a book. A real story
selected 111 calls, which does not fit the 15-minute play limit of a story.

What the change reaches through a hop, or through a changed shared book definition, is counted under `reached`. That
selection belongs to the scheduled whole play, and a story never plays it.

`only`, `journeys` and `by_journey` keep their content, so the other consumers of the report do not change.

The accepted cost is that a call the change alters through a shared helper is judged only by the scheduled whole play.
