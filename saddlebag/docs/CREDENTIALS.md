# Credentials — scan, select, lease, release

This is the reference for the credential half of saddlebag: what a credential record
holds, how a lease keeps two runs from taking the same identity, and every command
that manages the pool. The
[README](https://github.com/GabrielCpp/stablemate/blob/main/saddlebag/README.md)
covers install and the shortest path through it; the environment half is in
[docs/ENVIRONMENTS.md](https://github.com/GabrielCpp/stablemate/blob/main/saddlebag/docs/ENVIRONMENTS.md),
and what each command can and cannot leak is in
[docs/SECURITY.md](https://github.com/GabrielCpp/stablemate/blob/main/saddlebag/docs/SECURITY.md).

## The credential record

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

## The lease

When a credential is acquired it gets a `lease_id` and is marked locked. No other
workhorse run can check it out until it is released or the TTL expires (default 2h).
This makes parallel cross-env runs safe without collisions.

The TTL is a hard backstop, not a hint: once it elapses the credential is reusable
even if nobody released it, so a crashed run cannot strand an identity forever.

## Pool management

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
saddlebag remove cred-007                    # --force removes it even while leased

# Health check — store reachable? locked or stale leases? orphaned metadata?
saddlebag doctor
```

### Project scoping

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

### Importing from a `.env`

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

## Scan and select

This is the command a workhorse workflow calls from a node. It queries the pool,
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

# Or: emit candidates only, and let the workflow's agent turn do the reasoning
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

## Lease management

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
