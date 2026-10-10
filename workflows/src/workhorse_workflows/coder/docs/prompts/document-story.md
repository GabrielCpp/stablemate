---
agent: agent
---

# Own The Story's Documentation

You own this story's documentation. The implementation passed review, and QA derives its
obligations from the book next. Your job is to **merge everything this story changed into the
current OKF book**: new services, screens, components, commands, endpoints, interactions,
concepts, formats and flows. This is an incremental one-story update, not a changelog or a bulk
build. You do the work through subagents, and you decide what each one sees. This turn ends
with the book written, reviewed, repaired and green under `ostler doctor`, and the JSON result
below.

Your session is resumable. A later turn on this story continues this conversation with the
workflow's report or an operator's answer.

Load the skill and follow it: {{ skill_command("ostler-okf") }}
It carries the full loop (scaffold, author, fmt, doctor) and links the written model. That model
is the authority for everything below, and for every seat you brief:

- `references/node-types/<type>.md`: what a type owes, its keys, sections, relationships and
  doctor codes.
- `references/bullet-grammar.md`: what a normative bullet owes, and which claim a `verify:` or a
  `fixture:` attaches to.
- `references/check-vocabulary.md`: the checks and their signatures.
- `references/doctor-codes.md`: a code's trigger and its remedy.
- `references/defect-kinds.md`: what the review rejects on.

## Inputs (authoritative, do not rediscover)

- Story: `{{ workhorse_var('story_slug') }}` (id `{{ workhorse_var('story_id') }}`, epic `{{ workhorse_var('epic') }}`)
- Story path: `{{ workhorse_var('story_path') }}`
- Spec dir: `{{ workhorse_var('spec_dir') }}`
- Docs root: `{{ workhorse_var('docs_path') }}`
- OKF features root: `{{ workhorse_var('features_root') }}`
- Parent epic with authoritative user journeys: `{{ workhorse_var('epic_path') }}`
- Context mode: `{{ workhorse_var('context_mode') }}`
- Context notes: `{{ workhorse_var('context_notes') }}`
{% if plan_services %}

The services and repos the story touched:

{{ plan_services }}
{% endif %}
{% if workhorse_var('obligations') %}

## Grounding worklist (already computed, do not re-derive it)

The same deterministic mapper the gate uses has joined this story's diff against the book.
These are the changed production references no node's `code:` bullet owns yet, spelled the way
the source inventory spells them:

{% for ref in workhorse_var('obligations') %}
- `{{ ref }}`
{% endfor %}

This list **is** the grounding worklist. Hand it to the writer verbatim. Nobody reconstructs it
by hand: no grepping the book for each changed symbol, no listing a repo's files to work out
what changed. That join is arithmetic the tooling already did, and a reference re-spelled by
hand grounds nothing. An empty list means the mapper had nothing to map. It is not a cue to
compute one.
{% endif %}
{% if report %}

## The checks failed

The workflow checked your last turn, and the grounding gate did not hold. Its report:

{{ workhorse_var('report') }}

This turn repairs what the report names, and runs no new review. If the report points at a
`doctor-errors.txt`, read that file. It is the full list, and the note only points at it. A
note beginning `conformant;` is successful gate evidence, not a repair item. Every node the
report does not name stays exactly as it is.
{% endif %}
{% if operator_context %}

## Operator answer (authoritative ground truth)

An operator answered a block on this story. Treat the answer as fact. It overrides any earlier
assumption in the story, the book or a finding. Do not re-derive it, and do not raise the same
block again.

{{ workhorse_var('operator_context') }}
{% endif %}

## How to work

1. **Scope.** Read the story's acceptance criteria, the parent epic's `## User Journeys` and
   the spec dir. The implementation delta is the working tree plus every commit on the story
   branch since its base, including QA, regression, CI and merge remediation. From that delta,
   name each user-facing surface, element, behavior, concept or format the story added or
   changed: a screen, component or interaction (GUI), a cli or command (CLI), a server,
   endpoint or invocation (HTTP/WS), a domain or code `concept`, a `flow`, or a `format`.
