# Security model: where secrets live, and what cannot leak

This is the account to read before trusting saddlebag with a real credential, or before
adding a verb that touches one. The
[README](https://github.com/GabrielCpp/stablemate/blob/main/saddlebag/README.md)
summarises it in a paragraph.

## The threat

The process saddlebag defends against is an AI agent running as the same user, on the
same machine or in a container the user started. The agent reads every command's
output into its context, and that context is logged, summarised and sometimes sent to
a model provider. The goal is that a secret value never appears there by default, and
that every path by which it could is a command the user's permission layer can see
and deny.

The threat is not a hostile root, another user, or a compromised Vault. A process
running as the same user with the will to do so can read any file the user owns and
`/proc/<pid>/environ` of any process the user runs. Saddlebag's job is to leave
nothing there to read.

## Where secrets live

Saddlebag implements no encryption and keeps no database. Everything lives in one
HashiCorp Vault KV v2 mount, under `secret/saddlebag/<name>`:

| Where | What |
|---|---|
| The secret's data | the `password` and the `totp` seed |
| The secret's custom metadata | `username`, `description`, `var`, `tags` |

`list`, `tags` and `doctor` read metadata only, which is why they cannot emit a
value. `fill` and `exec` are the two readers that use one, and each hands it to a
consumer rather than to the caller.

## The daemon holds the token

Only `saddlebag serve` talks to Vault. Everything else is a client over a unix socket.

- The token arrives on stdin and is held in the daemon's memory. It is never written
  to a file and never placed in an environment variable. `serve` refuses to start when
  `VAULT_TOKEN` is set, because that variable is readable from `/proc`.
- The socket is created with owner-only permissions. It is a boundary against other
  users, not against the agent, which runs as the owner.
- `vault login` writes `~/.vault-token`, owned by the same user. A daemon that guards
  its token carefully next to that file guards nothing. Saddlebag never reads the Vault
  token helper, and `doctor` reports the file when it exists. The operator's own Vault
  use on the machine must not leave it behind.
- A run in a container gets the socket bind-mounted and nothing else. It never holds
  a token and never sees the browser's debug port.

The stronger variant, running the daemon under a second user and chowning the socket,
is possible and not done. The stdin-and-memory daemon already removes the token from
everything a same-user process can read without a debugger.

## The guarantees, by verb

- **No verb returns a stored value to its caller, with one exception described below.**
  `set` reports a character count. `list` and `tags` print metadata. There is no
  lookup verb and no flag that adds one.
- **A value is entered on stdin only.** `secret set` reads it there. A value on argv
  would land in the process table and the shell history.
- **`fill` moves a value into a browser, not back to its caller.** It types through
  `Input.insertText` and reports a character count, a selector and a URL. The value is
  never interpolated into an evaluated expression, so it does not reach the browser's
  protocol log either. Both the DevTools endpoint and the websocket URL it returns
  must be on loopback. That port is unauthenticated, and a non-local one is a password
  sent to whoever answers.
- **A TOTP seed leaves the store only as a computed code**, and only by being typed or
  bound into a command's environment. The seed itself is never filled anywhere.
- **`exec` is the one path that carries values out, and it carries them to a child
  process.** The client asks the daemon for the bound values, places them in the
  environment of the command it then becomes, and never prints them. A command that
  prints its own environment prints the secret. What `exec` guarantees is that the
  value is not in the transcript unless the command puts it there, and is never on
  disk. Which commands an agent may run under `exec` is the permission layer's
  decision, and the command line is visible to it in full.
- **The daemon logs no value.** Its log carries verbs, names, selectors and counts.
- **There is no plaintext path.** If Vault is unreachable or the token is not
  authenticated, the daemon does not start. Nothing degrades.

## What this does not protect

A same-user process that connects to the socket and sends the request `exec` sends
receives the same values. The socket protocol is not a secret, and the agent is the
owner of the socket. The protection is that the only tool which does so is
`saddlebag exec`, invoked with a command line the permission layer sees. An agent
that writes its own client has crossed a line that no local design closes.
