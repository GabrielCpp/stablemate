story: none
date: 2026-11-18
elements: PathEpic, LayoutApply
sources: 136ae7630, ostler/ostler/layout.py::check, ostler/ostler/layout.py::apply

A shelf that still holds an epic folder named `NNNN-slug` with an epic.md in it makes every command that reads the plan
refuse. The command prints `error: the epics shelf <shelf> still names <n> epic folder(s) by number and slug (<names>)`,
says that folders are named by their ids now and names `ostler layout apply`, on standard error, and exits 1. A command
that read the numbered folder would build its paths and milestone lines from a name that goes stale, so
ostler reads nothing until the shelf is renamed. An empty numbered folder, or one with no epic.md, is not a reason to
refuse.

`ostler layout apply` does not read the plan, so the refusal does not stop it. It records `slug:` under the `id:` of each
epic.md that names no slug, taking the slug from the old folder name, renames each story folder and then the epic folder
to its id. It prints one line for each, and
`every epic and story folder is already named by its id` when nothing moved.

The book reaches a numbered shelf through `CopyInAnOldEpic`, a person copying in one epic from an old shelf. Every
command shares the refusal, so the book plays it on `path epic` alone. The refusal names the one folder the book copies
in, as a rule's message is a template over the request and cannot count the shelf. The book does not play an epic or a
story with no `id:` or a rename onto a folder that exists, which apply refuses on standard error with exit 1.
