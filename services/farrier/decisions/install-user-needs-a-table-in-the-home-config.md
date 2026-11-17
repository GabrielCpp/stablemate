story: none
date: 2026-11-16
elements: InstallUser, ListUserLibrary

`farrier install --user` renders what the `[user_library.<harness>]` tables of the home config select into the
harness homes, and refuses when the config has none (`farrier/farrier/user_library.py::user_library_tables`,
`farrier/farrier/cli.py::_run_user_install`). `farrier init` only proposes the table, so a person writes it by hand,
and the book names that act an outside event. The table the book writes selects the demo skill, which the library
renders to `<home>/.claude/skills/demo/SKILL.md` with the same generated-by marks as a repository install. A home
other than the one the sandbox holds writes where the watch does not look, so the model changes no watched file for it.
