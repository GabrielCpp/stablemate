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

Saddlebag is not on PyPI. It runs from a checkout of the
[stablemate](https://github.com/GabrielCpp/stablemate) workspace:

```bash
make sync                              # at the workspace root
uv run --package saddlebag saddlebag --help
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
stdin, refuses to start if `VAULT_TOKEN` is set in its environment, and listens on a
unix socket created with owner-only permissions. Every other verb connects to that
socket, sends one request and reads one reply.

| | |
|---|---|
| Socket path | `$SADDLEBAG_SOCKET`, else `$XDG_RUNTIME_DIR/saddlebag.sock`, else the OS runtime dir |
| Vault address | `$VAULT_ADDR` or `--vault-addr` |
| Browser | `--cdp`, default `http://127.0.0.1:9222` |

The token is never written to a file and never placed in an environment variable,
because a process of the same user can read `/proc/<pid>/environ` and any file the
user owns. For the same reason the operator's own Vault login must not leave
`~/.vault-token` behind. `saddlebag doctor` warns when that file exists.

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
into, and a set of `key=value` tags. It holds up to two values: a `password` and a
`totp` enrolment seed. The username is metadata and may print. The two values never do.

```jsonc
{
  "name":        "normal_login",
  "username":    "gab",
  "description": "Log in as a normal user",
  "var":         "LOGIN_PASSWORD",
  "tags":        [["environment", "local"], ["role", "user"]],
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
| `serve` | run the daemon; token on stdin |
| `list` `tags` | query by tag; neither can emit a value |
| `secret create` `set` `unset` `remove` `tag` `untag` | manage a secret; `set` reads its value from stdin |
| `fill` | type a secret's username, password or current TOTP code into a browser field |
| `exec` | run a command with matching secrets in its environment |
| `doctor` | daemon reachable, Vault authenticated, secrets with no value, stray token file |

```bash
saddlebag fill NAME --field username|password|totp --selector S [--url-contains X]
saddlebag exec [--tag k=v]... [--env VAR=NAME[.field]]... -- cmd args...
```

`exec` fills each tag-matched secret's `var` with its password. An explicit
`--env VAR=NAME.field` binding may name any field, including the username and the
current TOTP code. A secret matched by tag that has no `var` is an error naming it,
not a silent skip.

**What each verb guarantees.** `fill` reports a character count, a selector and a URL.
The value is typed through `Input.insertText` and never interpolated into an evaluated
expression. A TOTP seed leaves the store only as a computed six-digit code, and only
by being typed. `exec` is as private as the command it runs: a command that prints its
own environment prints the secret. What `exec` guarantees is that the value is never
in the agent's transcript by default and never on disk. The agent's permission layer
decides which commands it may run under `exec`.

---

## The ostler stack

A repository's `docs/features/ops/stack.yml` names one secret source for its compose
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

Saddlebag implements no encryption and keeps no local database. Values and metadata
both live in Vault, under `secret/saddlebag/<name>`: the values as the secret's data,
the metadata as its custom metadata. There is no plaintext path and no fallback store.
If Vault is unreachable, the daemon does not start. The full account, including what
the socket does and does not protect against, is in
[docs/SECURITY.md](https://github.com/GabrielCpp/stablemate/blob/main/saddlebag/docs/SECURITY.md).
Driving saddlebag from a workflow node is in
[docs/INTEGRATION.md](https://github.com/GabrielCpp/stablemate/blob/main/saddlebag/docs/INTEGRATION.md).

---

## Upgrading from 1.x

Version 2.0 removes the OS keyring backend, the SQLite pool, credential leases,
AI selection, the `env` command family and the YAML manifest. Nothing is migrated.
Credentials in a 1.x pool and items in the OS keyring are left in place and orphaned.
Create each secret you still need with `secret create` and `secret set`.

---

## Package layout

```
saddlebag/
├── __init__.py
├── cli.py        # argparse thin client: build a request, send it, print the reply; `exec`
├── daemon.py     # `serve`: the accept loop and every verb, over the store and the browser
├── protocol.py   # the socket path, newline-JSON framing and the client's send()
├── vault.py      # Vault KV v2: values in the secret's data, metadata in its custom metadata
├── models.py     # Secret and tag parsing; no field of it carries a value
├── browser.py    # CDP target discovery and Input.insertText; only a length comes back
└── totp.py       # RFC 6238, computed in-process so the seed never leaves
```

## Name

A **saddlebag** is the kit a horse carries on a ride: the right tools, ready when
needed, returned to the stable when the ride is done. It fits the stablemate
vocabulary. Ostler tends the stable, farrier fits the gear, workhorse does the
riding, and saddlebag carries what the journey needs.

## Map

- `saddlebag/`: the package behind the `saddlebag` command. [Package layout](#package-layout) says what each module owns.
- `docs/`: the security model and the workflow integration.
- `tests/`: the suite, run from the repo root with `uv run --package saddlebag pytest saddlebag/tests`.
