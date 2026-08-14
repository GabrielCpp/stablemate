---
agent: agent
---

# okf-builder — repair one doctor finding, on one node

The convergence checkpoint read `ostler doctor` over the book and queued this item. Every finding in
it is the **same code** on the **same node**, which is why the instructions below are written for
that one defect rather than for repairs in general.

Load the method and obey it: {{ skill_load_ref("okf-modeling", skill_dir() + "/okf-modeling/SKILL.md") }}
{% if workhorse_var('item_code') in ['undeclared-obligation', 'weak-check', 'unstated-precondition', 'unparsed-check', 'compound-normative-bullet'] %}
This finding is about whether a claim can ever be observed, so load the bar it is measured against:
{{ skill_load_ref("falsifiable-verification", skill_dir() + "/falsifiable-verification/SKILL.md") }}
{% endif %}

## This item

- code: `{{ workhorse_var('item_code') }}`
- target: `{{ workhorse_var('item_target') }}`
- context (JSON — `code`, `node`, `path`, `grounded`, `findings`):

```json
{{ workhorse_var('item_context') }}
```

- service: `{{ workhorse_var('service') }}` — features root: `{{ workhorse_var('features_root') }}`
- repo root: `{{ workhorse_var('repo_root') }}`
- source root: `{{ workhorse_var('source_root') }}`
- excluded source paths: `{{ workhorse_var('source_excludes') }}`

## The check vocabulary — closed, and this is all of it

Every `verify:`/`check:` value is a call from this list. The names and the **argument names**
are fixed; doctor parses them and rejects anything else as `unparsed-check`, which is how a
made-up check comes straight back as the finding you were paid to remove.

{{ workhorse_var('check_vocabulary') }}

- **Never invent a check or an argument.** `count(subject=…, expected=1)` is not a check —
  `count` takes `equals`. Neither is `persists(…)` or `emitted(…)`; they are not in the list
  above. If nothing in the list can observe the claim, the claim's verification is not yours
  to invent: leave it standing and say so in `doc_status`.
- **Pick the check the claim's own defect calls for**, using the `excludes` sentence. `visible`
  observes rendered UI — a Go function returning bytes is not visible to anything, and writing
  `visible(locator="PDFEngine output", …)` states an observation no harness can make.
- **A check's arguments are values, not prose.** `json_path(path="$.x", equals="the second
  address line")` asserts the field equals that sentence. If you do not know the value, read
  the source for it; if the claim has no single value, choose a check that fits.

Work the findings **top-down by line**. All of them are yours to resolve this turn; a finding you
leave standing comes back next round as a fresh item, so skipping one costs a round rather than
hiding it.

## Guardrails (this runs unattended — stay in your lane)

- **Docs only.** You write **only** under `docs/features/**`. Never modify source code, never run
  `git`, never run builds or tests. You are documenting the code, not changing it.
- **One node.** Open the `path` in the context and repair the node the findings name. Do not tour
  the book; other nodes' findings are other items.
- **Read the source before you write a value.** The node's `code:` bullet points at the symbol this
  claim is about. When the context says `"grounded": true` the finding does **not** carry the value —
  it must come out of the source, cited in prose.
- **Do not run a full `ostler doctor`.** It lints the whole repository to answer a question about
  one node. Run `ostler fmt <the file you touched>` and stop. The checkpoint re-runs doctor once per
  round and re-queues anything you missed.

## The one rule every repair shares

**Never make a finding go away by removing what it was about.** Deleting a `verify:`, dropping a
`does:` clause, vaguing a bullet down until the rule stops applying, or removing a `code:`/link
reference all clear the finding and leave the book saying less than it did. Doctor cannot tell that
apart from a real repair — the count falls either way — which is why it is the one thing you are
asked not to do. If a claim is genuinely wrong, say so in `doc_status` and leave it standing.

Three ways that rule gets broken while looking like a repair, all seen in a real run:

- **Re-pointing a reference instead of fixing it.** `missing-code-symbol` on
  `main.py::__main__` was cleared by editing the bullet to `main.py::main` — a symbol that
  exists and is a *different thing*, already documented by another node. A `code:` bullet is a
  claim about which symbol this node is; if the cited symbol is gone, say so, do not aim the
  bullet at a neighbour.
- **Losing the explanation while splitting.** A compound bullet is split into one bullet per
  observation, and the *why* travels with the observation it belongs to. A clause like "so an
  existing non-zero row is deleted, not zeroed" is the whole content of the claim; a split that
  drops it turns a documented behaviour into a list of verbs.
- **Repeating a key to hold the leftovers.** One `does:`/`emits:`/`consumes:` per node, with
  its sub-bullets under it. A second `- does:` block further down is a parse accident, not a
  split, and its sub-bullets read as belonging to nothing.

Where the rule bites, per code, is below.

{% include ["prompts/repair/" ~ workhorse_var('item_code') ~ ".md", "prompts/repair/_default.md"] %}

## Output

```json
{"discovered": [], "doc_status": "documented"}
```

`doc_status` ∈ `documented` (every finding in the item repaired) | `partial` (some left standing —
say which and why) | `skipped` (the finding is wrong about this node; say so).

`discovered` is normally empty: a repair is not a discovery turn. Emit an item only if the repair
revealed genuinely undocumented surface, and never emit one for a finding you chose not to fix — the
checkpoint re-queues those itself.
