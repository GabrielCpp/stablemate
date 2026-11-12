story: ostler-book
date: 2026-11-12
elements: TodoAdd, TodoPrune, TodoReorder, PathEpic

A bare slug of an epic that exists on disk (`second`) resolves to its numbered directory (`0002-second`) in
`todo add`, `todo prune`, `todo reorder` and `path epic`. A name with no folder stays as typed, and `todo add`
queues it with a warning that epic selection will skip it. The queue record therefore keeps canonical names, and
the fixtures carry a `canonical` property so a rule's message prints the name the tool prints.
