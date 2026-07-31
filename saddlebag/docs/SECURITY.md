# Security model — where secrets live, and what cannot leak

This is the full account of saddlebag's threat model: which store holds a password,
how the keyring is scoped so two projects cannot clobber each other, and the list of
guarantees each command is built to keep. The
[README](https://github.com/GabrielCpp/stablemate/blob/main/saddlebag/README.md)
summarises it in a paragraph; this file is what you read before trusting the pool with
a real credential, or before adding a command that touches one.

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

`--backend {keyring,vault}` on any command does the same thing for one invocation.

## Two stores, one credential

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

## Config-only environments need no secret store

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

## The guarantees

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
- **No password ever reaches an agent's context.** The candidate list `scan` renders
  into the selection prompt is built from pool metadata, and an id the agent returns
  that was not on that list is rejected rather than trusted.
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
