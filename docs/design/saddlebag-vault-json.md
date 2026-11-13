# Saddlebag store export and import as plain JSON

Disclosure: before this design started, my context held the saddlebag skill
description and two memories. They name the consumers (`fill`, `type`, `exec`,
`env import`), a PreToolUse guard over credential files, and a deferred
"keyring-only" note. Each design decision they carry is a claim in 1b.
Sections 1 to 4 were drafted before any saddlebag source or doc was read.
Section 5 opens with the log of what the mapping changed in them.

## 1. Problem

The operator keeps test logins and tokens in saddlebag. On macOS, with no
daemon running, those secrets sit in the login Keychain plus a catalogue file,
and no command reads or writes them as a whole. Moving them to a new machine,
backing them up, or fixing twenty entries means `secret create` and
`secret set` again by hand, one prompt per value.

Done looks like this:

- One command run by the operator at a terminal writes every secret of the
  store the route picks to one JSON file they can open in an editor.
- One command loads that file into the store the route picks on any machine:
  the Keychain, the Secret Service, or Vault behind the daemon.
- The round trip loses nothing. Export, import into an empty store, export
  again, and the two files are byte-identical.
- A 50-secret store moves in one command each way. On the interpreter that
  created the Keychain items, export raises no Keychain prompt (A2).

Out of scope:

- An encrypted or passphrase-protected export.
- Live sync between machines.
- Reading the formats of other password managers.
- Vault's version history of a secret. Export reads the current version.
- Changing `env import`, whose conflict rule differs from this one (5, M4).
- Any path that hands a secret value to an agent.

The change gives up one stated guarantee, and the operator agrees to it by
approving this note: "saddlebag itself never writes a value to disk" becomes
"saddlebag writes values to disk only in a file the operator exported" (5b).

## 1b. Claims

1. saddlebag hands the secret to its consumer so the agent never holds the
   value (saddlebag skill description).
2. A PreToolUse guard refuses a read of a dotenv, key or credentials file
   (saddlebag skill description).
3. `env import` already loads a dotenv into the store (saddlebag skill
   description).
4. A keyring-only note was deferred (memory, configuration injection slices).

## 2. Parts and concepts

### Level 1

1. **The store.** Holds the named secrets on one machine, behind one route.
   Owns the records, the values and the OS or Vault storage behind them.
   Never knows a file format. Hands whole secrets to the transfer and takes
   whole secrets back. (Revised, see R1.)
2. **The document.** The plain JSON shape of a whole store. Owns the schema and
   its version. Never knows which storage the secrets came from.
3. **The transfer.** Moves secrets between a store and a document, both ways.
   Owns the conflict rule and the check-everything-before-writing load. Never
   knows JSON syntax or a storage API.
4. **The exposure guard.** Keeps the plaintext file between the operator and
   their own disk. Owns who may cause an export, the file's permissions, and
   the guard's recognition of the file. Never knows what a secret holds.

Flow. On export the operator asks at a terminal. The exposure guard checks that
a person at a terminal asked and that the file does not exist. The transfer
reads every secret with its values from the store and builds a document. The
exposure guard writes the file owner-only. On import the transfer reads and
validates the whole document, finds every conflict, and only then writes the
secrets into the store.

### Level 2

The store

| Concept | Owns | Never knows |
|---|---|---|
| Secret | One named record with its kind of attributes, as a value | Where it is stored, and its values |
| Secret store | Listing, reading and writing records and values | The document |
| Route | Which store a command reaches (keyring in-process, or the daemon) | The document (Revised, see R2) |

The document

| Concept | Owns | Never knows |
|---|---|---|
| Exported secret | One secret's record plus its values, as a value | The storage |
| Store document | The versioned top-level shape: format tag, version, exported secrets in name order | The storage |
| Document reader | Refusing a document whose format, version or any entry it cannot read | The store |

The transfer

| Concept | Owns | Never knows |
|---|---|---|
| Export | Turning every secret of a store into a document | File writing |
| Import plan | The writes a document implies, with every refusal found before the first write | JSON syntax |
| Conflict rule | Whether an existing name is refused or replaced | A secret's content |

The exposure guard

| Concept | Owns | Never knows |
|---|---|---|
| Operator presence | Refusing an export that no person at a terminal confirmed | The document |
| Export file | Creating the file owner-only, under a name the guard knows, never over an existing file | The secrets |
| Guard rule | Denying an agent's read of an export file | The document's shape |

