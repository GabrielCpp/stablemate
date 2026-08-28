---
agent: agent
---

# okf-builder — coverage re-scan (the exhaustiveness backstop)

The worklist drained, `ostler doctor` is clean — **every** non-waived finding, warns included — and
the machine has already computed that this book is still incomplete: there is a source unit nothing
cites. That is why you are running. Your job is to turn the computed gap into drainable work, plus
find the gaps arithmetic cannot see (orphans, stubs, journeys, the runbook).

**You do not decide whether the book is complete.** That verdict is a join, and the machine computes
it — coverage is arithmetic, not a self-report. It joins the source inventory against the book's
`code:` citations: is every unit documented. What is genuinely yours is the *ambiguity* in it —
whether a computed miss is a real gap or a unit already folded into a documented contract.
Adjudicate those, record each with its reason, and queue everything else.

Load the method: {{ skill_load_ref("ostler-okf", skill_dir() + "/ostler-okf/SKILL.md") }}

**Guardrails (unattended):** you may run read-only `ostler` (graph/list/trace/doctor) and read code,
but do **not** modify code, run `git`, or run builds/tests. Queue work by returning items; don't
author nodes yourself this turn. Stay inside the service's own source. The **one** file you may
write is the waivers file below.

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
- inventory errors: `{{ workhorse_var('inventory_errors') }}`
- **the computed coverage verdict:** `{{ workhorse_var('coverage_summary') }}`
- **the computed missing list** (your input for check 1): `{{ workhorse_var('missing_path') }}`
  — `{{ workhorse_var('missing_count') }}` units
- coverage errors (a blind instrument, if non-empty): `{{ workhorse_var('coverage_error') }}`
- waivers file (the one file you may write): `{{ workhorse_var('waivers_path') }}`

If `coverage_error` is non-empty, the instrument could not measure this book — fix nothing and queue
nothing on the strength of it; report it in your items' context so a human sees it. An unmeasurable
book is not an empty gap.

## Checks — emit an item for every gap you find

1. **The computed missing list — adjudicate it, don't recompute it (do this first).** Read
   `missing_path`. Every row is a source unit the join found no `code:` citation for; the join
   already applied the transitive module rule (a module is covered when it is cited, or when it
   declares symbols and all of them are cited), so do not re-litigate that arithmetic and do not
   replace the list with a sampled grep. For each row decide **exactly one** of:
   - **a real gap** → queue it as an item (batched, per the Output rules below);
   - **not a unit** → *waive* it, with a reason. A helper genuinely folded into a documented
     behavior's `does:` or a concept's parts, or a deliberate non-unit. A waiver is a claim that the
     book already says this — so name the node that says it. "Too small to document" is not a
     reason; "folded into `‹node-id›`'s contract" is.

   Waive by writing `waivers_path` as JSON, **preserving any entries already there** (they are prior
   rounds' judgements — reviewed, committed, and not yours to drop):

   ```json
   {"waivers": [{"code": "api/internal/x.go::parseRequest",
                 "reason": "folded into UI-EP-0007's does: contract"}]}
   ```

   A waived unit counts as covered on the next round's join, which is why the reason is committed
   and diffable rather than argued once and forgotten. Waive nothing you cannot justify in review:
   the join is the only thing standing between this book and a number nobody can reproduce.

   Watch for the two blind spots that motivated this check:
   - **Every implementation of an interface / ABC is its own node.** If the code has N subclasses of
     a base but the graph documents fewer, queue the missing ones. (e.g. an `AgentBackend` base with
     `Claude`/`Codex`/`Copilot`/`OpenCode`/`Cline` subclasses ⇒ **five** sibling `concept`s, not one
     with the rest named in prose.)
   - **Utility / library modules never reached from an entry point** are still surfaces of the
     service — queue them. (e.g. a `scriptutil`/`sdk` helper module imported by *other* tools.)
   Map each: class/module → `concept`, data shape → `format`, command/route/control → `element`.

   You are not asked about undeclared observations here. A node whose bullets mint obligations and
   declares no `verify:` is `undeclared-obligation`, and the convergence checkpoint you passed to
   reach this turn drains **every** non-waived doctor finding, warns included — so by construction
   there are none standing. Queue nothing for it; if you see one, the checkpoint is the bug.

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
   need only 1-3. Set `needs_journeys: yes` so the loop drains them, then re-checks. If
   representative flows exist, do not expand them merely for endpoint coverage.
6. **Operational surface — the run surface must be a `runbook`** (the OKF runbook profile).
   The inventory file carries an `operational` list —
   the mechanical run surface (make/just targets, compose services, package/console scripts,
   `__main__` entry points). Diff it against the graph: `ostler list runbook` / `ostler list
   environment` (and `ostler graph --surface ‹service› --type runbook`). **The book is not complete
   until the run surface is a runbook**: every driver the service exposes has a `runbook` whose
   `## Steps` are ordered and executable and whose `environment` resolves, and each target
   environment has an `environment` node. Queue a `runbook`/`environment` item for any driver or
   target that is missing or below the §4.4 bar (a step with no real `run:`/`health:`, an
   unresolved `environment:`/`surfaces:` link, a `service` step whose `health:` is a UI shell rather
   than a real probe). A repo with genuinely nothing to boot still needs one `artifact`/`none`
   runbook — its absence is a gap, not a pass.
7. **Judgment** — competing implementations with no recorded selection rule. Query the graph for
   two or more nodes of the *same type* whose `code:` bullets cite an identical `path::symbol`
   (`ostler graph --surface ‹service› --bullet 'code=<symbol>'` checks one; the doctor's
   `competing-implementations` warn lists the standing groups) with no shared `detail:` concept
   between them. For each such group, read the cited source for the evidence that settles the
   competition — a deprecation annotation, a migrated call site, a comment naming the successor —
   and emit one `judgment` item per concept, batching that concept's competing nodes:

   ```json
   {"kind": "judgment", "target": "<concept-slug>",
    "context": "nodes: <ids>; evidence: <path::symbol …>"}
   ```

   Cite the code that shows the preference. **An unsettled competition is recorded, not resolved
   by invention** — a concept whose `rule:` the source does not back is worse than no concept,
   because a reviewer trusts it exactly once.

## Output

```json
{"discovered": [{"kind": "element", "target": "…", "context": "…"}],
 "needs_journeys": "no"}
```

There is no `coverage_complete` to emit — the build ends when the next round *computes* the gap
closed: every unit covered, by a citation or by a waiver you justified, with the round cap bounded
and `doctor` clean of every non-waived finding. Your items and your waivers are what move those
numbers; nothing you can say about your own work does.

Batch uncovered source units by their nearest coherent module/package and emit one `layer` item per
group, listing every uncovered unit in `context`; do not emit hundreds of one-symbol items. Batch a
large surface's missing elements into `surface-slice` items by route/domain/screen region.
For a below-bar or orphan node already visited, add `"requeue": true` to its item so the worklist
opens it again. Returning empty `discovered` while the join still reports misses does not end the
build — it burns a round, and the run fails when the rounds run out.
