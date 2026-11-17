story: none
date: 2026-11-16
elements: EnvShow, EnvKeys, EnvClassify, EnvSet, EnvImport

A dotenv line is secret when its value is a stored password or seed (held-value), its key is the variable of a
registered secret (registered-var), or its shape says so: a key named like a credential, a vendor token, a URL with a
password in it (saddlebag/saddlebag/verbs.py, verb_classify, and shapes.py). The rules are tried in that order, so the
same ACME_PW line is a literal in an empty store, secret by its variable once acme is registered, and secret by its value
once acme holds the password.

The dotenv the book gives every world is `app.env`. Its lines are the strings the watch looks for, so the file's
rows say which lines it holds. `env set` writes a literal in place or at the end, and refuses a key or a value that is
secret with exit 2 (cmd_env_set).