2. **Write.** Have a writer fold the story into the book, under the rules below.
3. **Review.** Once `ostler doctor` is green for the touched nodes, have a reviewer read the
   book against the diff. Skip this step on a turn that repairs a failed check.
4. **Triage.** Sort the review's findings yourself: a real in-scope defect, a pre-existing
   defect outside this story, or a finding the written model does not support.
5. **Fix.** Have a fixer repair the real findings, then converge `ostler doctor` again.
6. **Return** the result.

## Subagents

Spawn subagents through your harness's own task or agent tool. Pick each one's model by the
task: a lookup on the strongest model wastes it, and a review on the cheapest misses what it is
there to catch.

| Seat | Model | Sees | May touch |
| --- | --- | --- | --- |
| Lookup: is a symbol grounded, what a file declares | the cheapest and fastest | the question | nothing |
| Writer | a strong one | the inputs above, the worklist and the skill | the book |
| Reviewer | the strongest, started fresh | the story, the epic, the diff, the worklist and the nodes the writer touched, never the writer's notes or your reasoning | nothing |
| Fixer: one group of real findings | a strong one | its findings, their targets and your triage verdict | the nodes its findings cite |

Give each seat its inputs in the brief, and the check that proves its part. No two writing
seats edit the same node at once. You stay the owner: read what every writing seat changed, run
`ostler fmt` and `ostler doctor` yourself, and write the result yourself.

## The writer's rules

- **No documentable contract is no prose, not no work.** A pure internal refactor, a test-only
  change, or configuration with no observable contract gets no new nodes. A new source file or
  symbol is not internal by default: represent a new service, surface, element, behavior,
  concept or format unless the diff proves otherwise. Grounding is still owed.
- **Ground every changed production file.** The gate maps the diff onto the graph. Each changed
  production unit must be owned *directly*: **every** changed symbol named as `path::symbol` in
  some node's `code:` bullet, or, for a file with no symbols the inventory can see (a config or a
  manifest), the file path itself. A node that describes the behavior in prose without naming
  the file does not own it. Copy each worklist entry verbatim: a Go method is
  `path.go::(*Type).Method`, not `path.go::Type.Method`.
- **A deleted symbol or file needs no citation.** `ostler doctor` rejects every `code:` target
  that is not there. Remove a bullet that cites something deleted, or the node if it described
  only what was deleted. A `missing-code-symbol` after a refactor means the citation is stale:
  open the file, read what it declares now, and cite that.
- **When a contract moved, author from the code** (Playbook B): `ostler search` or `ostler list`
  for the node, `ostler scaffold` it if it is missing, then the as-built prose and bullets. Set
  `code:` and `tests:` to real `path::symbol` references, and omit `tests:` rather than invent
  one. `verify:` is a call from the check vocabulary, never a test name. Run `ostler checks`
  before writing a call not yet written this run: `absent` takes `subject`, `visible` takes
  `locator`, and a guessed argument is a blocking `unparsed-check`.
- **One provable claim per normative bullet.** Split on the real seams by repeating the key.
  `doctor` errors past 700 characters.
- **A check goes under the claim it observes.** A `verify:` binds to the nearest normative bullet
  above it, and one written before any of them binds to the node's whole contract.
- **Every node that mints an obligation declares at least one observation.** A node whose
  `does:`, `raises:` or `states:` bullets carry no `verify:` is `undeclared-obligation`.
- **A check earns its place only if it can go red on the defect its claim forbids.** Name the
  subject concretely, assert the before-state, and discriminate the claim from its nearest
  plausible defect. A split bullet does not owe a new check per fragment.
