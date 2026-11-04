# One personal setup across Claude, Codex and OpenCode

Disclosure: I read farrier's install code, your home directories and the harness docs before
this method loaded. Sections 1 to 4 were then checked against the test "would I name this
without having seen the solution?". Design decisions that reached me that way are claims in
section 1b.

## 1. Problem

You move between Claude, Codex and OpenCode, and each one behaves like a different colleague.
Codex has none of your rules, none of your safety guards and neither of your helper agents.
OpenCode has your rules only by accident, through a fallback, and has no guards.

Done means one command gives all three harnesses the same setup:

- A new session on any harness follows the same rules.
- `cat .env` is denied on all three, and adding a code comment is denied on all three.
- "Use the `lookup` agent" works on all three, on that harness's cheap model.
- Playwright and Maestro are available in every project on all three.
- A check command says what drifted and which guards still wait for your approval.

Out of scope:

- Permissions and allow rules, because the three models do not translate safely.
- Default models and effort, because each harness keeps its own.
- Claude plugins and per-project memory.
- Copilot, which stays at skills only.
- Project trust lists, login and credentials.

## 1b. Claims

1. Global instructions render through the existing root mechanism (farrier `roots`).
2. Agent models come from the workhorse delegate roles (`CLAUDE.md`, model routing section).
3. A guard written for Claude can serve other harnesses (saddlebag guard passed a Codex-shaped call).
4. Codex hooks need your approval and must not be approved by a tool (Codex docs, my recommendation).

## 2. Parts and concepts

**Level 1.**

- **The personal setup** is what you author once: rules, guards, helpers and tool servers. It
  never knows any harness's file format. It hands its records to Choosing.
- **Choosing** decides which harness gets which record. It never knows file formats. It hands
  a per-harness list to Translating.
- **Translating** turns a record into what one harness reads. It never touches the disk. It
  hands intended content to Placing.
- **Placing** writes into a home that other programs also write to. It never knows what a
  guard or an agent means.
- **Guarding** is the running guard deciding one tool call. It never knows how it was installed.
- **Reporting** compares the intended setup with the home and says what differs. It never
  writes.

Flow: at install, setup → choosing → translating → placing. At check, the same chain ends in
reporting. During a session, the harness calls guarding, with no other part involved.

**The personal setup**

| Concept | Owns | Never knows |
|---|---|---|
| Rule text | The words of your always-on rules | Which file holds them |
| Guard record | Which tool kinds a guard watches, and its command | Each harness's tool names |
| Helper agent | A role's description, prompt and read-only flag | Model names |
| Tool server | A server's launch command and environment | Each harness's config spelling |

**Choosing**

| Concept | Owns | Never knows |
|---|---|---|
| Bundle | A named set of records selected together | Harnesses |
| Harness selection | Which bundles one harness takes | Record contents |
| Harness exception | A guard's list of harnesses it cannot serve | Why another harness can |

**Translating**

| Concept | Owns | Never knows |
|---|---|---|
| Harness dialect (role) | The translation of each record kind for one harness | Disk state |
| Claude dialect (variant) | Claude's spellings | The other dialects |
| Codex dialect (variant) | Codex's spellings | The other dialects |
| OpenCode dialect (variant) | OpenCode's spellings, including the guard bridge | The other dialects |
| Role model | The model one harness uses for one role | Agent prompts |

**Placing**

| Concept | Owns | Never knows |
|---|---|---|
| Whole-file target (variant) | A file farrier alone writes | Record meaning |
| Merged-entry target (variant) | One named entry inside a file another program owns | Other entries |
| Install ledger | Which merged entries and untagged files farrier installed | Their meaning |

**Guarding**

| Concept | Owns | Never knows |
|---|---|---|
| Tool call | One call in a shape every guard reads | Which harness sent it |
| Guard bridge | Calling a guard command from a harness with no command hooks | The guard's rule |
| Verdict | Allow or deny, with the reason | Harness output format beyond the shared one |

