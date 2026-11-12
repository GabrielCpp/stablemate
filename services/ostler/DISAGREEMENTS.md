# Where the source and ostler disagree

Found while writing this book from `ostler/ostler/`. Each entry names the command, what the source intends, and
what the tool does.

1. `ostler todo reorder A A`: `reorder` (`ostler/ostler/todo.py:100-108`) resolves every typed name and puts the
   list in front of the rest, without removing repeats. Naming an epic twice writes it twice into
   `art/epics/index.md`, and `todo list` then shows it twice. A queue holds an epic once, since `todo add` refuses
   a name already queued, so the source intends a reorder to keep that. The model keeps the queue as a set in
   order and the book never plays a repeated name.
