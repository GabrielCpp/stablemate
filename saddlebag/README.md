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

### Environment

The second first-class concept — a named, ordered set of **entries** answering
"what does the stack need to boot?", where a credential answers "who do I sign in
as?".

| Concept | Unit | Leased? |
|---|---|---|
| **Credential** | one test identity | yes — exclusive |
| **Environment** | one `.env`-shaped bundle | no — shared, so ten runs may render it at once |

Each entry is one `KEY` plus a declaration of where its value comes from:

| Entry kind | Value lives in | Use for |
|---|---|---|
| `config` | the pool DB, in the clear | hosts, ports, project ids, emulator addresses — material that is not sensitive and *is* worth diffing and reviewing |
| `secret` | the secret store (keyring / Vault) | API keys, tokens, anything the repo would not check in |
| `credential-ref` | resolved at render time from a **leased credential** | `TEST_USER_PASSWORD` — the join between the two concepts |
| `pending` | nowhere yet | a key that has been named but not supplied. `env doctor` reports these, and that list is exactly what a human still has to provide |

The `config`/`secret` split is what lets environments share the credential pool's
database without breaking its invariant. The DB holds an environment's key manifest
and its *non-sensitive* values; every sensitive value goes to the store. So
`env list` and `env show` stay **structurally incapable** of leaking a secret — the
same property that makes `list` and `scan` safe.

#### The channel decides the kind

Not a default, and not a flag you have to remember — **how you supply the value**:

```bash
saddlebag env set web-local VITE_FIREBASE_PROJECT_ID=predykt          # argv  -> config
printf '%s' "$KEY" | saddlebag env set web-local API_KEY --secret-stdin  # stdin -> secret
saddlebag env set web-local TEST_USER_PASSWORD --from-credential cred-007:password
```

A value on argv is already in the process table and your shell history: it cannot be
treated as a secret without lying about its exposure, so it is `config`. A value on
stdin is a `secret` — the same discipline `add --password-stdin` enforces. This is
self-enforcing rather than conventional: **there is no way to put a secret in the
pool DB by accident**, because the only channel that reaches the DB is the one that
has already published the value.

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

### Environments

Populate the pool once per repo, then reconstitute it anywhere:

```bash
# Define an environment and its render target
saddlebag env add web-local --env local --target web/.env.local

# Seed the key manifest from the checked-in example — keys only, values discarded
saddlebag env import web-local --from web/.env.example
#   -> every key lands `pending`. Nothing has been guessed, and `env doctor` now
#      reports exactly what still has to be supplied.

# Supply values (the channel decides the kind)
saddlebag env set web-local VITE_FIREBASE_PROJECT_ID=predykt
saddlebag env set web-local VITE_FIREBASE_AUTH_EMULATOR_HOST=127.0.0.1:9099 \
  --note "unset this to point the web app at real Firebase Auth"
printf '%s' "$KEY" | saddlebag env set web-local VITE_FIREBASE_API_KEY --secret-stdin
saddlebag env set web-local TEST_USER_PASSWORD --from-credential cred-007:password

# Inspect — these CANNOT emit a secret value
saddlebag env list [--project P] [--all-projects] [--json]
saddlebag env show web-local [--json]   # config in the clear; a secret reads as <set>

# Package and move
saddlebag env export web-local --output env/web-local.yaml   # safe to commit
saddlebag env import web-local --from env/web-local.yaml     # reconstitute anywhere

# Materialize — the only command that turns a secret into a file
saddlebag env render web-local [--output PATH] [--run-id RUN]
saddlebag env render web-local --check    # resolve everything, write nothing

# Health, and cleanup
saddlebag env doctor [--project P] [--json]
saddlebag env unset web-local SOME_KEY    # drops the key and its stored secret
saddlebag env remove web-local
```

#### The manifest — how configuration becomes a package

The pool DB is local and unsynced. For credentials that is tolerable; for
configuration it would defeat the point, because an environment that cannot leave
the laptop it was defined on has not packaged anything. So the thing that travels is
not the database but a **manifest** — a checkable-in YAML rendering of an
environment. It carries **no secret values**, by construction:

```yaml
# env/web-local.yaml — safe to commit
name: web-local
env: local
target: web/.env.local
format: dotenv
entries:
  - key: VITE_FIREBASE_PROJECT_ID
    kind: config
    value: predykt
  - key: VITE_FIREBASE_API_KEY
    kind: secret          # the value lives in the store, keyed predykt/env-001/VITE_FIREBASE_API_KEY
  - key: TEST_USER_PASSWORD
    kind: credential-ref
    from: cred-007:password
```