`Secret` is a shared value type between the store and the document.
`Exported secret` wraps it and is the one place a record and its values travel
together (R3).

## 3. Invariants

1. A round trip is lossless: export, import into an empty store, export again
   gives byte-identical files. Owner: Store document (fixed key order, name
   order, one trailing newline). Upheld by Export and the Import plan.
2. An import writes nothing until the whole document reads, every record
   passes the same checks `secret create` and `secret set` apply, and no
   name conflicts under the chosen rule. Owner: Import plan. A store failure
   after the first write stops the import and names the secrets already
   written (R4).
3. A secret value leaves the store as plaintext output only after a person at
   a terminal confirmed it. Owner: Operator presence.
4. An export file is created with mode 0600, never replaces an existing file,
   and its name ends in `.saddlebag.json`. Owner: Export file.
5. An agent's read of a file ending in `.saddlebag.json` is denied. Owner:
   Guard rule.

## 4. Forces and patterns

Forces:

- The storage varies by machine: the macOS Keychain, the Secret Service, Vault
  behind the daemon. Export and import must work on each without knowing
  which, and across them (export from the Keychain, import into Vault).
- The document outlives the code that wrote it: a file exported today is
  imported after the record grows a field.
- The record grows: metadata arrived after tags.
- Export and import must be testable without a real keychain.
- Agents run commands in this workspace and must not receive the plaintext.
- The operator edits the file by hand between export and import.

Patterns:

- Between parts: one value handed along. The store yields `Secret` records and
  values, the transfer builds a `Store document`, the guard writes it.
- Secret store is a role, from the storage force. Export and import depend on
  the role alone. Tests use an in-memory variant. The route stays the one place
  that chooses the store.
- Export and import run where the store runs, as two requests over the route,
  from the storage force. On the keyring route they run in-process. On the
  daemon route the daemon runs them, so the import plan sees one store and the
  client holds no Vault token (R5).
- Store document carries a format tag and an integer version, from the
  outlives-its-writer force. The reader refuses an unknown format or a newer
  version. No migration code until a version 2 exists.
- Exported secret reuses the record's own JSON form, from the record-grows and
  hand-edit forces. It is the shape `saddlebag list --json` already prints,
  with `fields` replaced by a `values` object. A field added to the record
  reaches the export with no second serialiser.
- Conflict rule is a value with two settings, refuse (default) and replace. It
  picks one branch in the import plan, so it is not a role.
- Operator presence is a check that stdin and stdout of the export command are
  a terminal, plus a `[y/N]` answer read from it, from the agent force. An
  agent's tool call has no terminal, so it is refused before any request.
- Export file and Guard rule share one suffix, from the agent force. The suffix
  is the only thing the guard can see in a tool call's arguments.

Claims:

- Claim 1 is re-derived as invariant 3. Export is a second deliberate
  exception, beside `exec`, and the security doc says so (5b).
- Claim 2 is re-derived as the Guard rule with one new suffix.
- Claim 3 is rejected as a base for import. `env import` stops at the first
  conflicting key after earlier keys are stored (M4). Import reuses its checks,
  not its loop.
- Claim 4 is unrelated. The deferred note concerns configuration injection,
  and this design works on both routes.

Open lookups, resolved in section 5: L1 what a record holds, L2 whether the
store lists its secrets on macOS, L3 what "the user vault" names, L4 how the
guard recognises a file, L5 how `env import` handles a conflict, L6 whether
saddlebag already detects a non-interactive caller.

## 5. Mapping onto the existing system

Revision log:

- R1. Section 2, part "the vault" renamed "the store". L3 found no vault
  scopes. "The user vault on macOS" is the keyring store, which the route
  picks when no daemon answers (`saddlebag/route.py:481`). "Vault" in
  saddlebag's code means HashiCorp Vault.
- R2. Section 2, concept "Vault scope" replaced by "Route". L3: the choice of
  store is `SADDLEBAG_BACKEND`, the config key, or a live daemon.
- R3. Section 2, concept "Entry" split into `Secret` and `Exported secret`. L1:
  the record type holds no value by construction (`saddlebag/models.py:121`),
  and that property protects `list`.
- R4. Section 3, invariant 2 narrowed from all-or-nothing to
  check-before-write. The keyring store writes the catalogue and each Keychain
  item separately (`saddlebag/keyring_store.py:286`), so no store offers a
  transaction.
- R5. Section 4, pattern "export and import run where the store runs" added.
  L6 and the socket protocol show every verb runs in `Verbs`, in-process or in
  the daemon (`saddlebag/route.py:449`).

