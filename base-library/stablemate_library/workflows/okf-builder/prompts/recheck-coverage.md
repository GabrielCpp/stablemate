---
agent: agent
---

# okf-builder — coverage re-scan (the exhaustiveness backstop)

The worklist drained and `ostler doctor` is clean. Before finishing, **prove the book is complete**:
re-enumerate from code and from the graph, find anything the crawl missed, and queue it. Also queue
the **journeys** once the nodes exist. This is the backstop that makes the build exhaustive rather
than best-effort.

Load the method: {{ skill_load_ref("stablemate-okf-modeling", skill_dir() + "/stablemate-okf-modeling/SKILL.md") }}

**Guardrails (unattended):** you may run read-only `ostler` (graph/list/trace/doctor) and read code,
but do **not** modify code, run `git`, or run builds/tests. Queue work by returning items; don't
author nodes yourself this turn. Stay inside the service's own source.

**Query the graph, don't grep it.** `ostler graph --surface ‹service›` is the source of truth for
what's documented: `--has-bullet code` lists every grounded node (diff against the mechanical source
inventory), `--orphans` lists unreachable nodes, `--bullet 'code=<symbol>'` checks a single symbol,
`--type field|method|concept` scopes by kind. Use it instead of grepping `docs/`.

## Inputs

- service: `{{ workhorse_var('service') }}` — features root: `{{ workhorse_var('features_root') }}`
- repo root: `{{ workhorse_var('repo_root') }}`
- source root: `{{ workhorse_var('source_root') }}`
- excluded source paths: `{{ workhorse_var('source_excludes') }}`
- mechanical source inventory: `{{ workhorse_var('source_inventory_path') }}`
- inventory errors (must be empty before declaring coverage): `{{ workhorse_var('inventory_errors') }}`

## Checks — emit an item for every gap you find

1. **Code inventory — the exhaustiveness floor (do this first, most rigorously).** Entry-point
   descent alone always misses siblings and non-entry modules; this diff is what makes the book
   *complete* rather than merely reachable. Read the complete, deterministic inventory at the
   supplied `source_inventory_path`; do not replace it with a sampled grep. It inventories modules
   plus public Python `class`/`def`, exported Go `func`/`type ... struct|interface`, and exported TS/TSX
   `function`/`class`/`interface`/`type`/`const`/`enum` declarations under the explicit source root,
   excluding tests, generated output, dependencies, and build artifacts. Then get **every**
   grounded symbol from the graph:
   `ostler graph --surface ‹service› --has-bullet code --json` (their `code:` bullets). A code unit
   counts as **covered** only if it has its own node
   **or** is explicitly folded into a documented behavior's `does:` / a concept's parts. Queue every
   uncovered unit — and watch for the two blind spots that motivated this check:
   - **Every implementation of an interface / ABC is its own node.** If the code has N subclasses of
     a base but the graph documents fewer, queue the missing ones. (e.g. an `AgentBackend` base with
     `Claude`/`Codex`/`Copilot`/`OpenCode`/`Aider` subclasses ⇒ **five** sibling `concept`s, not one
     with the rest named in prose.)
   - **Utility / library modules never reached from an entry point** are still surfaces of the
     service — queue them. (e.g. a `scriptutil`/`sdk` helper module imported by *other* tools.)
   Map each: class/module → `concept`, data shape → `format`, command/route/control → `element`.
2. **Missing from surfaces** — re-enumerate each surface's elements (every command / endpoint /
   control) and diff against `ostler list`. Any un-documented surface or element → its item.
   A web GUI's server node is incomplete unless it has top-level `launch`, `working-directory`,
   `entry-url`, `health-path`, and unique response-body `identity` bullets that can start and verify
   the app locally; requeue that server when any field is absent.
3. **Orphans** — `ostler graph --surface ‹service› --orphans` lists nodes no graph edge points to.
   Repair only top-level/file nodes and independent surface elements that should be reachable from
   a surface root. Ignore nested `field`/`method` members (and other typed sections already contained
   by a documented parent); their parent containment is the structural pointer, and giving every
   member an artificial inbound link creates redundant work rather than reachability.
4. **Stubs / below-bar** — scan documented nodes for incompleteness (a lone `code:` bullet, a
   `does:` with no effects, flags with no per-flag detail, a concept with no parts). Each → a
   re-visit item of its kind.
5. **Journeys** — model representative user/business paths, not transport inventory. Never create
   one flow per HTTP endpoint, command, screen, or invocation. If no representative `flow` nodes
   exist yet, emit at most 3-8 coherent domain journeys for a large service (for example
   signup-to-account-completion, project lifecycle, datasheet management, and command-order
   fulfillment), each allowed to traverse several invocations. A small single-purpose service may
   need only 1-3. Set `needs_journeys: yes` with `coverage_complete: no` so the loop drains them,
   then re-checks. If representative flows exist, do not expand them merely for endpoint coverage.

## Output

```json
{"discovered": [{"kind": "element", "target": "…", "context": "…"}],
 "coverage_complete": "yes",
 "needs_journeys": "no"}
```

Set `coverage_complete: yes` **only** when checks 1–4 find nothing (the code inventory is fully
covered), `inventory_errors` is empty, and journeys exist. Otherwise `no` (with the items to drain).
Batch uncovered source units by their nearest coherent module/package and emit one `layer` item per
group, listing every uncovered unit in `context`; do not emit hundreds of one-symbol items. Batch a
large surface's missing elements into `surface-slice` items by route/domain/screen region.
For a below-bar or orphan node already visited, add `"requeue": true` to its item so the worklist
opens it again. Empty `discovered` +
`coverage_complete: yes` ends the build.
