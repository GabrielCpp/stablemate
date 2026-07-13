# saddlebag

> Carry the right credentials for every ride.

`saddlebag` is the runtime credential pool for the stablemate ecosystem. It stores,
scans, and leases test identities so that `workhorse` workflows — and the AI agents
driving them — can acquire the right credential for a run without ever touching a
secret directly.

---

## Position in the ecosystem

| Tool | Job |
|---|---|
| **ostler** | Tends the knowledge graph — epics, stories, seeds, specs |
| **farrier** | Fits the shared prompt library onto each repo |
| **workhorse** | Runs the workflow graph unattended |
| **saddlebag** | Carries credentials — scan, select, lease, release |

Ostler owns the *spec* of what a test needs (roles, envs, surface). Saddlebag owns
the *runtime identity* that satisfies that spec. They don't overlap.

---

## Install

```bash
pipx install saddlebag                 # OS keyring backend
pipx install 'saddlebag[vault]'        # + HashiCorp Vault, for hosts with no keyring
```

Requires Python ≥ 3.12. Pool metadata lives in a local SQLite file whose location
follows each OS's convention (via `platformdirs`), overridable with `SADDLEBAG_DB`:

| OS | Default pool location |
|---|---|
| Linux | `~/.local/share/saddlebag/pool.db` (or `$XDG_DATA_HOME`) |
| macOS | `~/Library/Application Support/saddlebag/pool.db` |
| Windows | `%LOCALAPPDATA%\saddlebag\pool.db` |

---

## Where secrets live

Saddlebag does not implement encryption. It delegates to a store that already does
it properly, and picks one by availability:

1. **The OS keyring** — macOS Keychain, Windows Credential Manager, Linux Secret
   Service — whenever a real backend is present. This is the common case on a
   developer machine, and needs no configuration at all.
2. **HashiCorp Vault** (KV v2) otherwise — for containers, CI, and any host with
   no desktop session.

If neither is available, saddlebag **exits with an error** rather than falling back
to anything weaker. There is no plaintext path.

```bash
export SADDLEBAG_BACKEND=vault   # force a backend, skipping autodetection
export VAULT_ADDR=http://127.0.0.1:8200
export VAULT_TOKEN=root
```

### Two stores, one credential

| Where | What |
|---|---|
| Secret store (keyring / Vault) | the **password**, keyed by credential id |
| Pool database (SQLite) | **metadata** — `username`, `env`, `roles`, `features`, `surface` — and lease state |

The pool DB never contains a password, not even encrypted. `saddlebag list` and
`saddlebag scan` read only the pool, which is why they *cannot* leak a secret. Only
`acquire` reads the store, and only to write the password into one output file.

**Keyring scoping.** Secrets are namespaced under the service name `saddlebag`. That
is the whole of the portable cross-OS keyring contract — `(service, username,
password)` — and it is a genuine isolation boundary: a lookup under any other service
name returns nothing. There is no "separate keyring file" that works on all three
operating systems; Linux's Secret Service exposes a `preferred_collection` D-Bus
hook, but Keychain and Credential Manager have no equivalent, so relying on it would
be a Linux-only path that silently no-ops elsewhere.

**Per-credential keys are project-qualified.** Within that service, each secret's key
is `project/id` (or the bare `id` when unscoped). The keyring is one global namespace,
so this is what lets two *separate per-project pools* — e.g. a repo-local
`SADDLEBAG_DB` in each of two checkouts — both mint `cred-001` without one's password
clobbering the other's: they resolve to `repo-a/cred-001` and `repo-b/cred-001`. The
key is derived from the credential's own stored project, so `acquire`/`remove`/`doctor`
find the secret regardless of the directory you run them from.

> **Vault mode shares secrets, not the pool.** The metadata and lease table still
> live in the local `pool.db`, so two machines pointed at one Vault share passwords
> but keep independent pools and independent leases. A genuinely shared, collision-
> safe pool would mean holding the whole record in Vault — a change confined to
> `store.py`.

---

## Core concepts

### Credential

A test identity with metadata the AI can reason over:

```jsonc
{
  "id":        "cred-007",
  "username":  "admin@staging.example.com",
  "env":       "staging",
  "project":   "checkout-web",
  "roles":     ["admin", "billing"],
  "features":  ["mfa_enabled", "eu_region"],
  "surface":   "checkout/login",
  "locked":    false,
  "last_used": "2026-06-30T10:00:00Z",
  "lease_id":  null
}
```