**Reporting**

| Concept | Owns | Never knows |
|---|---|---|
| Drift | The difference between intended and installed | How to fix it |
| Pending approval | Guards Codex will skip until you approve them | The approval hash formula |

## 3. Invariants

1. Farrier never changes or removes a value it did not install. Owner: Install ledger. Merged-entry target upholds it.
2. A foreign entry with the same name and a different value stops the install and names the entry. Owner: Merged-entry target.
3. Comments and unrelated keys in a shared config survive an install byte for byte. Owner: Merged-entry target.
4. A guard installed on a harness denies there what it denies on Claude. Owner: Tool call, proven per dialect.
5. A guard is never installed where it would block ordinary work. Owner: Harness exception.
6. Farrier never grants Codex hook approval. Owner: Pending approval.
7. The check command writes nothing. Owner: Drift.

## 4. Forces and patterns

Forces:

- The file formats vary per harness, and independently of what is being declared.
- Harnesses will grow. OpenCode was added mid-design, which is the proof of the force.
- Harness home files are written by running programs, so a whole-file rewrite loses data.
- Guard rules must not fork per harness, because a fork lets one harness fall behind.

Patterns:

- **Between parts:** a sequence of stages with one value handed along. Force: install and check share all stages but the last.
- **Dialect:** a role with one variant per harness, chosen in one table. Force: formats vary. A new harness adds one concept and one table line.
- **Placement:** a role with two variants. Force: some files are ours and some are shared.
- **Tool call:** a shared plain value, with the Claude shape as the shape. Force: guards must not fork. The Claude shape is the only one with existing consumers, and Codex already sends it apart from patches.
- **Guard record:** names tool kinds (shell, edit, read, search). Force: tool names vary per harness.

Claims:

- Claim 1 is re-derived. Rule text is a record like any other, and the existing mechanism holds it after one refusal is removed.
- Claim 2 is re-derived. The same roles need the same models, so a second map would drift.
- Claim 3 is re-derived with a limit: two of three guards need work. See section 5.
- Claim 4 is kept. Approval is a safety boundary, and it belongs to the person it protects.

SOLID check: every Owns reads without "and" apart from Guard record's "kinds and command", which
is one declaration. A new harness adds one dialect and one table line. Consumers depend on the
roles. No changes needed.

## 5. Mapping onto the existing system

Revision log:

- Section 2, Placing: added the OpenCode whole-file route after a test showed OpenCode merges `opencode.json` over `opencode.jsonc`.
- Section 2, Placing: slice 5 made `opencode.json` a merged entry with the ledger instead of a whole file, so an entry farrier did not install stays protected and a dropped server leaves. `opencode.jsonc` is only read, and a differing entry there stops the install.
- Section 2, Harness exception: added after the timeout guard blocked a plain `ls` from Codex.

| Item | Verdict | Where and why |
|---|---|---|
| Rule text | Exists | `library/roots/<name>.md`. The rule refusal at `farrier/farrier/outputs.py:459` must go, because its reason is false. |
| Guard record | New | `library/hooks/<name>/`, script beside its record, installed to `~/.agents/hooks/<name>/`. |
| Helper agent | New | `library/agents/<name>.md`. |
| Tool server | New | `library/mcp/<name>.yml`. |
| Bundle | Exists | Packs. A pack named in each harness table is your one list. |
| Harness selection | Reshape | `Selection` in `core/stablemate_core/schema/selection.py` gains `hooks`, `agents` and `mcp`. A repo `agents.yml` naming one is refused. `selected no skills or prompts` must accept them. |
| Harness exception | New | Field on the guard record. |
| Dialects | Reshape | `USER_HARNESS_DIRS` in `renderer.py` maps a harness to one folder. OpenCode needs `.config/opencode` and installs no skills, because it already reads `~/.claude/skills`. |
| Role model | Exists | `[profiles.<harness>.delegates]`. Claude has it. Codex and OpenCode have none today. |
| Whole-file target | Exists | `install_outputs`, tagged by `ownership.py`. |
| Merged-entry target | New | `tomlkit` is already a dependency for `config.toml`. |
| Install ledger | New | `~/.agents/.farrier-home.json`. JSON cannot carry the generated mark. |
| Tool call | Reshape | The no-comments guard reads `file_path` and misses Codex patches. It must parse `tool_input.command` for `apply_patch`. |
| Guard bridge | New | Generated `~/.config/opencode/plugins/farrier-guards.ts`. It runs on `tool.execute.before`, sends the Claude shape to each command and throws on a deny. |
| Drift | Exists | `check_outputs` covers whole files and gains merged entries. |
| Pending approval | New | Reads `[hooks.state]` in `~/.codex/config.toml`. |

