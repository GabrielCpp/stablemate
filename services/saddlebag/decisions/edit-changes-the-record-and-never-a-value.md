story: none
date: 2026-11-24
elements: Edit

`secret edit` changes the username, the description or the variable of a secret that exists, and keeps its tags,
metadata and stored values (saddlebag/saddlebag/verbs.py, verb_edit). A flag left out keeps its field. An empty value
clears the field, so `--var ""` takes a secret out of `exec --tag`. The name stays fixed because the stores key the
values by it. With no flag given the command line refuses with exit 2 before any request is made (cmd_edit). A variable
that is not a valid name is refused like `create` refuses it.
