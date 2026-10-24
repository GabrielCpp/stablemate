# Saddlebag without a daemon: the OS keyring as a second shelf

Disclosure: the task that produced this note told me to read the saddlebag package and
the operator skill first, so I saw the existing solution before sections 1 to 4 were
written. It also carried design decisions already taken with the operator. Those decisions
and the shape I saw are listed as claims in 1b, and every part and concept below was tested
against "would I have named this without having seen the solution?". Measurements and the
state of this machine were taken before writing: gnome-keyring answers
`org.freedesktop.secrets` on the session bus, no saddlebag socket exists under
`$XDG_RUNTIME_DIR`, the `keyring` and `secretstorage` packages are not installed, and the
suite passes 102 tests.

## 1. Problem

An operator sitting at their own laptop wants to sign an agent in to a deployed site, or
run one command with a password in its environment. Today they first have to run a Vault
server, log in to it, start a long-lived helper process in a spare terminal and paste a
token into it. On this machine the helper does not even start, so the agent cannot sign in
at all. The operator already has a place that holds passwords for them, unlocked when they
log in: the desktop's keyring. Saddlebag cannot use it.

Done looks like this, to that operator:

- `saddlebag secret create`, `secret set`, `list`, `tags`, `fill`, `exec` and `doctor`
  work on a laptop with no Vault and no helper process running. The values rest in the
  OS keyring, which the desktop unlocked at login, and no verb prompts for approval on
  gnome-keyring. On macOS a value saddlebag stored is read back without a prompt until
  the Python interpreter is replaced.
- `list --json`, `list --tag` and `tags` print the same fields and obey the same tag
  query whichever place holds the values, so ostler's stack bring-up needs no change.
- A team or a container keeps using the shared Vault behind the helper process, with the
  same command lines as today.
- The operator who runs the helper can leave its Vault token in the keyring instead of
  pasting it each time. On a machine with no keyring, a private file holds it and
  `doctor` says so.
- Over SSH or on a server with no keyring, each verb stops with one line that names the
  two ways out: unlock or provide a keyring, or start the helper.
- No verb prints a secret value, whichever shelf it came from. That stays the one rule
  every path below obeys.

Out of scope:

- Moving existing secrets between the two shelves. A copy command is discussed under
  section 4 and deferred: this machine has nothing to move, and the operator re-registers
  a handful of secrets in minutes with the commands that already exist (A7).
- Any new way of delivering a value: `fill` over CDP and `exec` into a child environment
  stay the only two.
- Hardening against a hostile same-user process. The keyring is readable by every process
  of the logged-in user, as Vault's token file would be. The threat model in
  `saddlebag/docs/SECURITY.md` is unchanged: the agent's transcript, not a hostile peer.
- A third shelf (1Password, Bitwarden, a cloud secret manager). The design makes room for
  one but this change ships two.
- Windows Credential Manager. Not refused, not tested, not promised (A9).

## 1b. Claims

Decisions handed to me by the task, in its words, with the source.

1. "OS keyring is the local default for ad hoc invocations" (operator decision, task).
2. "Vault stays behind the daemon for shared and container cases" (operator decision, task).
3. "metadata needed for listing and tag filtering must survive in the keyring backend"
   (operator decision, task).
4. "A SecretStore abstraction with two backends: keyring ... and Vault" (task).
5. Backend selection by "env var, config file under the stablemate state dir, auto-detect
   when no socket is present" (task).
6. "the daemon's Vault token should also be storable in the keyring, with a 0600 file under
   $XDG_STATE_HOME/stablemate as the headless fallback and a `doctor` warning when the file
   is used. `serve` must still refuse VAULT_TOKEN in the environment" (task).
7. "never handle or print secret values, never run commands that dump the environment
   under exec" (operator rule, task).
8. Shape seen in the code: one process holds the Vault token and answers every verb over
   a unix socket; every other command is a thin client of it (`saddlebag/saddlebag/cli.py`,
   `daemon.py`).
9. Shape seen in the code: metadata lives beside the value in Vault's custom metadata,
   tags serialised as one JSON string (`vault.py`).

## 2. Parts and concepts

