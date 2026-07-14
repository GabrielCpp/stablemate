# Saddlebag environment pool — packaging a stack's configuration

> **Status:** **phases 1–3 implemented** in [`saddlebag`](../saddlebag/README.md); phase 4
> (workflow adoption) is outstanding and lives in `vigilant-octo`. This document extends
> saddlebag from a pool of *test identities* into the single source of truth for **environment
> material** — the `.env`-shaped configuration a dev stack needs to boot, secret **and
> non-secret alike**. It adds a second first-class concept (the **environment**) alongside the
> existing credential, sharing the same SQLite pool and the same secret store. Nothing about
> the credential model changes.
>
> Saddlebag is not only a vault. It is what **packages an environment** — an environment may
> contain no secrets at all and still be worth owning here, because the value of the pool is
> reproducing a stack anywhere, not merely hiding its passwords.

> **What shipped, and what it decided.** The model, schema, CLI, manifest and render are as
> described below. Four things the design left open were settled in the building, and §12 is
> updated accordingly:
>
> - **`env unset NAME KEY`** was added (not in §6). Without it, a mis-imported key could only
>   be removed by dropping the whole environment, and a `secret` whose entry changed kind would
>   strand its stored value. Changing an entry's kind away from `secret`, and `env unset`, both
>   delete the store key — orphans are *prevented* rather than detected, which is the only
>   option that works: the OS keyring has no enumeration API, so `env doctor` can see a pool
>   entry with no secret behind it, but never a stored secret with no entry in front of it.
> - **A `credential-ref` may name `username` as well as `password`.** A `.env.test` almost
>   always needs both `TEST_USER_EMAIL` and `TEST_USER_PASSWORD`, and the identity is already in
>   the pool. Both entries share **one** lease on the credential — leasing per *entry* would
>   have collided with itself.
> - **`--check` takes no lease and writes nothing at all**, so a QA preflight has no side
>   effects. It exits non-zero when the environment is unresolvable *or* when the target file is
>   absent, drifted, or has extra keys; the JSON report separates those two with `resolvable`
>   and `in_sync`, so a caller can tell "a human must supply a key" from "just render it".
> - **The `dotenv` writer is the exact inverse of the reader.** Values that cannot round-trip
>   through the parser's quoting contract (a newline; both quote characters *and* a need to
>   quote) raise rather than write something that reads back differently. A corrupted secret is
>   worse than a failed render; `--format json` takes what dotenv cannot.

## 1. Problem

Saddlebag exists so that "workflows — and the AI agents driving them — can acquire the right
credential for a run without ever touching a secret directly." That promise currently covers
exactly one kind of material: a **test identity** (`username` + one password, tagged with
`env` / `roles` / `features` / `surface`). It does not cover the material a stack needs to
*start*, and that gap has already cost a run.

### The incident

A `coder` run on Predykt reached QA, which blocked with "web not reachable on :5173". The
autonomous operator (`resolve_qa`) went to diagnose the dev stack and tried to read
`web/.env.local`. The agent-CLI permission layer **auto-rejected the read**. That turn then
died without emitting its JSON contract, workhorse retried by *resuming* the session, and the
resumed turn re-emitted the JSON while silently skipping the file write it was supposed to
have done — parking a supposedly autonomous run on an operator gate for hours.

The rejected read is the root of that chain, and it was the permission layer doing its job:
an agent should not be reading a file full of secrets. But there is no sanctioned alternative,
so today an agent that needs the stack's config has exactly three options, all bad — read the
secret file (rejected), invent placeholder values (silently wrong stack), or declare the
environment unfixable (escalate to a human for something no human needed to answer).

### What's actually in that file

```
VITE_FIREBASE_API_KEY            # publishable, but still material the repo doesn't check in
VITE_FIREBASE_AUTH_DOMAIN        # config
VITE_FIREBASE_PROJECT_ID         # config
VITE_FIREBASE_AUTH_EMULATOR_HOST # config — and stack-shape-defining
VITE_STRIPE_PUBLISHABLE_KEY      # publishable
```

None of it is an identity. There is nowhere in a `Credential` to put any of it: no username,
no roles, no surface, and five values rather than one password. The README is explicit that a
`.env` "cannot stand alone as a credential source" because it carries no metadata — which is
the same structural reason it cannot *round-trip through* the credential pool as-is.

### The consequence for setup_fix

