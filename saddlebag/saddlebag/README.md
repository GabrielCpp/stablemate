# saddlebag

The package behind the `saddlebag` command. A daemon holds the Vault token and answers verbs on a unix socket. The command line is a thin client of that socket. Each secret reaches its consumer without being returned to the caller.