Parts:

- **The store. Exists.** `SecretStore` (`saddlebag/store.py:34`) with
  `KeyringStore` and the Vault store. Owns and never-knows match. `names()` and
  `value(name, field)` are all export needs.
- **The document. New.** `saddlebag/transfer.py`, beside the catalogue's own
  JSON reader. One module holds the document and the transfer, because each is
  under a hundred lines and nothing else imports the document.
- **The transfer. New.** Same module, called from two new verbs in
  `saddlebag/verbs.py`: `export` and `import`.
- **The exposure guard. New in part.** Operator presence and the export file go
  in `saddlebag/cli.py`. The guard rule goes in `saddlebag/guard.py`.

Concepts:

| Concept | Verdict | Where, and the finding |
|---|---|---|
| Secret | Exists | `saddlebag/models.py:121`. Name, username, description, var, tags, fields, metadata (L1) |
| Secret store | Exists | `saddlebag/store.py:34`. Listing is `names()`, served on the keyring route by the catalogue, so macOS enumerates without a Keychain search (L2) |
| Route | Exists | `saddlebag/route.py:481` |
| Exported secret | New | `transfer.py`. `Secret.to_dict()` minus `fields`, plus `values: {"password": ..., "totp": ...}` with both keys always present and `""` for no value |
| Store document | New | `transfer.py`. `{"format": "saddlebag-export", "version": 1, "secrets": [...]}`, `indent=2`, secrets sorted by name, as the catalogue already writes (`saddlebag/catalogue.py:366`) |
| Document reader | New | `transfer.py`. Validates names, vars, tags, metadata keys and TOTP seeds with the functions `verb_create` and `verb_set` already call (`saddlebag/verbs.py:622`) |
| Export | New | `verb_export`. Logs the verb and a count, never a value |
| Import plan | New | `verb_import`. Checks every exported secret, then per secret: `create`, `set_value` per non-empty value. On replace, `remove` first |
| Conflict rule | New | `--replace` on `saddlebag import` |
| Operator presence | New | `cmd_export`. No helper checks stdin today. `_on_terminal` checks stdout and stderr for `exec` (`saddlebag/cli.py:285`), so presence is new (L6) |
| Export file | New | `cmd_export`. Opens with `O_CREAT|O_EXCL`, mode 0600, as the catalogue opens its temp file (`saddlebag/catalogue.py:368`). Refuses a name without the suffix |
| Guard rule | Reshape | `saddlebag/guard.py:68` matches by name. One more suffix joins `_KEY_SUFFIXES`' check (L4). `saddlebag import FILE` passes already, because `saddlebag` is not among the readers the guard knows |

Mismatches:

- M1. `SECURITY.md` states "No verb returns a stored value to its caller" with
  `exec` as the one exception, and "Saddlebag itself never writes a value to
  disk". Export breaks both. The code is not wrong and the design is not
  wrong. The doc is rewritten to name export as the second exception and to
  state its three fences: the terminal check, the 0600 file, the guard rule.
- M2. Over the daemon route, `verb_export` sends every value through the socket
  to whoever asks. A same-user process can already pull each value through the
  `env` request (`saddlebag/verbs.py:750`), as `SECURITY.md` admits, so
  export opens no new class of leak. It does make the full dump one request.
  The design keeps it on both routes, because "especially the user one"
  implies the daemon store is in scope too (A3).
- M3. The `env` request returns a stored TOTP seed, not a computed code, for a
  binding with field `totp` (`saddlebag/verbs.py:774` calls `_value`, which
  returns the seed). The README says a seed bound into a command's
  environment leaves as a code. This is a defect outside this design. It is
  not fixed here.
- M4. `env import` stops at the first name already in use, after the keys
  before it are stored (`saddlebag/cli.py:369`). The design's import finds
  every conflict first. The design is right for a 50-secret file. `env import`
  stays as is (out of scope).

What the existing system has that the design lacks: `doctor`'s missing-item
check. A catalogue record can claim a value whose Keychain item was deleted
behind it, so `value()` returns nothing. Export writes that value as `""` and
goes on without a warning (operator, 2026-11-13). To keep invariant 1, every
exported secret carries both value fields, and `""` means "no value". A secret
with no value, a missing item and a field never set all export the same way,
and import stores no value for any of them.

Command surface:

```bash
saddlebag export FILE.saddlebag.json       # terminal only, asks [y/N], prints "exported N secrets to FILE"
saddlebag import FILE.saddlebag.json [--replace] [--json]   # prints "imported NAME" per secret, never a value
```

