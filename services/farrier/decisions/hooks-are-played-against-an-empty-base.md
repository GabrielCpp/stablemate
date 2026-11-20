story: none
date: 2026-11-20
elements: HooksInstall, HooksList, Checks, Sync

farrier ships its base library, so every command resolves one. The sandbox names an empty base with
`STABLEMATE_BASE_DIR`, which outranks the shipped one. That keeps the answers of `hooks install`, `hooks list`,
`checks` and `sync` free of the base's content, which changes with every release. With the empty base,
`hooks install` writes `.agents/hooks/*` with no hook in them and `hooks list` reads `(none)` at every stage.
`checks` lists the repository's own `sync` check, which starts with the absolute path of the farrier that is running,
so the declaration leaves it opaque and the claim is the exit code.

`sync` is a commit check, and a commit check only runs inside a checkout. The sandbox is no git checkout, so `sync`
skips the check there and exits 0, the same answer it gives when no library resolves. It used to end in a traceback
there instead: see DISAGREEMENTS 4.
