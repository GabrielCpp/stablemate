story: none
date: 2026-11-21
elements: RunBook
sources: ostler/ostler/book/affected.py, ostler/ostler/book/change.py, ostler/ostler/book/sources.py

`ostler book affected --story <id>` reads the change of one story as its own commits and the uncommitted work, not as
the range from a base commit to the working tree. A commit is the story's when its `Story:` trailer names the id. A
message that only mentions the id in its body is not the story's.

The range made every plan `whole` on trunk. Commits of other work landed between the story's, their symbols were named
by no element, and the exit code 1 of the uncovered list stopped the plays before any service played. Reading only the
story's commits drops that foreign work.

Each file is compared from the parent of the first story commit that touched it to the last story commit that touched
it. The uncommitted and untracked work is read as well, because the seat's new journeys are uncommitted when the
selection runs: a file dirty in the working tree is compared to the working tree from the same start, and a file that is
only dirty is compared from HEAD.

The accepted risk is the span. A foreign commit that edits a file between two story commits that touch the same file
shows its hunks in that file's span, because the span runs from before the first story commit to after the last. The
selection then names a few symbols more than the story wrote. It never names fewer.

With no commit carrying the trailer the command exits 2 and writes no report. It does not fall back to the range,
because the range is what made the selection wrong. The coder reads the commits first and passes `--story` only when
some commit carries the trailer, and otherwise reads the range as before.

The plan keeps the kind `whole` when a fallback applies, and the report adds an `owed` list of the fallback reasons
instead of a new kind. Under `whole`, `only` and `by_journey` are already the selection the walk names, since a record hit and a
fallback add no call. A caller that plays what the selection names and owes the rest reads `owed`. The kinds `none`,
`empty`, `partial` and `whole` and the `reason` field stay as they were, so the coder's merge of kinds and the okf book
workflows that key on `whole` are unchanged.

The book of ostler does not play `affected`. The command reads a git checkout, and the demo world of the book is not
one. A later story can add a separate git world and an element for it.

`stale --story` and `verified --story` read the same commits, committed work only, because `verified` writes HEAD.
`verified --story` refuses only for the story's code, and writes no stamp while other commits leave code unnamed. A stamp
over foreign code with no pointer would hide it from every later reading that starts at the verified commit.