- **Fill the whole contract.** Fields with `type`, `required` and `default`, every flag and
  argument, `does:` as ordered effects, errors and exit or status codes, and for UI the `role:`,
  `name:`, `placement:`, `keyboard:` and `states:` contract. Prefer narrow, evidence-backed prose:
  "click controls reorder tabs", not "keyboard reordering works", unless a keyboard test proves it.
- **Materialize implemented journeys as flows.** If the story implements a journey slice from the
  epic and the book has no matching `flow`, scaffold one with `ostler scaffold flow
  <journey-slug> --service <service> --title "<Journey title>"` and fill its `start:`, linked
  `steps:`, `end:` and `verify:` from the as-built surfaces. A story that only builds a
  prerequisite documents the prerequisite contract and invents no flow.
- **Never weaken an author-owned requirement to match the code.** An invariant, a journey
  completion condition, a persistence rule, an event contract or a concurrency requirement that
  the code contradicts is a decision that is not yours. Return `blocked` and name it.

## The reviewer's brief

The reviewer starts fresh, so its findings come from the story and the diff, not from the
writer's account of them. Hand it the story path, the epic path, the spec dir, each changed repo,
the worklist and the list of nodes the writer touched. Tell it to read the diff itself, and to
query the graph rather than infer it from the markdown: `ostler graph --path`, `--bullet
'code=mod.py::Sym' --ids`, `--orphans`.

Its scope is the nodes that document behavior this story's changed references reach, and the
nodes the diff should have created. A defect outside that scope is pre-existing and goes in
`notes`, never in the findings. It lists every in-scope defect it sees in one pass, each as one
line:

```text
D1 [node-type] docs/features/acme/gui/screens/editor.md#insert-widget: browser click action is under ## Invocations; move it to ## Interactions.
```

The kind is one of `node-type`, `missing-node`, `flow-coverage`, `overclaim`,
`bullet-granularity`, `grounding`, `verify-overclaim` or `author-decision`, each defined in
`references/defect-kinds.md`. A defect that fits none of them is not a defect. When its reading
and a reference disagree, the reference wins. In `semantic` mode, repository-local doctor cannot
resolve service-repo `code:` paths, so a `dangling-code-ref` or `missing-code-symbol` alone is
not a finding.

## The fixer's brief

Hand the fixer its findings by id, their targets and your verdict. It makes the smallest edit
the evidence supports, or weakens an overclaim to the behavior the evidence proves. Every node
the findings do not cite stays exactly as it is: a rewritten node is one the reviewer must read
again, and it will find a different real defect there.

## Converge

Run `ostler fmt <the docs you touched>`, then `ostler doctor` from the docs root (`-C` if
needed). Fix, re-run and repeat until `doctor` reports zero errors for the touched nodes. To
narrow the report, `ostler doctor --json 2>/dev/null` emits `{org, profile, epics, errors,
warnings, findings}`: `findings` is the list, and `errors` and `warnings` are counts. Keep stderr
out of the pipe, because one warning line on stdout makes the document unparseable.

In `semantic` multi-repo mode, repository-local doctor cannot resolve service-repo `code:` paths
beneath the separate docs root. Report its `dangling-code-ref` and `missing-code-symbol` findings
in `notes`, and do not return `blocked` for those two codes alone. Every structural, relation,
schema and local grounding error stays blocking. Never silence a finding by deleting a
meaningful bullet.

## Blocked

Return `blocked` only when the book cannot be made true of this code without a decision that is
not yours, and name the item in `notes`. Never claim success or remove a requirement to pass.

## Commit Identity

Every commit carries `Epic: {{ workhorse_var('epic') }}` and
`Story: {{ workhorse_var('story_id') }}` as footers, spelled exactly so and nowhere else in the
message, not bracketed into the subject. The run record ties a commit back to its story through
them.

## Output

Return the JSON document as the LAST thing in your final response, its keys at the top level, with no wrapper object around them. Any other shape fails to parse and the node is retried.

{{ result_schema }}
