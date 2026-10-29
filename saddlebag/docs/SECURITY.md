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

Saddlebag implements no encryption and keeps no database of values. A secret lives in
one of two stores, chosen per command as the README describes:

| Store | Values | Metadata |
|---|---|---|
| the OS keyring, in this process | one keyring item per secret and field, under the service `stablemate-saddlebag` | `saddlebag/catalogue.json` under the stablemate state dir, owner-only, replaced atomically |
| Vault, behind `saddlebag serve` | the secret's data under `secret/saddlebag/<name>` | the same secret's custom metadata |

The catalogue holds names, usernames, descriptions, vars, tags and which fields hold a
value. It never holds a value, so `list` and `tags` cannot emit one. `fill` and `exec`
are the two readers that use a value, and each hands it to a consumer rather than to
the caller. `doctor` reads values without delivering them, to tell a catalogue entry
from a keyring item deleted behind it, and discards each one at once. The `classify` and
`holds` requests behind `env` and the guard read values the same way, to compare them
against text, and answer with a verdict or a name.

A repository's non-secret configuration is not saddlebag's to hold. It lives on the
ostler `environment` page under `variables:`, where `NAME: secret` marks the one kind of
value the page may not carry. `ostler env exec` is the one place the two meet: it reads
the page's literals itself and delegates the held names to `saddlebag exec --env`, so no
file and no process other than the consumer ever holds both halves. `ostler env dotenv`
renders the page as a file with every held name blank, and `ostler doctor` fails the page
when a literal matches a secret rule.

## The OS keyring

The keyring store accepts two backends of the `keyring` library, by name: the Secret
Service (gnome-keyring, KDE Wallet) and the macOS Keychain. Any other backend,
including the plaintext ones in `keyrings.alt`, is refused as "no OS keyring on this
session". Nothing degrades to a file.

The keyring protects against the same things the socket protects against: another
user, and a read of the disk. It does not protect against a process of the same user
in an unlocked session. That is the threat model above, so the keyring store is a peer
of the Vault store, not a lesser one.

- A locked keyring stops every verb with one line that says what the operator does:
  answer the prompt on a desktop, or over SSH feed their login password to
  `gnome-keyring-daemon --unlock`. Saddlebag never asks for that password and never
  unlocks a keyring itself.
- With no Secret Service on the session bus and no Keychain, every verb stops with the
  "absent" line. The way out is a desktop session, or a daemon.
- The macOS Keychain trusts the application that created an item. For saddlebag that
  is the Python interpreter of its install, so the same interpreter reads its items
  with no prompt. A reinstalled interpreter prompts once per item, and "Always Allow"
  or `security add-generic-password -T <interpreter>` extends the trust to it.
  `doctor` prints the interpreter path on macOS for that purpose.

## The daemon holds the token

Only `saddlebag serve` talks to Vault. Everything else is a client over a unix socket.

- The token arrives on stdin, or `serve` reads the one the operator kept in the OS
  keyring with `serve --keep-token`, or a file `saddlebag/vault-token` under the
  stablemate state dir that is mode 0600. It is held in the daemon's memory and never
  placed in an environment variable. `serve` refuses to start when `VAULT_TOKEN` is
  set, because that variable is readable from `/proc`. The kept token is one more
  keyring item, under its own service name, with the keyring's protections above. The
  filed token is the operator's choice for a machine with no keyring, and `doctor`
  names it with a warning, because a file the user owns is readable by their other
  processes.
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
  child's environment, and never prints them. When its output is a pipe, as in an
  agent's tool call, the client stays as the child's parent and relays its stdout and
  stderr with every secret value masked: as written, `$`-doubled the way compose
  escapes it, URL-encoded, and JSON-escaped. A value under 8 characters is left
  unmasked with a warning that names its variable, because a short string matches
  ordinary output. When stdout and stderr are both a terminal, the client becomes the
  child and masks nothing. Masking is a guard against a mistake, such as
  `docker compose config`, not against a command built to leak: any other encoding,
  a value split by the command itself, or a value written to a file goes through.
  Which commands an agent may run under `exec` is the permission layer's decision,
  and the command line is visible to it in full.
- **`env show`, `keys` and `classify` read a dotenv and print no secret value.** The
  client sends the file's key and value pairs to the store's `classify` request, which
  marks a pair secret when the store holds its value, when the value is a URL with
  `user:password@`, when it has a vendor token's or a PEM block's shape, or when the key's
  name says so. `show` prints the secret lines with `[REDACTED]` for the value, `keys` and
  `classify` print keys, rules and verdicts. A literal the rules miss prints as written;
  the rules are name-first so that a secret under a telling name never depends on its
  shape.
- **`env import` reads values from a file and writes them to the store.** It prints the
  record names it created and never a value, and it stops before any write when a
  requested key is absent or empty.
- **The guard refuses before a value is read.** `guard --hook` sees a tool call's
  arguments, not its output, and denies the ones whose output would be a secret: a read
  of a secret-bearing file, a dump of the environment, a secret manager's read, or a
  command whose text already carries a value the store holds. For the last it sends the
  command text to the store's `holds` request and gets back the record names, never a
  value. The daemon compares against every stored value's forms in memory and answers
  with names only. A denial carries the saddlebag line that gets the same job done. On a
  machine with no daemon, that one check is skipped with a note on stderr, because a
  keyring read for every tool call would prompt the operator.
- **The daemon logs no value.** Its log carries verbs, names, selectors and counts.
- **There is no plaintext path.** If Vault is unreachable or the token is not
  authenticated, the daemon does not start. A locked or absent keyring stops the
  command. Neither store falls back to the other on its own: `SADDLEBAG_BACKEND=daemon`
  or a set `SADDLEBAG_SOCKET` with no daemon answering is an error, and only an unset
  route lets a command take the keyring when no daemon answers.

## What this does not protect

A same-user process that connects to the socket and sends the request `exec` sends
receives the same values. The socket protocol is not a secret, and the agent is the
owner of the socket. The protection is that the only tool which does so is
`saddlebag exec`, invoked with a command line the permission layer sees. An agent
that writes its own client has crossed a line that no local design closes.

The keyring draws the same line. A same-user process in the unlocked session can ask
the Secret Service for any item under the service name, and on macOS an interpreter
the Keychain trusts reads them without a prompt. The tool that does so by design is
`saddlebag`, invoked with a command line the permission layer sees.

The guard is a redirect for the accidental read, not an access control. It knows the
file names, the readers, the environment dumpers and the manager reads listed in the
README, and a command it cannot parse, a reader it does not know, an interpreter given a
script file, or a tool outside Read, Grep, Write, Edit and Bash goes through. A pasted
value is caught only when a daemon answers and the value is at least 8 characters, the
same floor `exec` masks at. Nothing it denies was ever a boundary: the agent that wants
the value can rename the file or write a loop. What the guard changes is the default,
so that the ordinary move of reading `.env` to see a port lands on `saddlebag env show`
and leaves the password out of the transcript.
