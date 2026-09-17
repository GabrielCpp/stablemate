---
agent: agent
---

{% set codes = workhorse_var('item_codes') or [workhorse_var('item_code')] %}
# okf-builder — repair the doctor findings on one book file

The convergence checkpoint read `ostler doctor` over the book and queued this item. Its findings sit
in **one file** or, when the context carries `paths`, in the few sibling files it lists — and each code in it (`{{ codes | join('`, `') }}`) has instructions below written for
that defect rather than for repairs in general. You read each file and its source once, and repair
every finding in them this turn.

Load the method and obey it: {{ skill_load_ref("ostler-okf", skill_dir() + "/ostler-okf/SKILL.md") }}
{% if codes | select('in', ['undeclared-obligation', 'weak-check', 'unstated-precondition', 'unparsed-check', 'compound-normative-bullet', 'unminted-claim']) | list %}
A finding here is about whether a claim can ever be observed, so read the bar it is measured
against: `{{ skill_path_ref("ostler-okf", "references/falsifiable-verification.md") }}`.
{% endif %}

## This item

- codes: `{{ codes | join('`, `') }}`
- target: `{{ workhorse_var('item_target') }}`
- context (JSON — `grounded` and `findings`, each finding carrying its own `code`, plus one of:
  `code`/`node`/`path` (the one node this item is about); `codes`/`nodes`/`path` (the nodes of one
  file this item covers); `codes`/`nodes`/`paths` without `related` (the nodes of the sibling
  files this item covers, each finding naming its own `path`); or, on a group finding, `code`, `citation` (the `path::symbol` the group
  is about), `related` (every node this item covers) and `paths` (their files)):

```json
{{ workhorse_var('item_context') }}
```

- service: `{{ workhorse_var('service') }}` — features root: `{{ workhorse_var('features_root') }}`
- repo root: `{{ workhorse_var('repo_root') }}`
- source root: `{{ workhorse_var('source_root') }}`
- excluded source paths: `{{ workhorse_var('source_excludes') }}`
- source inventory (mechanical, per-file symbol list; may not exist before the first
  coverage re-scan): `{{ workhorse_var('source_inventory_path') }}`

## The check vocabulary — closed, and this is all of it

Every `verify:`/`check:` value is a call from this list. The names and the **argument names**
are fixed; doctor parses them and rejects anything else as `unparsed-check`, which is how a
made-up check comes straight back as the finding you were paid to remove.

{{ workhorse_var('check_vocabulary') }}

## The act vocabulary — the other closed list, for `arrange:`

`fixture:` names something run *beside* the surface; `arrange:` is a performance carried out
*on* it by whoever performs the step. A precondition over what the user typed is reachable
only by typing, and no out-of-process command can type into a form — so state a `fixture:`
cannot reach goes here, one act per bullet, above the claim it arranges.

{{ workhorse_var('act_vocabulary') }}

- **The locator is a reference into the book**, spelled exactly as a check's is:
  `arrange: fill(locator="#name-field", value="Widget A")`. A raw selector is
  `undeclared-act-locator`, for the same reason it is on a check — renaming the control has
  to show up in the book, not only in a red run.
- **A name with no parentheses is a fixture**, not an act, and `unparsed-act` says so and
  relocates it rather than asking you to invent a performance for it.
- **Check the driver list before writing one.** An act this target's driver cannot perform is
  a gap the compiler will mint, not a scenario it will emit.

- **Use the rendered inventory as authority for check names and arguments.** A missing
  dedicated check does not mean missing evidence: the scenario acquires observations,
  and a registered check compares them. If no obtainable observation can discriminate
  the claim, leave it standing and explain the specific evidence gap in `doc_status`.
- **Pick the check the claim's own defect calls for**, using the `excludes` sentence. `visible`
  observes rendered UI — a Go function returning bytes is not visible to anything, and writing
  `visible(locator="PDFEngine output", …)` states an observation no harness can make.
- **A check's arguments are values, not prose.** `json_path(path="$.x", equals="the second
  address line")` asserts the field equals that sentence. If you do not know the value, read
  the source for it; if the claim has no single value, choose a check that fits.

### Capture evidence, then compare it

Observations are **scenario-owned values, never invented product outputs**. Describe in
the book how the scenario obtains them: invoke the real method and capture its return,
expected exception, stdout/stderr, or independently read file content. The `verify:`
bullet carries **comparison arguments only**, not an `observed` argument or capture code.
For example, document a scenario calling `assert_file_contains` on an absent file (and
separately on a file containing the wrong text), capturing the exception type and message:

```markdown
- verify: json_path(path="exception.type", equals="AssertionError")
```

This is the corresponding QA scenario body, not code for this docs-only turn to run.
Here `sandbox` is the scenario's prepared directory, `rel` its absent or wrong-content
file, `text` the required substring, and `covers` the obligation IDs being exercised:

```python
from workhorse.testing import assert_file_contains

observed = {"exception": {}}
try:
    assert_file_contains(sandbox, rel, text)
except AssertionError as exc:
    observed["exception"] = {"type": type(exc).__name__, "message": str(exc)}

qa.verify("json_path", observed, path="exception.type", equals="AssertionError", covers=covers)
```