`surface` mirrors the ostler seed convention — so a seed's `surface:` field is the
natural key to query the pool by. `roles` and `features` match as **supersets**: a
credential qualifies when it holds every role you asked for, and extras are fine.

### Lease

When a credential is acquired it gets a `lease_id` and is marked locked. No other
workhorse run can check it out until it is released or the TTL expires (default 2h).
This makes parallel cross-env runs safe without collisions.

The TTL is a hard backstop, not a hint: once it elapses the credential is reusable
even if nobody released it, so a crashed run cannot strand an identity forever.

---

## CLI

### Pool management

```bash
# Add a credential (the password only ever arrives on stdin)
printf '%s' "$PASSWORD" | saddlebag add \
  --env staging \
  --project checkout-web \
  --username admin@staging.example.com \
  --password-stdin \
  --roles admin billing \
  --features mfa_enabled eu_region \
  --surface checkout/login

# Or import the password from a variable in a .env file
saddlebag add \
  --env staging \
  --username admin@staging.example.com \
  --password-env-file app.env --password-var STAGING_ADMIN_PASSWORD \
  --roles admin billing \
  --surface checkout/login

# List the pool (never emits passwords)
saddlebag list                               # scoped to the current project (see below)
saddlebag list --env staging --json
saddlebag list --project checkout-web        # a different project
saddlebag list --all-projects                # the whole pool, unscoped

# Remove a credential and its password
saddlebag remove cred-007

# Health check — store reachable? locked or stale leases? orphaned metadata?
saddlebag doctor
```

#### Project scoping

A credential belongs to a **project**, and by default that project is inferred
from where you run saddlebag — the enclosing git repository's name (stable from
any subdirectory), or the current directory's name outside a repo. So inside the
`stablemate` checkout, `saddlebag add` tags the new credential `stablemate` and
`saddlebag list` / `saddlebag scan` show only that project's credentials, with no
flag needed.

Override it explicitly with `--project NAME`, opt a credential out with
`--project ''`, and ignore scoping entirely with `--all-projects`:

```bash
saddlebag add --username … --env staging …        # project inferred, e.g. stablemate
saddlebag add --username … --project checkout-web  # explicit project
saddlebag list                                     # only the current project
saddlebag list --all-projects                      # every project
```

#### Importing from a `.env`

A credential is a *structured identity* — username, env, roles, features, surface —
but a `.env` is a flat `KEY=value` list that holds only the secret. It carries none
of that metadata. So you import **one variable at a time**: the `.env` supplies the
password via `--password-env-file`/`--password-var`, and every piece of metadata is
supplied as a flag on the same `add` command.

```bash
# app.env  — real-world .env: secrets only, no saddlebag metadata
#   DATABASE_URL=postgres://localhost/app
#   STAGING_ADMIN_PASSWORD="s3kr#t with spaces"
#   STRIPE_KEY=sk_test_123

saddlebag add \
  --username admin@staging.example.com --env staging \
  --roles admin billing --surface checkout/login \
  --password-env-file app.env --password-var STAGING_ADMIN_PASSWORD
```

There is no bulk `import` command and a `.env` cannot describe several credentials,
because it has nowhere to put each one's distinct metadata. Value handling favours
secrets: a value wrapped in matching quotes is taken literally (spaces and `#`
included), and inline `#` comments are **not** stripped — quote any value that
contains spaces or `#`.

### Scan and select

This is the command workhorse calls from a `script` node. It queries the pool,
renders the available candidates into a prompt, and asks the agent CLI to pick one:

```bash
# Emit candidates and let the AI select, lease, and write the result
saddlebag scan \
  --env staging \
  --roles admin billing \
  --surface checkout/login \
  --select-via claude \
  --run-id "$RUN_ID" \
  --output .workhorse/credential.json

# Or: emit candidates only, and let the workflow's agent node do the reasoning
saddlebag scan --env staging --roles admin --json
```

`--select-via` calls the agent CLI with a compact selection prompt:

```
You are acquiring a test credential. Choose the best match and return only JSON.

Required: env=staging, roles=[admin, billing], surface=checkout/login

Candidates:
[
  {"id": "cred-007", "roles": ["admin","billing"], "env": "staging",
   "features": ["mfa_enabled","eu_region"], "locked": false},
  {"id": "cred-012", "roles": ["admin"], "env": "staging",
   "features": [], "locked": false}
]

Respond with: {"selected": "<id>", "reason": "<one line>"}
```