`prompts/setup-fix.md` already instructs the environment fixer to "fix broken local config (a
wrong/missing local env file (`.env.local`), backend URL, emulator host/port)". It is told to
fix the file but given **no source of truth to fix it from**. A story-independent fixer that
must make a stack runnable, and cannot read or reconstruct the stack's own config, is being
asked to guess. The environment pool is what turns that instruction into a mechanical one.

## 2. Goals

- Make saddlebag the **record of environment material** across repos — secret *and non-secret* —
  so a dev stack can be materialized on any host or container from the pool alone.
- **Package configuration per environment**, not just secrets: an environment with zero secret
  entries is a legitimate, useful environment, and must work on a host with no keyring and no
  Vault (§7).
- Let an agent bring a stack up **without ever reading or writing a `.env` file**, and without
  a secret value ever entering its context.
- Give `setup_fix` a deterministic path: render the environment, or fail with the exact list of
  keys a human must supply.
- Preserve every existing saddlebag invariant, in particular: **the pool DB never contains a
  secret**, and there is **no plaintext fallback** for material that *is* secret.
- Stay additive — an existing pool, and every existing credential command, keeps working
  unchanged.

## 3. Non-goals

- **Not a general configuration manager.** Environments describe what a *stack* needs to boot
  for development and QA. Application settings, feature flags, and production config are out
  of scope.
- **Not a runtime config service.** An environment is rendered to a file once, before the stack
  starts. Nothing reads the pool at application runtime.
- **Not cross-machine pool sync.** The pool DB stays local; the manifest (§8) is what travels,
  and in Vault mode the secret *values* travel with it. See §8 for how those two halves meet.

## 4. The model

A second first-class concept, sitting beside the credential and sharing its infrastructure:

| Concept | Unit | Leased? | Answers |
|---|---|---|---|
| **Credential** (existing) | one test identity | yes — exclusive | "who do I sign in as?" |
| **Environment** (new) | one `.env`-shaped bundle | no — shared | "what does the stack need to boot?" |

An **environment** is a named, project-scoped, ordered set of **entries**. Each entry is one
`KEY` plus a declaration of *where its value comes from*:

| Entry kind | Value lives in | Use for |
|---|---|---|
| `config` | the pool DB, in the clear | hosts, ports, project ids, emulator addresses, feature toggles — material that is not sensitive and *is* worth diffing and reviewing |
| `secret` | the secret store (keyring / Vault) | API keys, tokens, anything the repo would not check in |
| `credential-ref` | resolved at render time from a **leased credential** | `TEST_USER_PASSWORD` — the join between the two pools (see §9) |

The `config`/`secret` split is the load-bearing part, and it is what lets the environment pool
live in the same SQLite DB without breaking the invariant. The pool DB holds an environment's
**key manifest** and its non-sensitive values; every sensitive value goes to the store, keyed
by the same project-qualified convention credentials already use. So `saddlebag env list` and
`saddlebag env show` remain *structurally incapable* of leaking a secret — exactly the property
that makes `list` and `scan` safe today.

Config is a **first-class** kind, not a tolerated exception. Most of what a dev stack needs to
boot is not sensitive at all — of Predykt's five keys in §1, the two that actually define the
stack's *shape* (`VITE_FIREBASE_PROJECT_ID`, `VITE_FIREBASE_AUTH_EMULATOR_HOST`) carry no secret
whatsoever, and they are precisely the ones an agent needed and could not get. An environment
holding nothing but config entries is a normal environment, and §7 makes sure it works on a host
with no secret store at all.

### How a value's kind is decided

Not by a default, and not by a flag the operator has to remember — **by how the value is
supplied**:

| Supplied as | Kind | Why |
|---|---|---|
| `env set NAME KEY=value` (on argv) | `config` | a value on the command line is already visible in `ps` and the shell history — it *cannot* be treated as a secret without lying about its exposure |
| `env set NAME KEY --secret-stdin` (on stdin) | `secret` | the same discipline `saddlebag add --password-stdin` already enforces |
| `env set NAME KEY --from-credential cred-007:password` | `credential-ref` | the value is never handled by saddlebag at all until render |

This is self-enforcing rather than merely conventional: there is no way to place a secret in the
pool DB by accident, because the only channel that reaches the DB is the one that has already
published the value to the process table. It also removes the awkward question of what a
sensible *default* kind would be — there isn't one, and now there doesn't need to be.

A key whose value has not yet arrived (the common state right after an import) is `pending`: it
has a name, a `required` flag and a note, but no value and no kind yet. `env doctor` reports the
pending set, and that list is exactly what a human still has to supply.

## 5. Schema