A no-op helper leaves the mapping empty, so the check fails. Catch only the expected
product exception around the product call; unexpected types propagate. Keep verifiers
outside that handler so verifier errors cannot become product evidence. For a diagnostic
claim, compare `exception.message` with a concrete `equals` or discriminating `matches`
derived from the documented input. Do not pre-fill expected results or use a no-op check
to claim behavior was proved. The same capture works for `assert_json_file` on mismatched
JSON; captured stdout/stderr can likewise be checked with `json_path` and `matches`,
without a dedicated exception, file-containment, or skip-output verifier.

## The bullet grammar — rendered from the registry, per node type

Every bullet you write or move must be a key the node's type declares, carrying the flags
below. This is the same contract `ostler doctor` enforces, rendered from the same registry,
so a key that is not here comes back as `unknown-bullet`.

{{ workhorse_var('bullet_grammar') }}

The full authority for a type — what each key *means*, with examples — is its reference
page: `{{ skill_path_ref("ostler-okf", "references/node-types") }}/<type>.md`. Read the
page for the node's type before restructuring its bullets; the grammar above says what is
legal, the page says what is right.

Work the findings **top-down by line**. All of them are yours to resolve this turn; a finding you
leave standing comes back next round as a fresh item, so skipping one costs a round rather than
hiding it.

## Guardrails (this runs unattended — stay in your lane)

- **Docs only.** You write **only** under `docs/features/**`. Never modify source code, never run
  `git`, never run builds or tests. You are documenting the code, not changing it.
- **One file, or the listed files.** Open the `path` in the context — or, when it carries `paths`
  and no `related`, each of those files — and repair the nodes the findings name, file by file.
  Do not tour the book; a file not in the context is another item's work. **Unless the context carries `related`** —
  then those locations *are* this item: open every one of them (`paths` lists the files) and
  repair the group as a whole. That finding is one defect spread over several nodes and it does
  not clear until each of them is edited. `related` is the whole of the exception — a node not
  in that list is still another item's work.
- **Every code is this turn's.** A finding's own `code` says which section below is its remedy.
  Where two findings touch the same bullet, make one edit that satisfies both.
- **Read the source before you write a value.** The node's `code:` bullet points at the symbol this
  claim is about. When the context says `"grounded": true` the finding does **not** carry the value —
  it must come out of the source, cited in prose.
- **Check your repair with the checker that raised it, never with a grep.** After `ostler fmt <the
  file you touched>`, run `ostler doctor --path <that file>` (under a minute: it reads the
  whole book but prints only this file's findings). Over several files, pass `--path` once per
  file in one run — `ostler doctor --path <a> --path <b>` — rather than one run per file. Give the command a timeout of at least
  120 seconds; a 15- or 30-second timeout kills it with no output, which checks nothing. Any finding it still reports under this item's
  codes is not repaired: fix it and check once more. Report `documented` only when none of them is
  left; after the second check, return `partial` naming what still stands. A pattern search is not
  a check. It misses every bullet that wraps onto a second line, and a turn that closed on one
  costs a whole turn more when the next doctor read re-queues the finding. Do not run `ostler
  doctor` without `--path`: the unscoped report is megabytes about other files.
- **The book was committed just before this turn**, so `git diff -- {{ workhorse_var('features_root') }}`
  is exactly what you changed, including what `ostler fmt` rewrote (keep that), and undoing an
  edit means editing the file back. `{{ workhorse_var('baseline') }}` is the same book as a plain
  copy, for when that commit could not land: `diff -ru {{ workhorse_var('baseline') }}
  {{ workhorse_var('features_root') }}`. Do not commit yourself; the run commits the book after
  this turn under the `commit_message` you return.

## The one rule every repair shares

**Never make a finding go away by removing the claim it was about.** Deleting a `verify:` that
binds an obligation, dropping a `does:` clause, vaguing a bullet down until the rule stops
applying, or removing a `code:`/link reference all clear the finding and leave the book saying
less than it did. Doctor cannot tell that apart from a real repair — the count falls either way —
which is why it is the one thing you are asked not to do. If a claim is genuinely wrong, say so in
`doc_status` and leave it standing.

This rule is about the *claim*, not the bullet's spelling. A bullet can be inert — written under a
key its node type mints nothing from, so it carries no claim at all — and removing an inert bullet
removes nothing the book was asserting. `unknown-bullet` is exactly that case; its own fragment
below says what to do instead of deleting on sight.

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

{% for code in codes %}
{% include ["main/prompts/repair/" ~ code ~ ".md", "main/prompts/repair/_default.md"] %}
{% endfor %}

## Output

```json
{"discovered": [], "doc_status": "documented", "commit_message": "docs(<service>): <what the repair changed>"}
```

`commit_message` is the subject of the commit that records this turn: `docs(<service>):` then a
lowercase imperative saying what changed in the book, not which finding was raised, 72 characters
at most. Leave it empty when you changed nothing.

`doc_status` ∈ `documented` (every finding in the item repaired) | `partial` (some left standing —
say which and why) | `skipped` (the finding is wrong about this node; say so).

`discovered` is normally empty: a repair is not a discovery turn. Emit an item only if the repair
revealed genuinely undocumented surface, and never emit one for a finding you chose not to fix — the
checkpoint re-queues those itself.
