---
name: saddlebag
description: "saddlebag: the Vault-backed daemon that hands a secret to its consumer (a browser field over CDP, or a command's environment) so the agent never holds the value. Covers finding a secret by tag, signing in with `fill` (username, password, TOTP), running a command or a compose stack under `exec`, the `secrets: saddlebag:` source in an ostler stack.yml, a workflow node that wraps a command, a run in a container, registering a secret, and reading its errors. Load when a QA run or an agent turn must sign in to a page, when a command needs a password or token in its environment, when a stack.yml names saddlebag, or when a saddlebag command fails."
tags: [cli, tests, qa]
---

# Operating saddlebag

saddlebag holds the secrets a run needs and delivers each one to the place that consumes
it. The value goes into a browser field or into a child process's environment. It never
comes back to the caller, so it never reaches your transcript. Every move below keeps it
that way: **the value travels to its consumer, and you handle names, tags and
descriptions.**

`saddlebag --help` and `saddlebag <verb> --help` are the flag reference. This skill
covers what `--help` cannot tell you: which verb fits the job, the conventions the tags
follow, and what each error asks of you.

## The daemon is the operator's

One process, `saddlebag serve`, holds the Vault token and talks to Vault. Every other
verb is a client of it over a unix socket. The operator starts it in their own terminal
and pipes the token in on stdin:

```bash
export VAULT_ADDR=http://127.0.0.1:8200
printf '%s' "$TOKEN" | saddlebag serve
```

The token is the operator's to type. When a verb reports `no saddlebag daemon on
<path>: start one with saddlebag serve`, ask the operator to start it, then run
`saddlebag doctor`. Keep your hands off the token and anything that holds it:
`VAULT_TOKEN`, `~/.vault-token`, the socket protocol. `serve` refuses to start with
`VAULT_TOKEN` set, and `doctor` warns when `~/.vault-token` exists, because any process
of this user can read either one.

`saddlebag doctor` is the health check. It exits 0 when Vault is authenticated and
every secret has a stored value. Otherwise it exits 1 and names what is missing.

## Find the secret by its tags

Tags are `key=value` pairs, and they are the whole query vocabulary. Two conventions
carry meaning across tools:

- `environment=<id>` names the environment a secret belongs to. In a repo with an ostler
  book, the id is the `environment` node's id, so a stack and its runbook find the same
  secrets.
- `role=<name>` separates the identities within one environment (`role=admin`,
  `role=user`).

```bash
saddlebag tags                                        # every pair in use
saddlebag list --tag environment=staging --tag role=admin
saddlebag list --tag environment=staging --json       # name, username, description, var, tags, fields
```

`list` matches secrets that carry **every** tag you pass. Choose between candidates by
their `description`, which exists for exactly this. The username is metadata and may
print. `fields` says which values are stored (`password`, `totp`), never what they are.

## Sign in to a page: `fill`

`fill` types one value into one field of a page in a browser that exposes a DevTools
port on loopback. The browser must be one you can also drive, so you can click the
submit button afterwards. Either start it with a debug port and connect your browser
tooling to that endpoint over CDP, or launch it from your tooling with
`--remote-debugging-port=9222`.

```bash
saddlebag fill admin_login --field username --selector "#login_field" --url-contains example.com
saddlebag fill admin_login --field password --selector "#password"    --url-contains example.com
saddlebag fill admin_login --field totp     --selector "#app_totp"    --url-contains example.com
```

- `--url-contains` picks the tab. It must match exactly one open page. The error lists
  the open URLs when it matches none or several, so narrow it and retry.
- `--field totp` types a code computed from the stored seed. When fewer than five
  seconds remain in the current 30-second window, `fill` waits for the next one, so
  the code survives your submit click. `--min-seconds N` changes that margin.
- The reply carries the selector, the URL, the length the field holds after the insert
  and, for a TOTP code, how many seconds it stays valid. A field that is still empty is
  an error. A length that differs from the value's only logs a warning on the daemon:
  the field may mask, truncate or reformat what it was given.
- `--cdp URL` overrides the daemon's endpoint. Only a loopback endpoint is accepted,
  because a DevTools port is unauthenticated.

Confirm the sign-in by what the page shows next, through your browser tooling. The
field's value is the one thing on that page you leave unread.

## Run a command with secrets: `exec`

`exec` asks the daemon for the values, puts them in the environment and then becomes
the command. The command reads the values itself.

```bash
saddlebag exec --tag environment=local -- docker compose up -d
saddlebag exec --env API_TOKEN=ci_bot --env BOT_USER=ci_bot.username -- make smoke
saddlebag exec --tag environment=local --env OTP=admin_login.totp -- ./scripts/e2e
```

- `--tag` binds every matching secret's `var` to its password. A matching secret with
  no `var` is an error that names it. Two secrets filling the same `var` is also an
  error.
- `--env VAR=NAME[.field]` binds one variable explicitly. The field is `password`
  (the default), `username` or `totp`.
- The command runs with your privileges and prints what it prints. Pick a command that
  consumes the variable: a test runner, a migration, `docker compose`. A command whose
  job is to show its environment (`env`, `printenv`, `echo $VAR`, `set -x` tracing)
  would put the value in your transcript, so the secret stays wrapped inside a command
  that uses it.

## An ostler stack

A repo's `docs/services/ops/stack.yml` names one secret source. With saddlebag it is a
tag query:

```yaml
secrets:
  saddlebag: environment=local
