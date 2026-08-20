---
agent: agent
---

# Repair the cited documentation (OKF UI profile)

This story is already documented and a gate sent the book back. **Do not re-document the
story.** Close every finding below; the deterministic gate re-runs `ostler doctor` when you
return and sends back whatever is still red, so **iterate `ostler doctor` yourself until it
reports zero errors for the affected nodes** before returning. One turn that converges costs
less than ten laps that each close a batch.

## Time budget — {{ node_timeout_min }} minutes

This turn is stopped at its budget ("unbounded" = no cap), and what survives is the book on
disk rather than this turn's reply. Being cut is **not** a failure: edit one node at a time,
saving as you go, and a turn that ran out having closed most of the findings is worth far
more than one that batched them and landed none. If it happens, the next turn continues this
same conversation with the still-red errors — it is told the budget stopped you, so do not
start the book over and do not re-close what is already closed.

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

**A doctor error the gate scoped to this story is a finding, wherever it sits.** So is one
your own edit mints. The worklist is "the cited findings, plus whatever `ostler doctor` still
reports for the affected nodes when you are done" — not "the nodes named in the prose". If the
gate notes point at a `doctor-errors.txt`, read that file: it is the full list, and the note is
only a pointer to it.

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

**`missing-code-symbol` after your own refactor is the same situation wearing a disguise.** The
behavior survived, so the node is right and only the citation is stale; the symbol that used to
carry it may have been *dissolved* into another rather than moved. Open the file and read what
it declares now, then cite that. Do not explain where the symbol "really lives" from memory —
grounding is part-wise and a re-export does not satisfy it, so an unverified explanation is a
guess that fails the next lap identically.

If the gate notes name an unowned path, `not_required` is the one answer that cannot be right:
a grounding bullet you had to add makes the answer `documented`.

**The other half: what the behavior would look like observed.** `code:` and `tests:` say where
the behavior lives; `verify:` says what holds when it works, and it is a *declaration*, not a
ref. It is a named call from ostler's check vocabulary with typed arguments.

**Read the signatures; do not infer them from the name.** The arguments are not uniform —
`absent` takes `subject`, `visible` takes `locator`, `emitted` takes `event` — and a plausible
guess costs a full gate lap:

```bash
ostler checks            # every check: signature + the defect it excludes
ostler checks emitted    # one of them
```

```markdown
- does: on a stale write the manifest is left byte-identical and the request is refused
- verify: http_status(409, title="Manifest Conflict")
- verify: unchanged(subject="manifest")
- tests: `api/publish_test.go::TestPublish_Conflict`
```

Two grounding failures land here, and they are repaired differently:

- **`unparsed-check`** (error, blocking) — the value is not a call: a test id, an unknown name, a
  bad argument. Move a test id to `tests:` and declare the observation in its place. The
  finding's suggestion line carries the failing check's own signature — use it rather than
  guessing again. Never "repair" it by deleting the bullet.
- **`undeclared-obligation`** (warn) — the node mints obligations and declares nothing at all, so
  a QA plan claiming them can assert anything and still pass. Add one `verify:` per observation
  the node's normative bullets promise. Read the code you just grounded to decide *which* call:
  the handler that refuses a stale write declares `http_status(409, …)`; the one that writes
  through a store before answering declares `persists(subject=…)`. This is the one bullet nobody
  downstream can supply for you — only the node knows what the behavior promised.

Do not invent an observation the code does not make. If a normative bullet is genuinely
unobservable from outside, that is usually the bullet being descriptive rather than normative:
reword it, which is a repair the deletion rule above already permits.

Pick the check by the shape of evidence the claim needs, not by the surface it appears on:

- use `http_status` for route readiness and response status;
- use `json_path` for exact payload values, extracted PDF text arrays, ordering, booleans such
  as "same page" / "different page", and other structured evidence;
- use `count` for cardinality, including "one heading per tab" or "no duplicate title";
- use `visible` only for a concrete thing a user can perceive. A locator string that says
  "A precedes B", "one per tab", "on the next page", or "all sentinels" does not prove that
  relationship — it only renames it. Replace it with a check whose value changes when the
  order, count, page relationship, or exact text is wrong.

For command startup, observe a real readiness seam. If the implementation starts a server and
does not print a banner, declare the health route or other actual probe, not invented stdout.

## Converge

Run `ostler fmt` on the docs you touched, then `ostler doctor` (from the docs root, `-C` if
needed). **Fix, re-run, repeat — iterate until `doctor` reports zero errors for the affected
nodes.** Do not return after one pass of edits and let the gate tell you what is left: that is
a whole extra lap, with a fresh read of the book, to learn something one more `doctor` call
would have told you here. Errors of a single shape are the cheapest case, not a reason to
stop — repair them all in this turn.

To narrow that report to your own nodes, `ostler doctor --json` emits
`{org, profile, epics, errors, warnings, findings}`. `findings` is the list — each entry
carries `path`, `line`, `code`, `severity` and `suggestion` — while `errors` and `warnings`
are **counts**, not lists. Keep stderr out of the pipe (`--json 2>/dev/null`, never `2>&1`):
a single warning line on stdout makes the document unparseable, and the parse error that
follows looks exactly like having picked the wrong key.

In `semantic` multi-repo mode, repository-local doctor cannot resolve service-repo `code:`
paths beneath the separate docs root: report its `dangling-code-ref` / `missing-code-symbol`
findings for independent review, but do not return `blocked` for those two grounding codes
alone. Every structural, relation, schema, and local grounding error remains blocking. Never
silence a finding by deleting a meaningful bullet.

Never weaken an invariant, journey completion condition, persistence rule, event contract, or
concurrency requirement merely to match the implementation. Such drift is a product/author
decision: return `blocked` and name the item, rather than claiming success or removing a
requirement to pass.

## Commit What You Wrote

The workflow does not commit on your behalf. Work still sitting in the working tree when the
story ends parks it for an operator instead of shipping it, so the last thing you do is record
what you wrote:

1. **Stage by explicit path** — never `git add -A`, `git add .` or `git commit -a`. Those sweep
   in whatever else is in the tree, and something else is usually working here. Anything that is
   not yours stays exactly where it is.
2. **One commit per repository**, its subject scoped to the package you changed:

   ```
   <type>(<package>): <lowercase imperative description>

{% if workhorse_var('epic') %}   Epic: {{ workhorse_var('epic') }}
{% endif %}{% if workhorse_var('story_slug') %}   Story: {{ workhorse_var('story_slug') }}
{% endif %}   ```

   `<type>` is `docs`: this commit writes specification, not product code, and must not
   release a version of anything. Subject ≤ 72 characters, no capital first word, no
   trailing period. Keep the trailers exactly as spelled — they are how the run record ties a
   commit back to its story.
3. **Do not push, open a pull request, or switch branches.** The workflow owns those.

## Output

Output JSON only:

```json
{"status": "documented", "nodes": ["docs/features/acme/gui/screens/example.md#example-panel"], "notes": "D1 resolved: docs/features/acme/gui/screens/example.md#example-panel — moved under ## Interactions; G1 resolved: api/widget.go::Widget grounded on the same node."}
```

`status` is one of `documented`, `not_required`, or `blocked`. `notes` must be the checklist:
`D1 resolved: <file#anchor> — <evidence>; D2 resolved: ...`, naming any item you could not
close and why. `nodes` lists every node you edited, by exact graph identity with its section
anchor; for `not_required`, an empty list.