Where each record lands:

| Record | Claude | Codex | OpenCode |
|---|---|---|---|
| Rules | `~/.claude/CLAUDE.md` | `~/.codex/AGENTS.md` | `~/.config/opencode/AGENTS.md` |
| Guards | `hooks` entries in `~/.claude/settings.json` | `~/.codex/hooks.json` | Generated plugin |
| Agents | `~/.claude/agents/*.md` | `~/.codex/agents/*.toml` | `~/.config/opencode/agents/*.md` |
| MCP | `mcpServers` in `~/.claude.json` | `[mcp_servers.*]` in `config.toml` | `mcp` in generated `opencode.json` |

Guards per harness:

| Guard | Claude | Codex | OpenCode |
|---|---|---|---|
| Secrets guard | Yes | Yes, unchanged (tested) | Yes, through the bridge |
| No comments | Yes | Yes, after it learns patches | Yes, through the bridge |
| Timeout | Yes | No, Codex sends no timeout | Yes, OpenCode's bash takes `timeout` (L1) |

The existing system has things the design lacks:

- `saddlebag guard install` also writes `settings.json`. It is a second writer of one entry, not waste. Invariant 2 catches a difference, and you stop using it for your home.
- `skills_from` links are a repo feature, and this design does not need them.

Lookups:

- **L1:** does OpenCode's bash tool take `timeout`? It decides whether the timeout guard installs there. Resolved in slice 5: it takes `timeout` in milliseconds. A real session retried with it after the guard denied the first call, so the guard installs there.
- **L2:** what does the `@` in `@gpt-6-sol` mean in a profile? It decides how Codex model names render. Resolved in slice 4: workflow runs drop everything up to the `@`, and agent files do the same.

## 5b. What must not move

| Receiver | Gets today | Enforced by | Before | Holds when |
|---|---|---|---|---|
| You on Claude | Three guards fire | Nothing | 3 hooks in `settings.json` | Same 3 deny the same probes |
| You on Claude | Other settings kept | Invariant 3 | 14 top-level keys | Same 14, same values |
| Claude Code | `~/.claude.json` state kept | Invariant 3 | 0 user servers, project entries present | Only `mcpServers` differs |
| Your Codex config | Trust, plugins, comments kept | Invariant 3 | 23 KB file | Only `mcp_servers` entries differ |
| Codex desktop | `node_repl` works | Invariant 1 | Present | Unchanged |
| Your OpenCode config | Long comments kept | Invariant 3 | 11,534 bytes | Identical bytes |
| Codex workflow runs | No personal rules or guards | Nothing | 0 bytes, 0 guards | Rules 6 KB (about 1,500 tokens a turn) and guards after approval, accepted (A2) |
| Codex workflow runs | Named delegates | Nothing | No delegates in the codex profile | Offered `worker` and `lookup`, accepted (A3) |
| Live client coder run | Reads your homes | Nothing | Running now | No real-home install while it runs (A5) |
| User-scope check | Reports skill drift | Tests | Exit 1, home skills behind the library | Same report plus the new records |
| Instruction budget | Below the Codex limit | Nothing | 17 KB of 32 KB with this repo's `AGENTS.md` | Under 32 KB |

