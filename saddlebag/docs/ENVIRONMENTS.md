# Environments — packaging the configuration a stack boots with

An **environment** is saddlebag's second first-class concept: a named, ordered set of
entries answering "what does the stack need to boot?", where a credential answers
"who do I sign in as?". This file is its reference — the four entry kinds, the rule
that decides which kind you got, every `saddlebag env` command, and the manifest that
lets an environment leave the machine it was defined on.

The [README](https://github.com/GabrielCpp/stablemate/blob/main/saddlebag/README.md)
covers install and the shortest path through it; credentials are in
[docs/CREDENTIALS.md](https://github.com/GabrielCpp/stablemate/blob/main/saddlebag/docs/CREDENTIALS.md),
and what each command can and cannot leak is in
[docs/SECURITY.md](https://github.com/GabrielCpp/stablemate/blob/main/saddlebag/docs/SECURITY.md).

## Entries, and the four kinds

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

### The channel decides the kind

Not a default, and not a flag you have to remember — **how you supply the value**:

```bash
saddlebag env set web-local VITE_FIREBASE_PROJECT_ID=acme          # argv  -> config
printf '%s' "$KEY" | saddlebag env set web-local API_KEY --secret-stdin  # stdin -> secret
saddlebag env set web-local TEST_USER_PASSWORD --from-credential cred-007:password
```

A value on argv is already in the process table and your shell history: it cannot be
treated as a secret without lying about its exposure, so it is `config`. A value on
stdin is a `secret` — the same discipline `add --password-stdin` enforces. This is
self-enforcing rather than conventional: **there is no way to put a secret in the
pool DB by accident**, because the only channel that reaches the DB is the one that
has already published the value.

## The commands

Populate the pool once per repo, then reconstitute it anywhere:

```bash
# Define an environment and its render target
saddlebag env add web-local --env local --target web/.env.local

# Seed the key manifest from the checked-in example — keys only, values discarded
saddlebag env import web-local --from web/.env.example
#   -> every key lands `pending`. Nothing has been guessed, and `env doctor` now
#      reports exactly what still has to be supplied.

# Supply values (the channel decides the kind)
saddlebag env set web-local VITE_FIREBASE_PROJECT_ID=acme
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

A key is required by default; `env set --optional` marks one that may stay unset
without failing a render, and `--required` undoes that.

## The manifest — how configuration becomes a package

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
    value: acme
  - key: VITE_FIREBASE_API_KEY
    kind: secret          # the value lives in the store, keyed acme/env-001/VITE_FIREBASE_API_KEY
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

## `render` and `--check`

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

An environment made only of `config` entries needs no secret store at all, which is
what makes it renderable on a container or CI box with no keyring — see
[docs/SECURITY.md](https://github.com/GabrielCpp/stablemate/blob/main/saddlebag/docs/SECURITY.md#config-only-environments-need-no-secret-store).
