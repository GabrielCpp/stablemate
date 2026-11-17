story: none
date: 2026-11-16
elements: HooksInstall, HooksList, Checks, Sync

The book plays `hooks install`, `hooks list`, `checks` and `sync` in a sandbox whose home config names no library.
That is the only state in which their answers do not depend on the machine: with a library, `hooks install` also
writes `.agents/hooks/*` and `checks` lists the commit checks of the skills the library selects, each starting with
the absolute path of the farrier that is running. The one `checks` line the book can state, the repository's own
`sync` check, starts with that path, so the declaration leaves it opaque and the claim is the exit code.

`hooks list` is played once more after `config set-library`, where the library holds no skill that declares a hook
and every stage reads `(none)`. `sync` is not played there: see DISAGREEMENTS 4.
