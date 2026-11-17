story: none
date: 2026-11-16
elements: EnvImport

`env import` creates and fills one secret per key in turn (saddlebag/saddlebag/cli.py, cmd_env_import). A clash on the
second key's name is refused after the first key is stored, and the first stays. The book plays a clash on the first key
and on the second, which are the cases that differ.
