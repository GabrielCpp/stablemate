# saddlebag

> Carry the right credentials for every ride.

`saddlebag` carries the material a run needs, so that `workhorse` workflows — and
the AI agents driving them — never touch a secret directly. It holds two kinds of
material, in one pool:

- a **credential** — a test identity, scanned, selected and leased for the run;
- an **environment** — the `.env`-shaped configuration a dev stack needs to *boot*,
  secret and non-secret alike, rendered to a file on demand.

Saddlebag is not only a vault. It is what **packages an environment**: an
environment holding no secrets at all is still worth owning here, because the value
of the pool is reproducing a stack anywhere, not merely hiding its passwords.

---

## Position in the ecosystem

| Tool | Job |
|---|---|
| **ostler** | Tends the knowledge graph — epics, stories, seeds, specs |
| **farrier** | Fits the shared prompt library onto each repo |
| **workhorse** | Runs the workflow graph unattended |
| **saddlebag** | Carries credentials and environments — scan, select, lease, render |

Ostler owns the *spec* of what a test needs (roles, envs, surface). Saddlebag owns
the *runtime identity* that satisfies that spec, and the *environment material* the
stack boots with. They don't overlap.

---

## Install

**Not on PyPI** — saddlebag is an optional add-on that runs from a checkout of the
[stablemate](https://github.com/GabrielCpp/stablemate) workspace; no base workflow
requires it:

```bash
make sync                              # at the workspace root
uv run --package saddlebag saddlebag --help
# the [vault] extra adds HashiCorp Vault, for hosts with no OS keyring
```

Requires Python ≥ 3.12. Pool metadata lives in a local SQLite file whose location
follows each OS's convention (via `platformdirs`), overridable with `SADDLEBAG_DB`:

| OS | Default pool location |
|---|---|
| Linux | `~/.local/share/saddlebag/pool.db` (or `$XDG_DATA_HOME`) |
| macOS | `~/Library/Application Support/saddlebag/pool.db` |
| Windows | `%LOCALAPPDATA%\saddlebag\pool.db` |

---

## Sixty seconds

Put one test identity in the pool, let an agent pick it, and give it back:

```bash
# 1. Add a credential. The password only ever arrives on stdin.
printf '%s' "$PASSWORD" | saddlebag add \
  --env staging \
  --username admin@staging.example.com \
  --password-stdin \
  --roles admin billing \
  --surface checkout/login

# 2. Ask the pool for something matching, and let the agent CLI choose.
#    What comes back is the lease and the identity — never the password.
saddlebag scan \
  --env staging --roles admin billing --surface checkout/login \
  --select-via claude --run-id "$RUN_ID" --json

# 3. …run whatever needed the identity, then give every lease back.
saddlebag release --run-id "$RUN_ID"
```

And the other half — the configuration a stack boots with:

```bash
saddlebag env add web-local --env local --target web/.env.local
saddlebag env set web-local VITE_FIREBASE_PROJECT_ID=acme            # argv  -> config
printf '%s' "$KEY" | saddlebag env set web-local API_KEY --secret-stdin  # stdin -> secret
saddlebag env render web-local                                       # writes web/.env.local, 0600
```

---

## Where secrets live

Saddlebag does not implement encryption. It delegates to a store that already does it
properly, and picks one by availability: the **OS keyring** (macOS Keychain, Windows
Credential Manager, Linux Secret Service) whenever a real backend is present, and
**HashiCorp Vault** (KV v2) otherwise, for containers, CI and any host with no desktop
session. If neither is available, saddlebag **exits with an error** rather than falling
back to anything weaker — there is no plaintext path.

```bash
export SADDLEBAG_BACKEND=vault   # force a backend, skipping autodetection
export VAULT_ADDR=http://127.0.0.1:8200
export VAULT_TOKEN=root
```

The password lives in that store; everything else — `username`, `env`, `roles`,
`features`, `surface`, lease state — lives in the pool database, which never holds a
password even encrypted. That split is why `list` and `scan` *cannot* leak a secret,
and why no password ever reaches an agent's context. The full account — keyring
scoping, project-qualified keys, what Vault mode does and does not share, and the
list of guarantees each command keeps — is in
[docs/SECURITY.md](https://github.com/GabrielCpp/stablemate/blob/main/saddlebag/docs/SECURITY.md).

---

## Core concepts

A **credential** is one test identity, with metadata the AI can reason over:

```jsonc
{
  "id":       "cred-007",
  "username": "admin@staging.example.com",
  "env":      "staging",
  "project":  "checkout-web",
  "roles":    ["admin", "billing"],
  "features": ["mfa_enabled", "eu_region"],
  "surface":  "checkout/login",
  "locked":   false,
  "lease_id": null
}
```

`surface` mirrors the ostler seed convention, so a seed's `surface:` field is the
natural key to query the pool by; `roles` and `features` match as supersets. Acquiring
a credential **leases** it — no other run can check it out until it is released or its
TTL (default 2h) elapses, which is what makes parallel cross-env runs collision-free.

An **environment** is the other unit: a named, ordered set of `KEY` entries answering
"what does the stack need to boot?" rather than "who do I sign in as?". Unlike a
credential it is *shared*, not leased, so ten runs may render it at once. Each entry is
`config` (in the pool DB, in the clear), `secret` (in the store), `credential-ref`
(resolved at render time from a leased credential), or `pending` — a key named but not
yet supplied. Which kind you get is decided by **the channel you supplied the value on**:
argv is `config`, stdin is `secret`. A value on argv is already in the process table and
your shell history, so it cannot honestly be called a secret.

---

## Commands

| | |
|---|---|
| `add` `list` `remove` `doctor` | manage the credential pool |
| `scan` | query the pool and let an agent CLI select and lease a match |
| `acquire` `release` `expire` | leases, by id or by `--run-id` |
| `env add` `import` `set` `unset` `remove` | define an environment and its entries |
| `env list` `show` `doctor` | inspect it — none of these can emit a secret |
| `env export` | write the checkable-in YAML manifest |
| `env render` | materialize the target file (`--check` to diff without writing) |

The vault is **opaque**: no command prints, logs or returns a stored secret — not
`acquire`, not `scan`, not with any flag. `env render` is the single verb that turns
a secret into anything outside the store, and what it writes is the environment's
own `0600` target file, never stdout.

A credential belongs to a **project**, inferred from the enclosing git repository's
name, so `list` and `scan` show only the current repo's credentials with no flag
needed; `--project NAME` and `--all-projects` override that.

Then, by topic:

- **[docs/CREDENTIALS.md](https://github.com/GabrielCpp/stablemate/blob/main/saddlebag/docs/CREDENTIALS.md)**
  — the credential record and the lease, every pool command, project scoping, importing
  a password out of a `.env`, and what the AI selection prompt actually contains.
- **[docs/ENVIRONMENTS.md](https://github.com/GabrielCpp/stablemate/blob/main/saddlebag/docs/ENVIRONMENTS.md)**
  — the four entry kinds, every `env` command, the YAML manifest that lets an
  environment leave the machine it was defined on, and the `render --check` gate.
- **[docs/SECURITY.md](https://github.com/GabrielCpp/stablemate/blob/main/saddlebag/docs/SECURITY.md)**
  — the threat model: which store holds what, keyring scoping, why a config-only
  environment needs no store at all, and the guarantees each command is built to keep.
- **[docs/INTEGRATION.md](https://github.com/GabrielCpp/stablemate/blob/main/saddlebag/docs/INTEGRATION.md)**
  — driving saddlebag from a workhorse workflow (acquire and release as blueprint
  nodes) and feeding a scan from ostler seed metadata.

---

## Package layout

```
saddlebag/
├── __init__.py
├── cli.py               # argparse entry point: add, list, remove, scan, acquire,
│                        #   release, expire, doctor, and the `env` subcommands
├── db.py                # SQLite pool — schema, metadata CRUD, lease management,
│                        #   environments and their entries
├── store.py             # Secret stores: OS keyring (default) + Vault (fallback)
├── selector.py          # AI selection: build prompt, call agent CLI, parse response
├── models.py            # Credential, Lease, Requirement, Environment,
│                        #   EnvironmentEntry — none of them carries a secret
├── context.py           # Project inference — the enclosing git repo's name
├── envfile.py           # Minimal `.env` reader/writer (no python-dotenv)
├── manifest.py          # The checkable-in YAML an environment travels as
├── render.py            # Resolve an environment to values; the `--check` gate
└── workhorse.py         # `write_private` — the 0600-before-content write
```

Two deliberate departures from the original spec: there is no `crypto.py`, because
delegating to the keyring or Vault means saddlebag never rolls its own encryption;
and the CLI is built on `argparse`, matching every other package in this workspace,
rather than Click.

---

## Name

A **saddlebag** is the kit a horse carries on a ride — the right tools, ready when
needed, returned to the stable when the ride is done. It fits the stablemate
vocabulary: ostler tends the stable, farrier fits the gear, workhorse does the
riding, saddlebag carries what's needed for the journey.
