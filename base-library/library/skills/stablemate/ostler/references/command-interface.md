# Ostler command interface

The CLI half of [`ostler`](../SKILL.md) — every command, its flags, and the JSON each returns.
Reached when you are writing a shell step, a gate, or a prompt that drives ostler from the
command line. A `workhorse` workflow script does **not** come here: it commands the graph
in-process through [python-api.md](python-api.md).

All read commands accept `--json`. Mutating commands allocate ids as needed and write canonical
markdown in place.

**Global**: `ostler --version`, `ostler -C/--chdir DIR <command> …`, `ostler --handles|--full-ids …`

**Short handles.** An id is `<PREFIX>-<26-char ULID>`; ostler abbreviates it git-style to
`<PREFIX>-<6+ chars>` — the shortest slice unambiguous in this repo. Human output prints handles by
default, `--json` prints full ids (a program wants the identity that never changes); `--handles` /
`--full-ids` override either. A handle is accepted **wherever a command takes an id**, in either
mode — `trace`, `query`, `create story --covers`, `seed add/remove`, `backlog prune`,
`freeze`/`unfreeze` — so a token copied out of one command goes into the next. Never write a handle
into a document: it lengthens as soon as a colliding id is minted. From Python, `okf.handle(id)` /
`okf.handles()` render and `okf.expand(token)` resolves.

**Inspect**
```bash
ostler doctor [--epic SLUG] [--json] [--no-schema]   # conformance + referential integrity; non-zero on a break
ostler trace  <id|slug|surface|path>                 # walk the graph from any node
```

**Retrieve**
```bash
ostler list   --type epic|story|knowledge|feature|spec|seed [--epic E] [--status S] [--json]
ostler search <query> [--type T] [--json]                         # full-text match over node prose
ostler query  stories-covering-seed|surfaces-referenced-by-story <arg> [--json]
ostler graph  [selectors…] [--tree|--ids|--json]     # query the node/edge/bullet graph
```

`ostler graph` is the **structural** query `search` can't do — it walks the *typed, nested* node
tree (every node carries its `- key: value` bullets, its resolved out-edges, and its
`title_path`/`type_path` hierarchy), so you filter precisely instead of by prose, **without `jq`**.
Selectors compose (AND); output is `--tree` (default), `--ids`, or `--json`:

```bash
ostler graph --surface SVC                       # the whole service, as an outline tree
ostler graph --path 'concept:agent / field:timeout'   # relative hierarchy query (/ =descendant, > =direct)
ostler graph --type field --under <id> --depth 1 # a node's direct children of a type
ostler graph --bullet 'code=mod.py::Sym' --ids   # dedup: is this symbol already grounded?
ostler graph --has-bullet code                   # coverage: every grounded node
ostler graph --orphans                           # nodes no edge points to (unreachable)
```

- **dedup before you scaffold** — `--bullet 'code=<symbol>'`: if a node already grounds it, enrich
  that node, don't make a second one. (`--path` for "does *this* nested node already exist?")
- **inventory coverage** — `--has-bullet code` lists every grounded node; diff against source symbols.
- **orphans** — `--orphans` is unreachable nodes, first-class (no `jq` walk).
```bash
ostler next-epic [--json]                            # next queued epic with unfinished work
ostler next-story <epic> [--json]                    # next runnable story (deps satisfied, not done)
ostler path epic <epic> | spec <slug> | story <epic> <slug> | branch <slug> [--epic] [--is_epic emits feat/<slug>]
```

Epic directories are numbered in creation order — `create epic checkout-flow` writes
`docs/epics/0001-checkout-flow/` — so ask `path epic` instead of joining `docs/epics/<slug>`.
The number orders the listing and is **not** the identity (that is the minted `id`), so every
command still takes the bare slug, and `path branch` drops it (`feat/checkout-flow`).

**Mutate** (allocates ids, writes markdown)
```bash
ostler create epic    <name>  --title T [--prefix P] [--json]
ostler create story   <epic> <slug> --title T [--covers a,b] [--depends a,b] [--prefix P] [--json]
ostler update story   <slug> --title T --covers a,b --depends a,b
ostler create feature <slug>  --title T [--area A] [--route R] [--prefix P] [--json]
ostler delete epic|story|feature <name>

ostler seed add    <epic> <id> [--status S] [--summary …] [--surface …] \
                               [--legacy-surface …] [--backing …] [--prerequisites …] [--source-bullet …]
ostler seed remove <epic> <id>
ostler set-status  <story> <status>

ostler backlog add <id> <text> [--section S] | ostler backlog prune <id> | ostler backlog list [--json]
ostler todo add <epic> [--front] | ostler todo prune <epic> | ostler todo reorder <e…> | ostler todo list [--json]
```
`create … --json` returns `{"ok": true, "id": "<allocated-id>", "name": "<name-on-disk>", "message": "…"}`
— for `create epic`, `name` is the numbered directory it wrote; read it back rather than guessing the number.