Document example:

```json
{
  "format": "saddlebag-export",
  "version": 1,
  "secrets": [
    {
      "name": "normal_login",
      "username": "gab",
      "description": "Log in as a normal user",
      "var": "LOGIN_PASSWORD",
      "tags": [["environment", "local"], ["role", "user"]],
      "metadata": {"phone": "+15555550100"},
      "values": {"password": "...", "totp": "JBSWY3DPEHPK3PXP"}
    }
  ]
}
```

## 5b. What must not move

| Receiver | Gets today | Enforced by | Before | Holds when |
|---|---|---|---|---|
| The agent's transcript | No verb an agent runs prints a value | `verbs.py` returns counts; tests in `test_cli.py` | 0 commands print a value | `saddlebag export` with no terminal exits non-zero before any request; a test proves it |
| The operator's disk | No value written by saddlebag | Nothing (a doc sentence) | 0 files | Only an export the operator confirmed writes one, mode 0600. Let go on purpose, listed in section 1 |
| An agent reading files | Denied on the dotenv, key and credential names in `guard.py:16-19` and two home paths | `test_guard.py` | Every case in `test_guard.py` passes | Same cases pass, plus a denial of `.saddlebag.json` |
| The daemon's log | Verbs, names and counts, no value | `test_daemon.py` | No value in the log | `export` and `import` log a count; a test greps the log for a value |
| Every existing verb | Its current behaviour | The suite | 495 tests pass in 8.6 s | 495 still pass, plus the new ones |
| The catalogue file | Version 1 format | `test_catalogue.py` | Version 1 | Unchanged; import writes through the store, never the file |

## 6. Slices

1. **Keyring round trip.** Export and import on the keyring route, refuse
   conflicts, presence check, 0600 file, suffix rule. Touches all four parts
   on one store. Done when a test exports a store of three secrets (one with a
   TOTP, one with no value, one with metadata) from an in-memory store,
   imports into an empty one, exports again and the bytes match; the
   no-terminal export test fails before any request; and every 5b row reads
   its after-value.
2. **Replace and refusals.** `--replace`, and every refusal reported before
   the first write. Done when a document with one conflict and one bad seed
   writes nothing and names both, and a store with a deleted Keychain item
   exports that value as `""` with exit 0.
3. **Daemon route and the guard.** The two verbs over the socket, the guard
   suffix, the `SECURITY.md` and README rewrites. Done when a daemon test
   round-trips through the socket, `guard --hook` denies
   `cat x.saddlebag.json`, and the 5b rows hold.
4. **The operator's own move.** Manual: export on the Mac, import on Linux
   with the keyring route and with the daemon. Done when `saddlebag list` on
   the target matches the source and a `fill` of one migrated login works.
   Only the operator can run this (A1).

## 7. Assumptions

1. **Assumption:** the operator runs export from a real terminal, where stdin
   and stdout are TTYs. **Decided:** export refuses otherwise, including from
   the desktop app's own shell. **Basis:** none. **If wrong:** Operator
   presence; the operator would need another confirmation channel, such as a
   flag the guard denies to agents.
2. **Assumption:** the interpreter running export is the one that created the
   Keychain items. **Decided:** the done line promises no prompt only then; a
   reinstalled interpreter prompts once per item, as today. **Basis:**
   `SECURITY.md`, "The OS keyring". **If wrong:** section 1 done line.
3. **Assumption:** "my vault, especially the user one on macOS" means every
   store, with the keyring store first. **Decided:** both routes, keyring
   slice first. **Basis:** the request's word "especially". **If wrong:**
   drop slice 3's daemon half and mismatch M2.
4. **Assumption:** a fixed `.saddlebag.json` suffix is acceptable on every
   export file. **Decided:** the CLI refuses another name. **Basis:** the
   guard sees only paths (`saddlebag/guard.py:68`). **If wrong:** Guard rule
   loses its only handle; invariant 5 has no owner.
5. **Assumption:** replace means the file's version of a secret wins whole,
   including dropping a value the file lacks. **Decided:** replace removes the
   secret and recreates it. **Basis:** none. **If wrong:** Import plan grows a
   merge rule.
6. **Assumption:** stdout is not a destination. **Decided:** export takes a
   file only, so a pipe cannot carry the plaintext into another tool's log.
   **Basis:** the agent force. **If wrong:** Export file accepts `-` behind
   the same presence check.