## 6. Slices

Every slice updates the book, runs `make lint` and farrier's tests, and re-measures section 5b
in a temporary home.

1. **Rules reach Codex.** Rule text → Claude and Codex dialects → whole-file target. Done when a real `codex exec` in a temporary `CODEX_HOME` quotes a rule, and the check passes then fails after an edit.
2. **Same MCP servers.** Tool server → merged-entry target → ledger. Done when both harnesses list the servers, `node_repl` and all comments survive, a foreign `playwright` value stops the install, and removing a server deletes only ours.
3. **Guards on Codex.** Guard record, patch parsing, pending approval. Done when a real Codex session denies `cat .env` and a comment patch, runs `ls`, and the check named the guard as pending before approval.
4. **Helper agents.** Helper agent, role model. Done when a real Codex session spawns `lookup` on the configured model.
5. **OpenCode.** One dialect and the bridge. Done when a real OpenCode session passes the same probes as slices 1 to 4, and `opencode.jsonc` is byte-identical.
6. **Move your real setup.** Copy your rules, agents, guards and servers into `agent-library`, then install. Done when the probes pass in your real homes and the Claude row of section 5b holds. Done on 2026-11-04 during a live client run, on the user's word. Claude passes every probe. Codex passes rules, servers and helper, and its guards wait for the user's approval in `/hooks`. OpenCode passes rules, servers and guards, and its helper's Kimi model is out of monthly quota.

## 7. Assumptions

1. **Assumption:** a running Claude session will not overwrite an MCP entry written beside it. **Decided:** read, change one key, rename atomically, and let the check catch a lost write. **Basis:** none. Claude rewrites `~/.claude.json` often. **If wrong:** Merged-entry target, switching to `claude mcp add`.
2. **Assumption:** you want your rules in Codex and OpenCode workflow runs as well. **Decided:** no run-time exclusion. **Basis:** your rules say a run's own prompt outranks routing, and Claude runs already load them. **If wrong:** Harness selection, and row 7 of section 5b.
3. **Assumption:** workflow runs may use the delegates you add for Codex and OpenCode. **Decided:** one model map. **Basis:** `CLAUDE.md` says the agent names match the delegate roles so both route alike. **If wrong:** Role model gains its own table.
4. **Assumption:** `lookup` cannot be enforced as read-only on Codex, because agents inherit the sandbox. **Decided:** the prompt says read-only, and Claude and OpenCode enforce it. **Basis:** Codex subagent docs. **If wrong:** Codex dialect.
5. **Assumption:** the live client run ends before slice 6. **Decided:** slices 1 to 5 use temporary homes only. **Basis:** process 12836 was live. **Proved false:** the user had slice 6 run during it. The user had the run stopped on 2026-11-04. The old `~/.claude/hooks` scripts stay on disk until every desktop session started before the move has restarted, because those sessions may still call them. Config keys are safe, because the schema allows unknown keys.
6. **Assumption:** the OpenCode bridge sees `filePath`, `oldString`, `newString` and `content`. **Decided:** map these to the Claude names. **Basis:** slice 5 confirmed these names in real `bash`, `read`, `grep`, `edit` and `write` calls. `apply_patch` takes `patchText` in the OpenCode binary's tool schema and was not seen in a real session, because OpenCode offers it only to GPT models. **If wrong:** Guard bridge.
7. **Assumption:** Codex's approval hash cannot be recomputed. **Decided:** the check reports a missing approval, and install prints a reminder when a guard changes. **Basis:** the formula is undocumented. **If wrong:** Pending approval gets stronger.
8. **Assumption:** you stop editing `~/.claude/CLAUDE.md` directly after slice 6. **Decided:** the check reports such an edit as drift. **Basis:** your choice of the private library. **If wrong:** Choosing needs an import path.