Additive. Two new tables in the existing `pool.db`; `CREATE TABLE IF NOT EXISTS` in `_SCHEMA`
means an old pool simply gains them, empty, the first time a new saddlebag opens it — no entry
in `_MIGRATIONS` is needed (that list is for `ALTER TABLE ... ADD COLUMN` on the pre-existing
`credentials` table).

```sql
CREATE TABLE IF NOT EXISTS environments (
    id          TEXT PRIMARY KEY,           -- env-001, minted like cred-001
    name        TEXT NOT NULL,              -- web-local
    project     TEXT,                       -- predykt — inferred from the git repo, as today
    env         TEXT NOT NULL,              -- local | staging — same vocabulary as credentials.env
    target      TEXT,                       -- default render path, repo-relative: web/.env.local
    format      TEXT NOT NULL DEFAULT 'dotenv',   -- dotenv | json
    description TEXT,
    last_used   REAL,
    UNIQUE (project, name)
);

CREATE TABLE IF NOT EXISTS environment_entries (
    environment_id TEXT NOT NULL REFERENCES environments(id) ON DELETE CASCADE,
    key            TEXT NOT NULL,           -- VITE_FIREBASE_API_KEY
    kind           TEXT NOT NULL DEFAULT 'pending',  -- pending | config | secret | credential-ref
    value          TEXT,                    -- config: the value. everything else: NULL, always.
    cred_ref       TEXT,                    -- credential-ref: "cred-007:password"
    required       INTEGER NOT NULL DEFAULT 1,
    note           TEXT,                    -- why this key exists; surfaced in `env show`
    position       INTEGER NOT NULL DEFAULT 0,      -- render order, so a rendered file is stable
    PRIMARY KEY (environment_id, key),
    CHECK (kind IN ('pending', 'config', 'secret', 'credential-ref')),
    CHECK (kind = 'config' OR value IS NULL)    -- the invariant, enforced by SQLite itself
);

CREATE INDEX IF NOT EXISTS idx_environments_project ON environments(project);
CREATE INDEX IF NOT EXISTS idx_environments_env     ON environments(env);
```

**Invariant:** a row with `kind != 'config'` must have `value IS NULL`. It is a SQLite `CHECK`
constraint rather than a rule in `db.py`, so a bug in a caller — or a future caller that has not
been written yet — cannot quietly cross the boundary. The database itself refuses to hold a
secret.

### Secret store keys

Secret entries key into the existing `SecretStore` as:

```
<project>/<environment_id>/<KEY>        e.g.  predykt/env-001/VITE_FIREBASE_API_KEY
(bare <environment_id>/<KEY> when the environment is unscoped)
```

This mirrors the existing project-qualified `project/id` scheme, and for the same reason: the
keyring is one global namespace, so two repos each holding an `env-001` must not clobber each
other.

**`store.py` needs no Protocol change.** `SecretStore` is already "put/get/delete a
string-keyed secret" — `credential_id` is just the name of the parameter. One small change *is*
warranted in `VaultStore`: it currently writes the KV field as `{"password": ...}`, which is a
lie for an env value. Write `{"value": ...}` going forward and, on read, fall back to
`password` when `value` is absent, so existing Vault-mode pools keep resolving.

## 6. CLI

```bash
# Define an environment and its render target
saddlebag env add web-local --env local --target web/.env.local

# Seed the key manifest from the checked-in example (keys only — never values)
saddlebag env import web-local --from web/.env.example
#   → every key lands `pending` and `required`. `env doctor` now reports exactly
#     what still has to be supplied, and nothing has been guessed.

# Supply values — the channel decides the kind (§4)
saddlebag env set web-local VITE_FIREBASE_PROJECT_ID=predykt              # → config
saddlebag env set web-local VITE_FIREBASE_AUTH_EMULATOR_HOST=127.0.0.1:9099   # → config
printf '%s' "$KEY" | saddlebag env set web-local VITE_FIREBASE_API_KEY --secret-stdin  # → secret
saddlebag env set web-local TEST_USER_PASSWORD --from-credential cred-007:password     # → credential-ref

# Inspect — these CANNOT emit a secret value
saddlebag env list [--project P] [--all-projects] [--json]
saddlebag env show web-local [--json]     # config values in the clear; secrets as <set>/<pending>

# Package and move (§8)
saddlebag env export web-local --output env/web-local.yaml   # manifest: keys + config, no secrets
saddlebag env import web-local --from env/web-local.yaml     # reconstitute on another host

# Materialize — the only command that touches a secret value
saddlebag env render web-local [--output web/.env.local] [--run-id RUN]
saddlebag env render web-local --check    # resolve everything, write nothing; exit non-zero on gaps

# Health
saddlebag env doctor [--project P]        # pending required keys, orphaned store keys, dangling cred refs
saddlebag env remove web-local            # drops entries and their stored secrets
```

