story: none
date: 2026-11-16
elements: SecretRecord, Exec, SetValue

`list` and the catalogue say which of a secret's two values exist (`fields`) and never carry one
(saddlebag/saddlebag/models.py, Secret.to_dict). The only command that hands a value to a process is `exec`, so the
book keeps each stored password and seed on the record and judges them by what `exec` prints.

A stored value of eight characters or more is replaced by [REDACTED] in the command's output, and a shorter one is
printed as stored, with a warning on stderr that the book does not compare (saddlebag/saddlebag/cli.py, cmd_exec,
and redact.py). The username and a metadata value are plain text and never masked.