The two halves then meet cleanly: **the manifest carries the configuration, the
store carries the secrets.** On a fresh container, `env import` plus a reachable
Vault reconstitutes the whole environment; with no Vault it reconstitutes everything
*except* the secrets, and `env doctor` names exactly which ones are missing. Neither
half can leak the other. A manifest that tries to carry a `value:` on a `secret`
entry is rejected on import, not imported.

This subsumes `.env.example` rather than living beside it — the example file is a key
list with no kinds, notes, required flags, target or values, and the manifest is a
strict superset. `env import --from .env.example` stays supported precisely so an
existing repo can bootstrap its first manifest from what it already has.

#### Config-only environments need no secret store

Saddlebag refuses to run without a store — deliberately, because a credential
without one is meaningless. But an environment made entirely of `config` entries
needs no store at all, and the hosts where that matters most are exactly the ones
with no keyring: containers, CI, headless boxes — the places a stack most needs to
be reproducible. So the store is opened **lazily, and only when an entry actually
requires it**:

- an environment whose entries are all `config` renders on any host, with no
  keyring, no Vault and no configuration whatsoever;
- the moment one `secret` or `credential-ref` entry is in play, the store must open,
  and if it cannot, saddlebag fails rather than rendering a partial file.

The no-plaintext-fallback rule is untouched: it governs material that *is* secret. It
was never a claim that non-secret material must be treated as if it were.

#### `render` and `--check`

`render` is the single point where a secret becomes a file. It writes through the
same `0600`-before-content path as the credential file, and prints nothing to stdout
but the path it wrote. Nothing is written until *everything* resolves, so a missing
key can never leave a half-rendered file behind; if a required key has no value,
render exits non-zero and **names the exact keys a human must supply**.

`--check` is the gate: it resolves every entry, takes no lease, writes nothing, and
diffs the result against the target file, reporting missing, extra and drifted keys.
It is safe to run anywhere, in CI or in an agent's context, because its report names
keys and never values — including for drift, where the comparison looks at values but
the output does not.

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

### Bringing the stack up

An environment renders in the same shape, and needs no new release node — the
existing one already covers any `credential-ref` leases that `render` took out:

```yaml
  - id: ensure_env
    type: script
    script: saddlebag env render {{ env_name }} --run-id {{ run_id }}
    next: qa

  # ... and at the end of the run, the release node that is already there:
  - id: release_credentials
    type: script
    script: saddlebag release --run-id {{ run_id }}
```

This is what lets an environment fixer stop touching `.env` files at all. The stack's
environment material is owned by saddlebag, not by files in the repo: an agent runs
`env render` to materialize it, and never reads, writes, or invents the contents of a
`.env`. If render reports pending required keys, that is a human-only wall — the
agent reports it and names the exact keys, rather than guessing a value and producing
a silently wrong stack. Once that sanctioned path exists, a permission layer can deny
agent reads of `.env*` outright.

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

- Secrets are held by the **OS keyring or Vault**, never by saddlebag itself and
  never in the pool database. For environment entries this is enforced by the
  database itself: a `CHECK (kind = 'config' OR value IS NULL)` constraint means a
  bug in a caller — or a caller that has not been written yet — *cannot* quietly put
  a secret in a row.
- A secret is only ever *entered* on stdin (`--password-stdin`, `--secret-stdin`) —
  never as an argv element, where it would land in the process table and shell
  history. A value supplied on argv is therefore `config`, by definition rather than
  by policy.
- `list`, `scan`, `env list`, `env show`, `env doctor` and the agent selection prompt
  read pool metadata only, and so cannot emit a secret. `acquire` and `env render`
  are the sole readers of the store.
- The credential file written by `--output`, and the file written by `env render`,
  are created `0600` before the secret is written. `env render` prints only the path
  it wrote, never the contents.
- The **manifest** (`env export`) is the artefact meant to be committed, and carries
  no secret values by construction. A manifest that tries to smuggle one in is
  rejected on import.
- Leases have a hard TTL (default 2h). `saddlebag expire` in CI cleanup force-releases
  anything that leaked.
- When no secret store is available, saddlebag **fails** rather than degrading — for
  material that *is* secret. A config-only environment needs no store and renders
  anyway; that is not a fallback, it is the absence of a secret.

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
├── models.py            # Credential, Lease, AcquiredCredential, Requirement,
│                        #   Environment, EnvironmentEntry
├── envfile.py           # Minimal `.env` reader/writer (no python-dotenv)
├── manifest.py          # The checkable-in YAML an environment travels as
├── render.py            # Resolve an environment to values; the `--check` gate
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