The safety properties are deliberate and mirror the credential pool's:

- **`list` / `show` / `doctor` read only the pool DB** for anything sensitive, so they cannot
  leak a secret even when handed to an agent. `show` prints config values in the clear — that is
  the point of config — and reports a secret entry as `<set>` or `<pending>`, which is enough to
  reason about and is never the value.
- **`render` is the single point where a secret becomes a file.** It writes through the same
  `0600`-before-content path as `workhorse.write_credential` (create with owner-only mode, then
  `fchmod`, so the value is never momentarily world-readable), and prints nothing to stdout but
  the path it wrote. Prefer `--output PATH` over a shell redirect, for the same reason the
  README already gives.
- **`render --check` is the gate.** It resolves every entry, compares against the target file if
  one exists, and reports missing/unset/extra keys — without writing. This is what a QA preflight
  or a CI job calls, and it is safe to run anywhere because it emits key *names* only.

## 7. Config-only environments, and the secret store

Accepting non-secret material has one consequence that must be designed for rather than
discovered: **saddlebag today refuses to run without a secret store.** `open_store()` raises
`StoreUnavailableError` when there is no OS keyring and no `VAULT_ADDR` — deliberately, because
a credential without a store is meaningless and degrading to plaintext is not on the table.

But an environment made entirely of `config` entries needs no store at all, and the hosts where
that matters most are exactly the ones with no keyring: containers, CI, headless boxes — the
places a stack most needs to be reproducible. If `env render` opened the store eagerly, a
config-only environment would fail on precisely the machines it was built for.

So the store is opened **lazily, and only when an entry actually requires it**:

- an environment whose entries are all `config` renders on any host, with no keyring, no Vault,
  and no configuration whatsoever;
- the moment one `secret` or `credential-ref` entry is in play, the store must open, and if it
  cannot, saddlebag fails with the existing remediation message rather than rendering a partial
  file.

The no-plaintext-fallback rule is untouched: it governs material that *is* secret. It was never
a claim that non-secret material must be treated as if it were.

## 8. The manifest — how configuration becomes a package

Config values live in the pool DB, and the pool DB is **local and unsynced** — the README is
explicit that even in Vault mode, "the metadata and lease table still live in the local
`pool.db`." For credentials that asymmetry is tolerable. For configuration it is fatal to the
whole point: an environment that cannot leave the laptop it was defined on has not packaged
anything.

The fix is that the thing which travels is not the database but a **manifest** — a checkable-in
YAML rendering of an environment, holding every key, its kind, its note, its `required` flag,
the render target and format, and, for `config` entries, the value itself. It holds **no secret
values**, by construction: a `secret` entry appears as a declaration that a secret is required
under that key, not as the secret.

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
  - key: VITE_FIREBASE_AUTH_EMULATOR_HOST
    kind: config
    value: 127.0.0.1:9099
    note: unset this to point the web app at real Firebase Auth
  - key: VITE_FIREBASE_API_KEY
    kind: secret          # value lives in the store, keyed predykt/env-001/VITE_FIREBASE_API_KEY
  - key: TEST_USER_PASSWORD
    kind: credential-ref
    from: cred-007:password