```

ostler then runs `saddlebag list --tag environment=local --json`, checks each secret's
`var` against the `${VAR}` references in the rendered compose file, and runs every
`docker compose` command under `saddlebag exec`. No `stack.env` is written. A variable
the compose file references and no secret fills fails `ostler env check` with the
variable's name. The fix is a secret with that `var` and that tag, registered as below.

## A workflow node

A node that needs a secret wraps its command in `exec` and passes it through
`run_tool`. The secret stays out of the node's return value, its checkpoint and its
telemetry, because the node only ever holds the command line.

```python
run_tool(
    ["saddlebag", "exec", "--tag", f"environment={environment}", "--", "make", "seed"],
    check=True,
    logger=logger,
)
```

## A run in a container

The daemon, the browser and its debug port stay on the host. The container gets the
socket and its path, and nothing else:

```bash
docker run -v "$SADDLEBAG_SOCKET:/run/saddlebag.sock" -e SADDLEBAG_SOCKET=/run/saddlebag.sock ...
```

The client finds the socket at `$SADDLEBAG_SOCKET`, else `$XDG_RUNTIME_DIR/saddlebag.sock`,
else the OS runtime directory.

## Register a secret

You may create a secret's metadata. The value comes from the operator.

```bash
saddlebag secret create api_db --var POSTGRES_PASSWORD \
  --tag environment=local --description "The local stack's database password"
```

Then hand the operator the line that stores it, which reads the value on stdin:

```bash
saddlebag secret set api_db                  # password
saddlebag secret set admin_login --field totp  # the TOTP enrolment seed
```

When the value is one the project generates for a local stack, such as a database
password, you may generate it and pipe it straight into `secret set` in the same
command, so it never prints:

```bash
openssl rand -hex 24 | saddlebag secret set api_db
```

A value that belongs to a real account comes from the
operator, typed into their own terminal.

`secret tag` / `untag NAME K=V...` adjust tags. `secret unset NAME --field F` forgets
one value. `secret remove NAME` deletes the secret and every version of it. Removal is
permanent, so ask the operator before you run it.

## Errors and what they ask

| Message | Do this |
| --- | --- |
| `no saddlebag daemon on <path>` | Ask the operator to start `saddlebag serve`. In a container, check the socket mount and `SADDLEBAG_SOCKET`. |
| `<name> has no <field>. Store one with: ...` | Hand the operator the quoted `secret set` line. |
| `no such secret: <name>` | `saddlebag list` with the environment's tags, and pick by description. |
| `no secret carries all of those tags` | `saddlebag tags` shows the pairs in use. Drop or correct a tag. |
| `<name> matches the tags but has no var to fill` | Bind it with `--env VAR=<name>`, or narrow the tags so it does not match. |
| `<a> and <b> both fill <VAR>` | Narrow the tags, or bind one of them explicitly with `--env`. |
| `no open page's URL contains ...` / `N pages match ...` | Pick a `--url-contains` that matches exactly one of the listed URLs. |
| `the browser has no inspectable pages open` | Open the page first, in the browser that owns the debug port. |
| `no element matches <selector> on that page` | Read the page's structure through your browser tooling and pick the input's selector. |
| `<selector> matches a <tag>, which cannot hold typed text` | Point the selector at the `<input>` itself, not its wrapper or label. |
| `<selector> is still empty after the insert` | The field is read-only or the page re-rendered it. Wait for the form to settle, then fill again. |

## Install

The distribution is `stablemate-saddlebag`. The command and the import package are
`saddlebag`. `uv tool install stablemate` installs it with the rest of the stablemate
tools, and `uv tool install stablemate-saddlebag` installs it alone. It needs Python
3.12 or newer and a Vault with a KV v2 mount named `secret`. For a developer machine,
`vault server -dev` is enough.
