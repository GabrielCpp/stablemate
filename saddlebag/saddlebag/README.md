# saddlebag

The package behind the `saddlebag` command. A daemon holds the Vault token and answers verbs on a unix socket. The command line is a thin client of that socket. Each secret reaches its consumer without being returned to the caller.

## Map

- `browser.py`: the `fill` delivery path. It finds a page over the Chrome DevTools Protocol on loopback and types a value into it.
- `cli.py`: the argparse entry point. Every verb builds a request and prints the reply, except `serve`, which runs the daemon, and `exec`, which replaces itself with the command.
- `daemon.py`: the socket listener and the verb handlers. It answers one connection at a time and never logs a value.
- `models.py`: the secret record, tag parsing and name validation. A secret names which values exist and never holds one.
- `protocol.py`: the socket path, the newline-terminated JSON framing and the client `send`.
- `totp.py`: RFC 6238 codes computed in-process, so a seed never leaves.
- `vault.py`: the `SecretStore` protocol and the Vault KV v2 adapter. It is the only place a stored value is kept.