```

`env export` writes it; `env import` reads it back, on this host or any other. Then the two
halves meet cleanly: **the manifest carries the configuration, the store carries the secrets.**
On a fresh container, `env import` + a reachable Vault reconstitutes the whole environment; with
no Vault, it reconstitutes everything except the secrets and `env doctor` names exactly which
ones are missing. Neither half can leak the other.

This also subsumes `.env.example` rather than living beside it. The example file is a key list
with no kinds, no notes, no required flags, no target and no values — the manifest is a strict
superset, and it is the artifact the repo should actually check in. Keeping `.env.example` is
then a compatibility choice for humans and unrelated tooling, not a second source of truth.
(`env import --from .env.example` remains supported precisely so an existing repo can bootstrap
its first manifest from what it already has.)

## 9. The join with credentials

A `credential-ref` entry is the reason both concepts belong in one tool. A `.env.test` that
needs the leased test user's password is currently unrepresentable: the identity is in the pool,
the file that consumes it is not.

At render time, a `credential-ref` entry causes saddlebag to **acquire a lease** on the named
credential (honouring `--run-id` and the existing TTL semantics), read the password from the
store, and write it into the rendered file. The lease is held by the run, exactly as
`saddlebag acquire` does today, and freed by the existing `saddlebag release --run-id "$RUN_ID"`
— which therefore needs **no change** to also clean up after `env render`.

Environments themselves are **not leased**. A credential is an exclusive identity — two runs
signing in as the same user collide. An environment is shared, read-only config; ten runs may
render it concurrently. Adding a lease to it would buy nothing and would serialize parallel
runs for no reason.

## 10. Workflow integration

This is the payoff, and it is what closes the incident in §1.

**`setup_fix` stops touching env files.** Its prompt's "fix broken local config" bullet becomes:

> The stack's environment material is owned by saddlebag, not by files in the repo. Run
> `saddlebag env render <name> --run-id "$RUN_ID"` to materialize it. **Never read, write, or
> invent the contents of a `.env` file.** If render reports pending required keys, that is a
> human-only wall: report `unfixable` and name the exact keys.

That converts the one failure mode a fixer genuinely cannot resolve (a secret only a human
holds) into a precise, actionable escalation, and removes the three bad options entirely. An
agent no longer has any reason to read a secret file — which in turn means the permission layer
can **deny agent reads of `.env*` outright**, a rule that is only enforceable once a sanctioned
path exists.

**The coder workflow gains a bookend pair**, in the shape the README already documents for
credentials:

```yaml
  - id: ensure_env
    type: script
    script: |
      saddlebag env render {{ env_name }} --run-id {{ run_id }}
    next: qa

  # ... at the end of the run, the existing release node already covers any
  # credential-ref leases that `render` took out:
  - id: release_credentials
    type: script
    script: saddlebag release --run-id {{ run_id }}
```

**The operator populates the pool once per repo**, and only once: `env import --from .env.example`
gives the key list, the operator supplies the values, `env export` writes the manifest, and the
manifest is committed. From then on any host or container reconstitutes the environment from the
repo — plus the store, for whichever keys are genuinely secret.

## 11. Phasing

1. **Model + storage.** `models.Environment` / `EnvironmentEntry`, the two tables, the `CHECK`
   invariant, the project-qualified store keys, the lazy `open_store()` (§7), and the `VaultStore`
   field rename with back-compat read.
2. **CLI.** `env add|import|set|list|show|remove|doctor`, with the leak-proof read paths.
3. **Package + render.** `env export`/`env import` for the manifest (§8), then `env render` /
   `--check`, the `0600` write path, `--run-id` plumbing, and the `credential-ref` join with the
   existing lease machinery.
4. **Workflow adoption.** The `setup-fix.md` rewrite, the `ensure_env` node, and the permission
   rule denying agent reads of `.env*`. Populate Predykt's pool from `web/.env.example` as the
   first real consumer.

Phases 1–3 are self-contained in saddlebag and land with unit tests in the existing style; a pool
with no environments behaves exactly as it does today. Phase 4 is the only one that touches
`vigilant-octo`, and it is the one that pays back the incident.

Note that phases 1–2 are already useful on their own to a repo with **no secrets at all**: a
config-only environment, exported to a manifest, is a better `.env.example` than `.env.example`.
That is the test of whether config is really first-class here — if the tool is worth adopting
before a single secret is stored, it is.

## 12. Open questions

- **Should `env render` refuse to overwrite an existing target that has drifted?** *Settled as
  proposed:* render is authoritative and overwrites, and `--check` — which never writes and takes
  no lease — is what a workflow calls first, so drift is *reported* before it is clobbered.
  `--check` reports drift by key **name** only, so it stays safe to run in CI or hand to an agent.
- **One environment per target, or several?** *Still open, and deliberately unaddressed.* The
  schema allows many environments per project, each with its own `target`, so a stack needing
  `web/.env.local` *and* `api/.env` is two environments rendered by two `env render` calls. A
  `--group` concept could bundle them; nothing yet justifies it.
- **Should a `config` entry be able to interpolate another?** *Settled as proposed: not in v1.*
  Entries are literal. `manifest.load` coerces a YAML scalar to `str`, so a bare `9099` is text
  rather than an int, but nothing is expanded.

> The earlier draft asked whether a publishable key like `VITE_FIREBASE_API_KEY` should default to
> `config`. Making config first-class **dissolves** that question rather than answering it: there is
> no default kind any more (§4), so the operator states what the value is by how they hand it over,
> and neither answer is a silent one.
