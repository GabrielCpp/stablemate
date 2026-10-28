# saddlebag

> Carry the right credentials for every ride.

`saddlebag` holds the secrets a QA run needs and puts each one where it is consumed, so
that an agent driving a `workhorse` workflow never holds a secret in its context. A
secret leaves the store in exactly two ways. `fill` types it into a field of a browser
over the Chrome DevTools Protocol. `exec` runs a command with it set in that command's
process environment. Neither hands the value back to whoever ran them.

One daemon holds the HashiCorp Vault token, and every other command is a thin client
over a unix socket. That is what lets the same tool serve a run on the host and a run
in a container: the container sees the socket and nothing else.

---

## Position in the ecosystem

| Tool | Job |
|---|---|
| **ostler** | Tends the knowledge graph: epics, stories, seeds, specs |
| **farrier** | Fits the shared prompt library onto each repo |
| **workhorse** | Runs the workflow graph unattended |
| **saddlebag** | Carries secrets and fills them where they are consumed |

Ostler owns the spec of what a test needs and which environment it runs against.
Saddlebag owns the secret material that satisfies it. Ostler's stack bring-up asks
saddlebag for the variables a stack needs, as described under
[The ostler stack](#the-ostler-stack).

---

## Install

Saddlebag publishes to PyPI as `stablemate-saddlebag`, because the name `saddlebag` is
unavailable. The command and the import package stay `saddlebag`.

```bash
uv tool install stablemate-saddlebag
pipx install stablemate-saddlebag
```

The `stablemate` package installs it along with the other tools (`uv tool install stablemate`).
From a checkout of the [stablemate](https://github.com/GabrielCpp/stablemate) workspace:

```bash
uv run --package stablemate-saddlebag saddlebag --help
```

Requires Python ≥ 3.12 and a reachable HashiCorp Vault with a KV v2 mount named
`secret`. For a developer machine, `vault server -dev` is enough.

---

## Sixty seconds

```bash
# 1. Start the daemon. The token arrives on stdin and stays in the daemon's memory.
export VAULT_ADDR=http://127.0.0.1:8200
printf '%s' "$VAULT_TOKEN_FROM_YOUR_LOGIN" | saddlebag serve

# 2. In another shell: describe a secret, then give it its value on stdin.
saddlebag secret create normal_login \
  --username gab \
  --description "Log in as a normal user" \
  --var LOGIN_PASSWORD \
  --tag environment=local --tag role=user
printf '%s' "$PASSWORD" | saddlebag secret set normal_login

# 3. An agent finds it by tag and reads the description. No value is printed.
saddlebag list --tag environment=local

# 4. Deliver it. Into a browser field, or into a command's environment.
saddlebag fill normal_login --field username --selector "#login_field" --url-contains example.com
saddlebag fill normal_login --field password --selector "#password"    --url-contains example.com
saddlebag exec --tag environment=local -- docker compose up
```

The browser the fourth step talks to is one you started with a debugger port:

```bash
chromium --remote-debugging-port=9222 --user-data-dir=/tmp/qa-profile
```

Saddlebag connects only to a DevTools endpoint on loopback and refuses any other
host. That port is unauthenticated and grants total control of the browser.

---

## The daemon

`saddlebag serve` is the one process that talks to Vault. It reads the token from
stdin when piped, else from the OS keyring where `saddlebag serve --keep-token` stored
it, else from `saddlebag/vault-token` under the stablemate state dir when that file is
mode 0600. It refuses to start if `VAULT_TOKEN` is set in its environment, and listens
on a unix socket created with owner-only permissions. Every other verb connects to
that socket, sends one request and reads one reply.

| | |
|---|---|
| Backend | `$SADDLEBAG_BACKEND` (`keyring` or `daemon`), else `backend` under `[saddlebag]` in the shared stablemate `config.toml`, else a daemon that answers on the socket, else the OS keyring |
| Socket path | `$SADDLEBAG_SOCKET`, else `$XDG_RUNTIME_DIR/saddlebag.sock`, else the OS runtime dir |
| Vault address | `$VAULT_ADDR` or `--vault-addr` |
| Browser | `--cdp`, default `http://127.0.0.1:9222` |

saddlebag never puts the token in an environment variable, because a process of the
same user can read `/proc/<pid>/environ`. The kept token lives in the OS keyring. The
filed token is the operator's choice, and `doctor` warns about it because any file the
user owns is readable by their other processes. For the same reason the operator's own
Vault login must not leave `~/.vault-token` behind, and `doctor` warns when that file
exists.

### A run in a container

Mount the socket and name it. The client inside the container talks to the daemon
on the host, which is also where the browser and its debug port live.

```bash
docker run \
  -v "$SADDLEBAG_SOCKET:/run/saddlebag.sock" \
  -e SADDLEBAG_SOCKET=/run/saddlebag.sock \
  ...
```

---

## Secrets and tags

A **secret** has a name, an optional username, a description an agent reads to choose
between candidates, an optional `var` naming the environment variable `exec` fills it
into, a set of `key=value` tags, and a map of printable metadata such as a phone number
or a role, given with `--meta key=value` and changed later with `secret meta` and `secret
unmeta`. It holds up to two values: a `password` and a `totp` enrolment seed. The
username and the metadata may print. The two values never do.

```jsonc
{
  "name":        "normal_login",
  "username":    "gab",
  "description": "Log in as a normal user",
  "var":         "LOGIN_PASSWORD",
  "tags":        [["environment", "local"], ["role", "user"]],
  "metadata":    {"phone": "+15555550100"},
  "fields":      ["password"]
}
```

Tags are the whole query vocabulary. `list --tag environment=local --tag role=admin`
returns the secrets carrying both pairs. `tags` lists the distinct pairs in use. The
convention the ostler integration relies on is that a secret for a QA environment
carries `environment=<ostler environment node id>`.

---

## Commands

| | |
|---|---|
| `serve` | run the daemon; token from stdin, the OS keyring or a 0600 file; `--keep-token` stores one |
| `list` `tags` | query by tag; neither can emit a value |
| `secret create` `set` `unset` `remove` `tag` `untag` `meta` `unmeta` | manage a secret; `set` reads its value from stdin; `meta K=V` adds or overwrites printable metadata, `unmeta KEY` drops it |
| `fill` | type a secret's username, password or current TOTP code into a browser field |
| `exec` | run a command with matching secrets in its environment |
| `doctor` | backend and route in use, store reachable, secrets with no value, orphan keyring items, stray token file, and on the daemon route where its token came from |

```bash
saddlebag fill NAME --field username|password|totp --selector S [--url-contains X]
saddlebag exec [--tag k=v]... [--env VAR=NAME[.field|.meta.KEY]]... -- cmd args...
```

`exec` fills each tag-matched secret's `var` with its password. An explicit
`--env VAR=NAME.field` binding may name any field, including the username, the
current TOTP code and a metadata key as `NAME.meta.KEY`. A secret matched by tag that has no `var` is an error naming it,
not a silent skip.

**What each verb guarantees.** `fill` reports a character count, a selector and a URL.
The value is typed through `Input.insertText` and never interpolated into an evaluated
expression. A TOTP seed leaves the store only as a computed six-digit code, and only
by being typed. `exec` masks what the command prints when its output goes to a pipe,
which is how an agent's tool call runs it. Saddlebag stays as the command's parent and
copies its stdout and stderr through, with each secret value replaced by `[REDACTED]`.
It masks the value as written and in the forms tools escape it into: compose's `$$`,
URL encoding and JSON string escaping. It looks for no other encoding, such as base64.
A value shorter than 8 characters is not masked, and `exec` names its variable in a
warning on stderr. A username bound with `--env` is metadata and is not masked. When
stdout and stderr are both a terminal, `exec` becomes the command and masks nothing,
so colors, `-it` and progress bars keep working for a person at the keyboard.

Masking catches the leak an agent makes by mistake, such as running
`docker compose config` under `exec`. It does not stop a command written to leak, and
it does not reach what the command writes to a file. Saddlebag itself never writes a
value to disk. The agent's permission layer decides which commands it may run under
`exec`.

---

## The ostler stack

A repository's `docs/services/ops/stack.yml` names one secret source for its compose
stack. With saddlebag as that source, ostler asks `saddlebag list` for the variable
names the matching secrets fill, checks them against the `${VAR}` references in the
rendered compose file, and runs every `docker compose` command under `saddlebag exec`.
No `stack.env` file is written.

```yaml
secrets:
  saddlebag: environment=local
```

The value is one or more space-separated tag pairs. The ostler README documents the
other two sources and the required-name check.

---

## Where secrets live

A command picks its route in this order: `SADDLEBAG_BACKEND`, then the `backend` key
of the `[saddlebag]` table in the shared stablemate `config.toml`, then a daemon that
answers on the socket, else the OS keyring in this process. A set `SADDLEBAG_SOCKET`
always means the daemon, and nothing listening there is an error, never a silent
fall-back to the keyring.

Without a daemon, values live in the OS keyring, one item per secret and field under
the service `stablemate-saddlebag`, and their metadata in `saddlebag/catalogue.json`
under the stablemate state dir, owner-only. Behind the daemon, values and metadata both
live in Vault under `secret/saddlebag/<name>`: the values as the secret's data, the
metadata as its custom metadata. Saddlebag implements no encryption and keeps no
plaintext fallback. A locked or absent keyring stops the command with a line that says
what to do, and if Vault is unreachable, the daemon does not start.

Over SSH the keyring is usually locked. Feed your login password to
`gnome-keyring-daemon --unlock` to open it, or set `SADDLEBAG_BACKEND=daemon`. On
macOS the Keychain trusts the interpreter that stored an item, so a reinstalled
interpreter prompts once per item; `doctor` prints the interpreter path, which
`security add-generic-password -T <path>` takes to pre-authorise it. The full account,
including what the socket and the keyring do and do not protect against, is in
[docs/SECURITY.md](https://github.com/GabrielCpp/stablemate/blob/main/saddlebag/docs/SECURITY.md).
Driving saddlebag from a workflow node is in
[docs/INTEGRATION.md](https://github.com/GabrielCpp/stablemate/blob/main/saddlebag/docs/INTEGRATION.md).

---

## Upgrading from 1.x

Version 2.0 removed the 1.x OS keyring backend, the SQLite pool, credential leases,
AI selection, the `env` command family and the YAML manifest. Nothing is migrated.
Credentials in a 1.x pool and 1.x keyring items under the service `saddlebag` are left
in place and orphaned; the keyring store of 2.x reads only items under
`stablemate-saddlebag`, which it wrote itself. Create each secret you still need with
`secret create` and `secret set`.

---

## Package layout

```
saddlebag/
├── __init__.py
├── cli.py        # argparse front end: build a request, route it, print the reply; `exec`
├── route.py      # how a command reaches the counter: the daemon's socket, or in-process over the keyring
├── verbs.py      # the verb handlers over one store, used in-process or behind the daemon
├── store.py      # the SecretStore contract every verb talks to, and StoreUnavailable
├── custody.py    # the Vault token's three sources and the refusal
├── daemon.py     # `serve`: the socket accept loop over the verbs
├── protocol.py   # the socket path, newline-JSON framing and the client's send()
├── vault.py      # Vault KV v2: values in the secret's data, metadata in its custom metadata
├── keyring_store.py  # the OS keyring door and the shelf: values in the keyring, records in the catalogue
├── catalogue.py  # the keyring shelf's records, in one owner-only JSON file
├── models.py     # Secret and tag parsing; no field of it carries a value
├── redact.py     # `exec` off a terminal: the child's output relayed with every secret form masked
├── browser.py    # CDP target discovery and Input.insertText; only a length comes back
└── totp.py       # RFC 6238, computed in-process so the seed never leaves
```

## Name

A **saddlebag** is the kit a horse carries on a ride: the right tools, ready when
needed, returned to the stable when the ride is done. It fits the stablemate
vocabulary. Ostler tends the stable, farrier fits the gear, workhorse does the
riding, and saddlebag carries what the journey needs.