**Repair / approve**
```bash
ostler edit relink    <old-path> <new-path> [--write]
ostler edit rename    <old-slug> <new-slug> [--write]
ostler edit settle-review <slug> [--write]
ostler freeze   <ident> [--by WHO] [--note …]   # pin an approved story/seed as immutable ground truth
ostler unfreeze <ident>
```

**OKF UI profile** (surfaces / elements / behaviors — see "The OKF UI profile" below)
```bash
ostler scaffold <type> <name> [--service SVC] [--in FILE] [--title T] [--json]  # new node, canonically placed
ostler fmt [PATH…] [--check]              # canonicalize frontmatter/bullets/headings; --check = no writes, exit 1 if unclean
```

**Visual-fidelity check** (used by `coder`'s QA gates — see [[coder-workflow]])
```bash
ostler vet <screenshot> --manifest M (--cdp-url U | --regions FILE) --slug S [--state s] [--iou-threshold 0.5] [--json]
```

**QA context and execution control plane**
```bash
ostler qa context --base REV [--head REV|WORKTREE] --spec DIR \
  --source-root SURFACE=PATH [--source-root SURFACE=PATH ...] \
  [--story-file PATH] --json
ostler qa context-validate --spec DIR --json
ostler qa validate DIR/qa_plan.py --spec DIR --json
ostler qa run DIR/qa_plan.py --spec DIR --json
```

`qa context` writes `qa-okf-context.json` and its Markdown rendering beside the plan.
Blocking unmapped production changes use a nonzero process exit but still produce JSON;
workflow adapters must route that as `invalid`, not crash. Plan validation reports
`passed|invalid`. Execution reports `passed|failed|blocked|invalid` and owns deletion and
recreation of `qa/`, service/driver cleanup, `qa-run.ndjson`, `run-manifest.json`, and
evidence. `qa_plan.py` and static `qa-inputs/` remain outside disposable `qa/`.

A browser scenario also leaves `qa/traces/<scenario>-diagnostics.json` (manifest kind
`browser-diagnostics`) — the whole console and the whole network for that scenario, every
record stamped with `atMs`, the run-relative offset `qa-run.ndjson` also carries, so the two
read against each other:

| Key | Holds | Why it exists separately |
| --- | --- | --- |
| `schema` | `"browser-diagnostics/1"` | a trace left by an older driver has a different shape; without this the mismatch is only a jq crash, and the plan gets repaired toward the stale shape |
| `console` / `consoleCount` | every message, with `type`, `text` and `url:line:col` | the `warn`-level hydration or key warning that explains a failure is not an error |
| `consoleErrors` | error-level text only | legacy, predates `console`; kept because plans assert on it — prefer `console` |
| `pageErrors` | uncaught exceptions (`name`, `message`) | `pageerror` is a *different event* from the console; a throw during hydration is in no other key |
| `requests` / `requestCount` | every request issued | a request in here with no response and no failure was still in flight — a hung endpoint is in no other key |
| `responses` / `responseCount` | every response, with `status` | the only place a status appears; `[.responses[] \| select(.status >= 500)] \| length == 0` is how a 5xx is caught |
| `failedRequests` | requests that never completed, with `errorText` | `requestfailed` never fires for a completed 5xx; gate on `select(.errorText != "net::ERR_ABORTED")` or an app cancelling its own fetch goes red |

`console`, `requests` and `responses` are capped at 500 records and the `*Count` key reports
the true total — compare them before reading a list as complete. `pageErrors` and
`failedRequests` are uncapped. No response body and no headers are here; assert on those
through a `command` step with `expect_http`. Full reference: stablemate's
`ostler/docs/QA-RUN.md`.

**Schema-checked workflow artifacts** (a workflow's plan/review/qa docs under `docs/specs/<slug>/`)
```bash
ostler artifact scaffold <kind> --spec DIR [--force]   # write the kind's skeleton into the spec dir
ostler artifact vet      <kind> --spec DIR [--json]    # validate the artifact against its contract
ostler artifact list     [--json]                      # show registered artifact kinds
```

