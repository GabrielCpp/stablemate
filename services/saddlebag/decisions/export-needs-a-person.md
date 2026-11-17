story: none
date: 2026-11-16
elements: Export

`saddlebag export` writes every secret in plaintext, so it asks a person at a terminal to confirm (saddlebag/saddlebag/
cli.py, cmd_export). The book runs every command with no terminal, so it plays the two refusals that come before the
question: a name without the .saddlebag.json suffix, and a missing terminal. The file and the confirmation stay unplayed.
