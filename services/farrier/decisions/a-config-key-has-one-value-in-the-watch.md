story: none
date: 2026-11-16
elements: ConfigShow, ConfigGet, ConfigSet, ConfigSetWorktree, ConfigSetStablemate, ConfigSetLibrary, ConfigSetBase, FileRecord

The watch marks each key of the home config by its name and never by its value: `worktree_dir = "` says the key is
set. The book gives every directory key one value, the folder the sandbox holds for it (`lib`, `st`, `wt`), so the
model prints that value in `config show` and `config get` without holding it in the row. A directory that does not
exist is refused only for the library and the base, as `farrier/farrier/cli.py::_dispatch_config` checks. The value
of `default_cli` is held only when it is `codex`, the one the book sets. `config set` keeps any other value
verbatim, which the model echoes and does not hold.

`config show` lists the keys in the order of the schema, whatever order the file holds them in, with the
`[user_library.*]` table last, as a Python dictionary.
