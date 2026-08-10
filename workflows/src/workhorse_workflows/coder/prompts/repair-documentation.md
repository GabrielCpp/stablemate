---
agent: agent
---

# Repair the cited documentation (OKF UI profile)

This story is already documented and a gate sent the book back. Close the findings below.
**Do not re-document the story, and do not revisit a node no finding names.**

Load the skill and follow it: {{ skill_load_ref("ostler-documentation", skill_dir() + "/ostler-documentation/SKILL.md") }}
It carries the node-type vocabulary, the bullet schema and the linter rules; obey them. The
reference for the type table and bullets is the `ostler` skill it links to.

## Inputs

- Story path: `{{ workhorse_var('story_path') }}`
- Spec dir: `{{ workhorse_var('spec_dir') }}`
- Docs root: `{{ workhorse_var('docs_path') }}`
- OKF features root: `{{ workhorse_var('features_root') }}`
- Parent epic with authoritative user journeys: `{{ workhorse_var('epic_path') }}`
- Context mode: `{{ workhorse_var('context_mode') }}`
- Context notes: `{{ workhorse_var('context_notes') }}`
- Deterministic gate notes: `{{ workhorse_var('gate_notes') }}`
- Semantic review notes: `{{ workhorse_var('review_notes') }}`

{% if workhorse_var('obligations') %}
## Grounding worklist — already computed, do not re-derive it

The same deterministic mapper the gate uses has already joined this story's diff against the
book. These are the changed production references no node's `code:` bullet owns yet, spelled
the way the source inventory spells them:

{% for ref in workhorse_var('obligations') %}
- `{{ ref }}`
{% endfor %}

This list **is** the grounding half of your worklist. Do not reconstruct it by hand — do not
grep the book for each changed symbol, and do not list a repo's files to work out what
changed. That join is arithmetic the tooling already did, it is slower and less accurate done
with shell commands, and a reference you re-spell yourself grounds nothing. Copy each entry
verbatim into the `code:` bullet of the node that documents that behavior.

An empty list means the mapper had nothing left to map, not that you should compute one.
{% endif %}

## The rule

**The findings above are the complete worklist for this pass, and every node they do not
name stays exactly as it is.** Not reworded, not reordered, not tidied, not improved.

This is not a stylistic preference. A node you rewrite is a node the `power="high"` reviewer
must read again, and it will — correctly — find a different real defect in it. That is how a
story spends four documentation passes on a book that was one edit from conformant. A
gratuitous improvement to an uncited node is a defect in this turn.

Retain the stable `D1`, `D2`, ... IDs on semantic review findings, and normalize unresolved
deterministic grounding failures as `G1`, `G2`, .... For each item:

- identify the exact file/anchor it names;
- inspect the implementation symbol or cited test **before** writing prose;
- make the smallest documentation edit the evidence supports, or weaken an overclaim to the
  exact behavior the evidence proves;
- if no implementation or test proves a claim, omit the claim or state the limitation rather
  than inventing support.

A deterministic note beginning `conformant;` is successful gate evidence and context, not a
grounding repair item. A finding already satisfied by the current book needs no edit — say so
in `notes` rather than touching the node to prove you read it.

## Grounding, when the gate is what refused

Each changed production unit must be owned *directly*: **every** one of its changed symbols
named as `path::symbol` in some node's `code:` bullet, or, for a file with no symbols the
inventory can see (a config or manifest), the file path itself. A node that describes the
behavior in prose but does not name the file does not own it.

**Copy each reference verbatim** — the spelling is the inventory's, not yours, and a symbol
renamed on the way into a bullet grounds nothing. A Go method is `path.go::(*Type).Method`,
not `path.go::Type.Method`. Grounding a file the notes never mentioned, or half its symbols,
spends a rework pass and changes nothing.

**A symbol or file this story deleted needs no `code:` citation at all.** `ostler doctor`
rejects every `code:` target that isn't there, with no exception, so the correct response to a
deletion is to remove the bullet that cites it — or the node, if it described only what was
deleted — never to invent a citation for something gone.

If the gate notes name an unowned path, `not_required` is the one answer that cannot be right:
a grounding bullet you had to add makes the answer `documented`.

## Converge

Run `ostler fmt` on the docs you touched, then `ostler doctor` (from the docs root, `-C` if
needed). Fix any error by its named remedy until `doctor` is green for the nodes you touched.
In `semantic` multi-repo mode, repository-local doctor cannot resolve service-repo `code:`
paths beneath the separate docs root: report its `dangling-code-ref` / `missing-code-symbol`
findings for independent review, but do not return `blocked` for those two grounding codes
alone. Every structural, relation, schema, and local grounding error remains blocking. Never
silence a finding by deleting a meaningful bullet.

Never weaken an invariant, journey completion condition, persistence rule, event contract, or
concurrency requirement merely to match the implementation. Such drift is a product/author
decision: return `blocked` and name the item, rather than claiming success or removing a
requirement to pass.

## Output

Output JSON only:

```json
{"status": "documented", "nodes": ["docs/features/acme/gui/screens/example.md#example-panel"], "notes": "D1 resolved: docs/features/acme/gui/screens/example.md#example-panel — moved under ## Interactions; G1 resolved: api/widget.go::Widget grounded on the same node."}
```

`status` is one of `documented`, `not_required`, or `blocked`. `notes` must be the checklist:
`D1 resolved: <file#anchor> — <evidence>; D2 resolved: ...`, naming any item you could not
close and why. `nodes` lists every node you edited, by exact graph identity with its section
anchor; for `not_required`, an empty list.