### Level 1: parts

**The shelf.** Where secrets rest between uses: each one's metadata (name, username,
description, var, tags) and its values (password, TOTP seed). It owns durability and
lookup by name. It never knows what a verb is, who asked, or where a value will be
delivered. It hands a record or a value to the counter on request.

**The counter.** The one place that answers a request: list what is on the shelf, filter by
tags, register a secret, store a value, resolve which values a `fill` or an `exec` needs,
report health. It owns every rule about secrets (names, fields, tag matching, the "two
secrets fill one var" error). It never knows which kind of shelf stands behind it nor
whether the request arrived from the same process or over a socket. It hands a value to
delivery and a reply to the route.

**Delivery.** Putting a value into its consumer: typed into a browser field, or placed in
the environment of a command the current process becomes. It owns the browser protocol,
the TOTP code computation and the exec. It never knows where the value came from. It
returns counts and locations, never the value.

**The route.** How a command line reaches a counter. Two shapes exist: the counter is in
the same process as the command, or it lives in a long-running process reached over a
socket. The route owns the choice between them and the error when neither is reachable.
It never knows what a verb does or what the shelf is made of. It hands a request to a
counter and a reply back to the command.

**Key custody.** The long-running process needs one credential of its own, the Vault token.
Custody owns where that token is read from and in what order of preference, and the
refusal of the unsafe places. It never knows a secret record. It hands one token to the
Vault shelf at start-up.

**The command surface.** Parsing the command line, printing tables and JSON, exit codes. It
owns the operator's vocabulary. It never knows a value exists. It hands a verb and its
arguments to the route.

Flow. The operator types a verb. The command surface parses it and asks the route for a
counter. The route either builds a counter in-process over the local shelf, or opens the
socket to the counter the operator started earlier. The counter applies the rules and asks
its shelf for records or a value. For `fill` and `exec` the counter hands the value to
delivery, which puts it where it is consumed. A reply, never carrying a value, returns along
the route to the command surface. Key custody acts at one other moment only: when the
operator starts the long-running counter, custody finds the Vault token and gives it to the
Vault shelf.

Test of the split: a person who has never seen the code can hear it as "there is a shelf
where secrets rest, a counter that applies the rules, a courier that puts a value into a
browser or a command, a way of reaching the counter, and someone who holds the key to the
Vault shelf". A password manager CLI with a plugin store would fit the same five parts. No
part is named after a module: the code has no `route`, `shelf`, `custody` or `counter`.

### Level 2: concepts

**The shelf**

| Concept | Owns | Never knows |
|---|---|---|
| Shelf (role) | The contract the counter calls: list names, read a record, create, store a value, forget a value, remove, read a value, retag, say whether it is reachable | Which variant it is; what a verb is |
| Vault shelf (variant) | Keeping records and values in one KV v2 mount, metadata in custom metadata | The keyring; the socket; the token's origin |
| Keyring shelf (variant) | Keeping values in the OS keyring, one item per (secret, field) | Vault; tags' query semantics |
| Catalogue | The metadata of every secret the keyring shelf holds, and which fields hold a value, in one private file | Any value; the keyring's API |
| Keyring door | Opening the OS keyring, telling "absent", "locked" and "refuses this process" apart, refusing plaintext backends | Secret records; what the caller wanted |
| Record | The value type both variants return: name, username, description, var, tags, fields | Where it came from |

Record is a shared value type. The catalogue exists only inside the keyring shelf: the
Vault shelf keeps its metadata in Vault and needs no catalogue, so the catalogue is not a
sign the split is wrong. The keyring door is separate from the keyring shelf because the
same door answers for key custody (below), and because the shelf's Owns would otherwise
read "keep values and diagnose the keyring".

**The counter**

| Concept | Owns | Never knows |
|---|---|---|
| Verb rules | Each verb's checks and its reply: list, tags, create, set, unset, remove, tag, untag, fill, env, doctor | Which shelf; which route |
| Tag query | Whether a record carries every wanted pair; the set of pairs in use | Where records come from |
| Binding | Which var gets which secret's which field for `exec`, and the collision error | The value |
| Health report | What `doctor` says: shelf reachable, secrets with no value, the route in use, the token's source, warnings | How to fix anything |

**Delivery**

| Concept | Owns | Never knows |
|---|---|---|
| Field typist | Picking the page, the element, inserting text, reporting a length | The secret's name; the shelf |
| Code clock | Turning a TOTP seed into the code valid now, and how long it stays valid | Anything else |
| Environment hand-off | Becoming the command with the bound values in its environment | Where values came from |

**The route**

| Concept | Owns | Never knows |
|---|---|---|
| Route (role) | Taking a request and returning a reply | Which variant it is |
| In-process route (variant) | Building a counter over the local shelf in this process and calling it | Sockets |
| Socket route (variant) | Finding the socket, sending one request, reading one reply | Shelves; verbs |
| Route choice | Which route a command uses: the explicit setting, else the config file, else "a socket answers" | What any verb does |
| Preference | The operator's standing choice of route, read from an environment variable or the shared stablemate config file | Sockets; shelves |

**Key custody**

| Concept | Owns | Never knows |
|---|---|---|
| Token source (role) | Handing one Vault token to the Vault shelf at start-up, or saying none exists | Secret records |
| Piped token (variant) | Reading the token from stdin when stdin is not a terminal | Files; the keyring |
| Kept token (variant) | Reading the token the operator stored in the OS keyring, through the keyring door | Files |
| Filed token (variant) | Reading a 0600 file `saddlebag/vault-token` under the platformdirs state dir, flagged for `doctor` | The keyring |
| Token refusal | Refusing to start when `VAULT_TOKEN` is in the environment; refusing `~/.vault-token` | Anything downstream |

**The command surface**

| Concept | Owns | Never knows |
|---|---|---|
| Parser | Verbs, flags, usage errors | Values |
| Printer | Tables, JSON, the one-line error, exit codes | Values |

## 3. Invariants

1. **No reply carries a value.** Owner: verb rules. Every reply is built from a record,
   a count, a selector, a URL or a name. Upheld during construction by the record type,
   which has no value field.
2. **A value leaves the shelf to exactly two consumers**, a browser field or a child
   process's environment, plus the one probe `doctor` makes to confirm a value exists.
   Owner: verb rules. Upheld by delivery, which has no return path for the text it typed.
3. **A value enters on stdin only.** Owner: the parser, which has no argv slot for one.
4. **The catalogue holds no value, ever.** Owner: the catalogue, which serialises a record
   and refuses any other type. Upheld by the keyring shelf, which writes values to the
   keyring door only.
5. **Every record `list --json` prints carries name, username, description, var, tags and
   fields, from either shelf.** Owner: the record type. Upheld by both variants, which
   must fill every field or `None`.
6. **No plaintext shelf.** When the OS keyring is absent or locked, the keyring shelf
   fails; it never falls back to an on-disk value store, including the `keyring` library's
   own plaintext backends. Owner: the keyring door.
7. **The Vault token is never read from the environment or from `~/.vault-token`.**
   Owner: token refusal. Upheld by the three token sources, none of which look there.
8. **The long-running counter stands only in front of a Vault shelf.** The in-process
   route never constructs a Vault shelf, so the token never enters an ad hoc process.
   Owner: route choice.
9. **A tag query means "carries every wanted pair"** in both shelves. Owner: tag query,
   which is the one function both variants are filtered through.
10. **Two secrets never fill one var under `exec`.** Owner: binding.

## 4. Forces and patterns

Forces:

- **Where values rest varies** (Vault today, the OS keyring now, maybe a third later), and
  it varies independently of what verbs do. Two variants exist today.
- **Where the counter runs varies** (this process, or a long-running one reached over a
  socket) and it varies independently of the shelf. In-process over Vault is forbidden
  (invariant 8), so it is not a free 2x2.
- **Where the Vault token comes from varies** by machine: a desktop has a keyring, a
  server does not, a one-off run pipes it. Three variants, one ordering.
- **Tests must swap the shelf** for an in-memory one, as they do today.
- **Metadata must be queryable by tag without reading a value**, and the OS keyring on
  macOS has no attribute search, while the Secret Service does. The keyring library that
  reaches both exposes neither.
- **The ad hoc path must stay cheap**: one process, a handful of keyring reads, no server.
- **A keyring that is locked, absent or distrustful of this binary must be told apart**,
  because each asks the operator for a different action.
- **The macOS Keychain trusts the creating application**: an item saddlebag wrote is read
  back by the same interpreter without a prompt; a different interpreter prompts per item.

Between parts: **ports and adapters**. The counter depends on the shelf role and the
command surface depends on the route role. Each role has variants chosen in one place.
Force: two axes of variation, independent of each other and of the verbs. The flow between
parts is **one request handed along, one reply handed back**, as today.

Inside parts:

- **Shelf role with two variants** (claim 4, re-derived from "where values rest varies").
  The Vault shelf is one variant beside the keyring shelf, not the base it extends. The
  protocol already in the code, confirmed in section 5, is the role.
- **Catalogue as a sidecar index** (claim 3, re-derived from "queryable by tag without
  reading a value" and "macOS has no attribute search"). The keyring shelf writes values
  to the keyring and metadata to one JSON file under the stablemate state dir, resolved
  through `platformdirs.user_state_dir("stablemate")` as ostler does, so it is
  `~/.local/state/stablemate/saddlebag/catalogue.json` on Linux and
  `~/Library/Application Support/stablemate/saddlebag/catalogue.json` on macOS. The file
  is owner-only and replaced atomically. One place holds metadata on both platforms, so `list --tag` is
  the same filter over the same records. Secret Service item attributes were considered
  and rejected: they would give Linux an attribute search macOS cannot match, so the
  catalogue would be needed anyway, and attributes are readable by any same-user D-Bus
  client, so they buy no secrecy. The keyring item carries a label for the operator's
  keyring UI and nothing else (A3).
- **Which fields hold a value is recorded in the catalogue**, not probed. Force: the ad hoc
  path must stay cheap, and on macOS a probe per item is a prompt per item when trust is
  lost. `doctor` is the one verb that probes, so a catalogue that drifted from the keyring
  (an item deleted in the keyring UI) is reported there.
- **Route role with two variants and one choice** (claim 5). The choice is: an explicit
  `SADDLEBAG_BACKEND` of `keyring` or `daemon` wins; else the `backend` key of the
  `[saddlebag]` table in the shared stablemate `config.toml`, the file `stablemate_core`
  already resolves through `platformdirs.user_config_dir("stablemate")`; else a socket
  that answers means `daemon`, and no socket means `keyring`. Claim 5's "config file under
  the state dir" is rejected on one force: the repo already has one config file per user
  for every tool, and a second file is a second place to look (A11). An explicit `SADDLEBAG_SOCKET` with no socket
  answering is an error, not a fall-through: the container case set it on purpose, and
  silently reading an empty local keyring there would hide the mount mistake. `serve`
  takes no route; it is the daemon.
- **Verb rules as one object over a shelf, used by both routes.** Force: the verbs must
  not fork. The in-process route constructs it over the keyring shelf; the daemon
  constructs it over the Vault shelf. Both call the same handler.
- **Token source role with three variants, ordered** (claim 6). Piped wins when stdin is
  not a terminal: an operator who pipes meant it. Else the kept token in the keyring. Else
  the filed token, which `doctor` reports with a warning. The kept token is written by
  `saddlebag serve --keep-token`, which reads it on stdin, stores it and exits; the filed
  token the operator writes themselves, and saddlebag refuses it unless its mode is 0600.
- **Keyring door as a plain function with a typed outcome**: open, locked, absent,
  distrusted. Force: three failures need three messages. No pattern beyond an enumeration.
- **Preference as a plain value** read from two places. No pattern.
- **On `set`, the keyring item is written before the catalogue records the field.** Force:
  a crash between the two writes must leave a state `doctor` can describe, and the
  catalogue must never claim a value that is not there. A record with no item is "no
  value"; an item with no record is "orphan item", listed by `doctor` and removed by
  `secret remove`.

Claims re-derived or rejected:

- Claims 1, 2, 4, 5, 6, 7: re-derived above.
- Claim 3: re-derived, with the sidecar chosen over item attributes.
- Claim 8 (every verb is a thin client of the daemon): rejected as a rule. It becomes one
  route variant. The counter keeps its shape, so the daemon loses nothing.
- Claim 9 (tags as one JSON string in custom metadata): kept for the Vault shelf, since
  changing it would migrate existing Vault data for no force. The catalogue stores tags as
  a list of pairs, and the record type hides the difference.

Variants are roles: shelf, route and token source are each named for what the consumer
asks, and no variant is a flag on another.

SOLID check:

- Single responsibility: every Owns reads without "and" after splitting the keyring door
  from the keyring shelf and the catalogue from both.
- Open/closed: a third shelf adds one variant and one line in route choice; a fourth token
  source adds one variant and one line in its ordering.
- Liskov: the in-process route is not a kind of socket route; the keyring shelf is not a
  kind of Vault shelf.
- Interface segregation: the shelf role declares the nine calls the counter makes today and
  nothing about tokens or sockets. Token custody has its own role.
- Dependency inversion: verb rules' Never-knows names the shelf variants; the command
  surface's names the route variants.

Open lookups, resolved in section 5:

- L1. Does the existing store protocol already match the shelf role's nine calls?
- L2. Where does the daemon's verb object live and can the in-process route construct it?
- L3. Does ostler parse anything from `list --json` beyond name and var?
- L4. Does the `keyring` library tell "locked" from "absent", and can plaintext backends
  be refused?
- L5. What does the Keychain ACL do for an item written by the `keyring` library?

Code paths that touch a value, by name, so the invariant can be audited:

| Path | Touches | Hands it to |
|---|---|---|
| `secret set` parser reading stdin | the typed value | verb rules |
| verb rules `set` | the value | shelf `set_value` |
| verb rules `fill` | the value, or the seed | code clock, then field typist |
| verb rules `env` | the bound values | the reply to `exec` only, over the in-process route or the socket |
| `exec` environment hand-off | the bound values | `execvpe` |
| `doctor` existence probe (keyring shelf) | each recorded value, read and discarded | nobody |
| Vault shelf read and write | values | hvac |
| Keyring shelf read and write | values | the keyring door |
| Token sources | the Vault token | the Vault shelf constructor |
| `serve --keep-token` reading stdin | the Vault token | the keyring door |

Nothing else may hold one, and none of these may log or print.

## 5. Mapping onto the existing system

Revision log:

- Section 2, the shelf: "Keyring door" split out of "Keyring shelf" after L4 showed the
  library raises distinct exceptions that key custody must also interpret.
- Section 4, route choice: added "explicit `SADDLEBAG_SOCKET` with no socket is an error"
  after reading `protocol.socket_path`, which honours that variable first.
- Section 3, invariant 2: added the `doctor` probe exception after deciding the catalogue
  records fields rather than probing them.

Parts:

- **The shelf**: Exists as `SecretStore` in `saddlebag/saddlebag/vault.py`, lines 20 to 31.
  L1: the protocol declares exactly the nine calls the role needs, and the fake in
  `tests/conftest.py` already implements it. Verdict for the role: Exists, but Reshape its
  home: a role that two variants implement should not live in one variant's module. It
  moves to `store.py`, with `vault.py` keeping the Vault variant. The Vault shelf: Exists.
  The keyring shelf, catalogue and keyring door: New, in `keyring_store.py` and
  `catalogue.py`. `Record`: Exists as `Secret` in `models.py`.
- **The counter**: Exists as `Daemon` in `daemon.py`, lines 61 to 230. L2: it is
  constructed from a store and a browser endpoint and holds no socket, so the in-process
  route can build one. Mismatch: its name and module say "daemon", and `verb_doctor`
  reports `vault_authenticated` and `~/.vault-token`, both Vault-shelf facts. Reshape: the
  class moves to `verbs.py` as the verb rules; `daemon.py` keeps `_bind`, `_answer`,
  `serve`. The health report grows `backend`, `route`, `token_source`, `catalogue_orphans`,
  `interpreter`, and `vault_authenticated` becomes `store_reachable` with the old key kept
  one release for callers (A8). Tag query and binding: Exist, as `models.matches` and
  `verb_env`.
- **Delivery**: Exists as `browser.py` and `totp.py` and `cmd_exec`'s `execvpe`. No change.
- **The route**: the socket route Exists as `protocol.send`; route choice and the in-process
  route are New, in `route.py`. Mismatch: `cli._ask` in `cli.py` line 33 calls
  `protocol.send` directly, so every command is wired to one variant. Reshape: `_ask` takes
  its reply from the chosen route. `cmd_serve` is the one command that bypasses the route.
- **Key custody**: Exists in part as the first thirty lines of `cmd_serve` (the refusal and
  the stdin read). Reshape into `custody.py` with the three sources and the refusal. The
  kept-token write is New: `serve --keep-token`.
- **The command surface**: Exists in `cli.py`. Grows `--keep-token` on `serve`, the new
  doctor lines, and the three keyring error texts.

Claims against the code: claim 8 is what the code does today and the design relaxes it;
claim 9 is what `vault.py` does and the design keeps it for that variant.

Lookups:

- L3: `ostler/ostler/environments/secrets.py` lines 118 to 135 read `secrets[].name` and
  `secrets[].var` and nothing else, and run `saddlebag exec --tag ... --`. Both routes
  must therefore keep the exit code, the JSON shape and the `exec` flags unchanged, and
  they do.
- L4: the `keyring` library raises `NoKeyringError` when no backend is viable and
  `KeyringLocked` when the Secret Service collection is locked and the unlock prompt was
  dismissed or impossible (headless). Plaintext backends live in the separate `keyrings.alt`
  package; the door refuses any backend outside the allowed set by name, so an installed
  `keyrings.alt` is never chosen (A4). A macOS item written by another application raises
  a generic `KeyringError` on denial; the door maps that to "distrusted".
- L5: the `keyring` macOS backend creates items through the Security framework, so the
  creating application, the Python interpreter binary of saddlebag's venv, is in the item's
  trusted list. The same binary reads without a prompt. A replaced interpreter is a new
  application: each item prompts once, and "Always Allow" adds the new binary to that item.
  Pre-authorisation exists through `security add-generic-password -T <interpreter> -U` per
  item, which only the operator runs; `doctor` prints the interpreter path on macOS so the
  operator has the argument (A5).

What the existing system has that the design lacks: nothing. The `ping` verb stays as the
daemon's liveness check, used by route choice to confirm a socket answers (it is a better
probe than a bare connect, since it also returns the daemon's version).

Repo structure: the member README's `## Map` and `Package layout` sections must gain the
new modules, under the `codebase-map` rule. `hvac` stays a hard dependency but is imported
inside the Vault shelf, so a venv missing it still runs every keyring-route verb and fails
`serve` with "hvac is not installed" instead of killing the whole command at import, which
is the failure on this machine today (A6). `keyring` becomes a hard dependency with the
`secretstorage` extra on Linux.

## 5b. What must not move

| Receiver | Gets today | Enforced by | Before | Holds when |
|---|---|---|---|---|
| ostler stack bring-up | `list --json` with `secrets[].name` and `.var`, exit 0 | `ostler/tests/test_environments.py` on a fake runner; no saddlebag test pins the JSON shape | the six keys in `Secret.to_dict`, `tests/test_vault.py` | identical keys and types from both routes |
| ostler stack bring-up | `saddlebag exec --tag K=V -- cmd` runs cmd with the var set | `test_cli.py` exec tests | passes | unchanged flags, exit 127 on a missing command |
| the agent reading errors | the error lines in the operator skill's table | `test_daemon.py`, `test_cli.py` match on substrings | 102 tests pass in 10.1 s | every listed line unchanged; new lines added only |
| the agent | `no saddlebag daemon on <path>: start one with saddlebag serve` when nothing answers | `test_cli.py` | present | still printed when the route is `daemon` by setting or by `SADDLEBAG_SOCKET`; in auto mode the keyring route takes over and this line is not seen |
| the operator | `serve` exits 2 with `VAULT_TOKEN` set | `test_cli.py` | present | unchanged |
| the operator | `doctor` exits 1 when a secret has no value, 0 otherwise | `test_cli.py` | present | unchanged, with the new warnings not affecting the code |
| a container | finds the daemon through `SADDLEBAG_SOCKET` | `test_protocol`-style socket path tests | present | unchanged, and a set variable never silently becomes the keyring route |
| the test suite | swaps the store through the protocol | `conftest.FakeVault` | 102 pass | the fake implements the moved protocol unchanged |
| the ad hoc operator | time to first `fill` | nothing | not measured: today it is the time to start Vault and the daemon, minutes (A2) | one process, under a second plus the browser round trip |

The last row is enforced by nothing and the design keeps it on purpose: it becomes the
"ad hoc path stays cheap" force, with the catalogue-not-probe decision as its carrier.
The fourth row changes a behaviour on purpose: in auto mode with no socket, the agent no
longer sees the "start one" line. The skill's error table gains the keyring lines, and
that edit belongs to the last slice.

## 6. Slices

1. **Keyring route, `secret create`, `secret set`, `list`, `fill`.** Parts: shelf (role
   moved, keyring shelf, catalogue, keyring door), counter (verb rules moved), route (in-
   process, choice with env var only), command surface. Done when: on this laptop with no
   socket, `secret create`, `secret set` on stdin, `list --tag`, `list --json` and `fill`
   into a page over CDP work with no prompt; the suite still passes with the fake store;
   every row of 5b is re-measured and holds, with the fourth row's auto-mode exception
   stated.
2. **`exec`, `tags`, `secret unset/remove/tag/untag`, `doctor` in keyring mode.** Parts:
   counter (binding, health report), delivery (environment hand-off). Done when: ostler's
   bring-up against a local stack runs under `saddlebag exec` with no daemon; `doctor`
   reports `backend: keyring`, `route: in-process`, orphans and missing values, exit codes
   as before; 5b re-measured.
3. **Route choice completed, the config key and the daemon error paths.** Parts: route
   (preference, socket detection by `ping`), command surface. Done when: `SADDLEBAG_BACKEND`,
   the `[saddlebag] backend` key of the shared `config.toml` and auto-detect pick as
   section 4 says, on a Linux path and a macOS path in the tests; `SADDLEBAG_SOCKET` with no socket
   errors; a running daemon is used when it answers; 5b re-measured.
4. **Key custody.** Parts: key custody, health report, command surface (`serve
   --keep-token`). Done when: `serve` starts from the kept token with stdin a terminal,
   from a piped token when piped, and from the 0600 file otherwise; `doctor --json` names
   the source and warns on the file; `VAULT_TOKEN` is still refused; 5b re-measured.
5. **Headless and macOS behaviour, the docs.** Parts: keyring door, health report, the
   operator skill and `docs/SECURITY.md`. Done when: over SSH with gnome-keyring locked each
   verb prints the locked line; with no session bus the absent line; on macOS a value
   saddlebag stored is read back with no prompt and `doctor` prints the interpreter path;
   the skill's error table and the security doc describe both shelves; `make agent-check`
   passes; 5b re-measured.

What `doctor` prints per mode, fixed here so the slices agree:

| Line | keyring route | daemon route |
|---|---|---|
| `backend` | `keyring` | `vault` |
| `route` | `in-process` | `socket <path>` and the daemon's version |
| `store reachable` | the keyring door's outcome | Vault authenticated |
| `secrets without a stored value` | from the catalogue | from Vault |
| `orphan keyring items` | items with no record | not applicable |
| `token source` | not applicable | `stdin`, `keyring` or `file <path>` with a warning on `file` |
| warnings | `~/.vault-token` exists; catalogue drift | `~/.vault-token` exists; token in a file |
| macOS only | `interpreter <path>` | not applicable |

The error texts, fixed here so the slices agree:

- Locked: `the OS keyring is locked. Unlock it (desktop: answer the prompt; SSH: pipe your
  login password to gnome-keyring-daemon --unlock), or start a daemon with saddlebag
  serve and set SADDLEBAG_BACKEND=daemon.`
- Absent: `no OS keyring on this session: no Secret Service on the session bus and no
  Keychain. Run saddlebag from a desktop session, or start a daemon with saddlebag serve
  and set SADDLEBAG_BACKEND=daemon.`
- Distrusted (macOS): `the Keychain refused this interpreter (<path>) for <name>. Choose
  Always Allow in the Keychain prompt, or pre-authorise it with security
  add-generic-password -T <path> -U -s stablemate-saddlebag -a <name>/<field>.`

## 7. Assumptions

Ordered by the cost of being wrong.

- **A1.** Assumption: a same-user process reading the OS keyring is inside the threat model's
  accepted exposure, as `~/.vault-token` and the socket already are. Decided: the keyring
  shelf is a peer of the Vault shelf, not a lesser one. Basis: `saddlebag/docs/SECURITY.md`,
  "The threat". If wrong: section 1 out of scope, invariant 6, and the whole keyring shelf.
- **A2.** Assumption: the operator's time to first `fill` today is dominated by starting Vault
  and the daemon, minutes not seconds. Decided: the "cheap ad hoc path" force and the
  catalogue-not-probe choice. Basis: the task's description of today's steps; not
  measured. If wrong: section 4 catalogue fields decision only.
- **A3.** Assumption: one metadata file for both platforms is worth more than a Linux-only
  attribute search. Decided: sidecar catalogue, no item attributes. Basis: the `keyring`
  library exposes no attributes on either platform; macOS Keychain has no attribute search
  usable without a custom Security-framework binding. If wrong: section 2 catalogue and
  section 4's second pattern.
- **A4.** Assumption: refusing backends by class name is enough to exclude every plaintext
  backend the `keyring` library could pick. Decided: an allow-list in the keyring door.
  Basis: the library's documented backend selection by priority and `keyrings.alt` being
  the only plaintext family. If wrong: invariant 6 needs a different guard.
- **A5.** Assumption: the `keyring` library's macOS backend creates items the same
  interpreter can read back with no prompt, and a reinstalled interpreter prompts once per
  item. Decided: no `-T` pre-authorisation in code, only the printed path. Basis: the
  Security framework's ACL model as documented; not tested on a Mac in this session. If
  wrong: slice 5 gains a `saddlebag keyring trust` verb that shells out to `security`.
- **A6.** Assumption: `hvac` import failure is what breaks `~/.local/bin/saddlebag` today, and
  a lazy import is enough. Decided: lazy import, `hvac` stays a dependency. Basis: the
  task's words "fails with a missing hvac module"; the pipx venv was not inspected. If
  wrong: section 5 dependency paragraph.
- **A7.** Assumption: no machine holds Vault secrets that must become keyring secrets in
  this change. Decided: no copy command. Basis: the task says the daemon path is unused on
  this machine. If wrong: a sixth slice, `secret copy --to`, which moves values through
  memory only.
- **A8.** Assumption: no consumer reads `doctor --json`'s `vault_authenticated` key besides
  the saddlebag tests. Decided: rename to `store_reachable`, keep the old key one release.
  Basis: grep of ostler and workhorse finds no `doctor` call. If wrong: keep both keys.
- **A9.** Assumption: Windows is not a target. Decided: the door's allow-list names the
  Secret Service and macOS backends only. Basis: none beyond the task's two platforms. If
  wrong: one line in the allow-list.
- **A10.** Assumption: `platformdirs.user_state_dir("stablemate")/saddlebag/` is the right
  home for the catalogue and the filed token on every platform, beside ostler's state.
  Decided: both there, 0700 directory, 0600 files, never a literal `$XDG_STATE_HOME`.
  Basis: `ostler/ostler/environments/runtime.py` line 42 and `saddlebag/protocol.py`
  already resolve directories through platformdirs. If wrong: two paths in section 4.
- **A11.** Assumption: the shared stablemate `config.toml` accepts a `[saddlebag]` table
  without a change to `stablemate_core`'s loader. Decided: the backend preference lives
  there, not in a saddlebag-only file. Basis: `stablemate_core/config.py` line 70 names the
  file; whether unknown tables pass its validation was not read. If wrong: saddlebag reads
  the same file itself for its own table.