The candidate list is built from pool metadata, so **no password is ever placed in
an agent's context**. If the agent returns an id that was not on the list, saddlebag
rejects it rather than trusting it. The selected credential is then leased and written
to the output file.

Prefer `--output PATH` over `--output-json > PATH`: `--output` creates the file with
mode `0600` before writing the secret, whereas a shell redirect leaves permissions to
your umask.

### Lease management

```bash
# Acquire by exact id (bypasses AI selection)
saddlebag acquire cred-007 --ttl 3600 --output .workhorse/credential.json

# Release by lease id
saddlebag release --lease-id <lease_id>

# Release everything a workhorse run holds
saddlebag release --run-id "$RUN_ID"

# Force-expire stale leases (safe and idempotent — good CI cleanup)
saddlebag expire
```

`release` is idempotent: releasing an already-released lease succeeds, so a cleanup
step cannot fail a build.

---

## Workhorse integration

Credentials flow through a workflow as `script` nodes that bookend the agent work:

```yaml
# workflow.yaml (excerpt)
nodes:
  - id: acquire_credential
    type: script
    script: |
      saddlebag scan \
        --env {{ env }} \
        --roles {{ required_roles | join(' ') }} \
        --surface {{ surface }} \
        --select-via {{ agent_cli }} \
        --run-id {{ run_id }} \
        --output .workhorse/credential.json
    next: run_test

  - id: run_test
    type: agent
    prompt: test_login.j2
    inputs:
      credential: "{{ load_json('.workhorse/credential.json') }}"
    next: release_credential

  - id: release_credential
    type: script
    script: saddlebag release --run-id {{ run_id }}
    next: done
```

Releasing by `--run-id` rather than `--lease-id` means one node cleans up every
credential the run holds, including those acquired in parallel branches:

```yaml
  - id: acquire_staging
    type: script
    script: saddlebag scan --env staging --run-id {{ run_id }} ... --output .workhorse/cred-staging.json

  - id: acquire_prod
    type: script
    script: saddlebag scan --env prod --run-id {{ run_id }} ... --output .workhorse/cred-prod.json
```

Output files belong under `.workhorse/`, which workhorse's default scaffolding
gitignores.

---

## Ostler integration

Ostler seed metadata carries the *spec*; saddlebag satisfies it at runtime. No code
coupling — workhorse reads ostler's JSON output and passes fields as flags:

```bash
SEED=$(ostler show seed checkout-flow address-step --json)
ROLES=$(echo "$SEED" | jq -r '.required_roles | join(" ")')
SURFACE=$(echo "$SEED" | jq -r '.surface')

saddlebag scan \
  --env "$ENV" --roles $ROLES --surface "$SURFACE" \
  --select-via claude --run-id "$RUN_ID" \
  --output .workhorse/credential.json
```

Ostler seed frontmatter can carry two optional fields saddlebag understands:

```markdown
### address-step
- status: researched
- surface: checkout/address
- required_roles: admin billing        # saddlebag --roles
- required_features: eu_region         # saddlebag --features (optional filter)
- summary: Collect & validate the shipping address
```

---

## Security model

- Passwords are held by the **OS keyring or Vault**, never by saddlebag itself and
  never in the pool database.
- A password is only ever *entered* on stdin (`--password-stdin`) — never as an
  argv element, where it would land in the process table and shell history.
- `list`, `scan` and the agent selection prompt read pool metadata only, and so
  cannot emit a password. `acquire` is the sole reader of the store.
- The credential file written by `--output` is created `0600` before the secret is
  written, and belongs in gitignored `.workhorse/`.
- Leases have a hard TTL (default 2h). `saddlebag expire` in CI cleanup force-releases
  anything that leaked.
- When no secret store is available, saddlebag **fails** rather than degrading.

---

## Package layout

```
saddlebag/
├── __init__.py
├── cli.py               # argparse entry point: add, list, remove, scan, acquire,
│                        #   release, expire, doctor
├── db.py                # SQLite pool — schema, metadata CRUD, lease management
├── store.py             # Secret stores: OS keyring (default) + Vault (fallback)
├── selector.py          # AI selection: build prompt, call agent CLI, parse response
├── models.py            # Credential, Lease, AcquiredCredential, Requirement
└── workhorse.py         # `.workhorse/credential.json` contract (0600 output)
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
