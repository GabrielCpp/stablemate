---
agent: agent
---

# Review Story Documentation

Independently review the frozen implementation diff and the current OKF book after the
documentation author has finished. Do not edit code or documentation. Your decision is a hard
gate before QA.

You and the author are held to the same written model, so that a finding you file is one the
author could have read beforehand: {{ skill_load_ref("ostler-okf", skill_dir() + "/ostler-okf/SKILL.md") }}
Judge against its references, not against a standard you re-derive here — `references/node-types/<type>.md`
for what a type owes, `references/bullet-grammar.md` for claim splitting and check attribution,
`references/check-vocabulary.md` for the checks and their signatures, and
`references/defect-kinds.md` for the definition of every `kind` you may return. When your reading
and a reference disagree, the reference wins and there is no finding.

## Inputs

- Story: `{{ workhorse_var('story_path') }}`
- Spec directory: `{{ workhorse_var('spec_dir') }}`
- Docs root: `{{ workhorse_var('docs_path') }}`
- Features root: `{{ workhorse_var('features_root') }}`
- Parent epic with authoritative user journeys: `{{ workhorse_var('epic_path') }}`
- Author status: `{{ workhorse_var('author_status') }}`
- Author notes: `{{ workhorse_var('author_notes') }}`
- Deterministic gate: `{{ workhorse_var('gate_notes') }}`
- Previous semantic review notes: `{{ workhorse_var('review_notes') }}`

## What this story is answerable for

{% if workhorse_var('obligations') %}
This story changed exactly these production references:

{% for ref in workhorse_var('obligations') %}
- `{{ ref }}`
{% endfor %}

They are your scope. A node is in scope when it documents behavior reached by one of those
references, or when this story's diff should have created it and did not.
{% else %}
No changed-reference worklist could be computed for this story, so scope it yourself from the
branch commits since the story/epic base — the diff, not the book.
{% endif %}

**A defect outside that scope is pre-existing, and pre-existing is not grounds to refuse.**
The book was already incomplete when this story started; the author was not asked to finish
it and cannot, and a finding against a node this story never touched returns unfixed next
pass and every pass after it. Say it in `notes` if it matters. Do not put it in `findings`.

**Find everything you are going to find, this pass.** List every in-scope defect you can see
now, however many that is — a long list of real findings is a good review. A defect you could
have named this pass and held back is not grounds for a later refusal: if the author repairs
what you listed, you approve.

## The review

Read the story, the parent epic's `## User Journeys`, plan context, working tree, branch commits since
the story/epic base, and affected OKF nodes. Include QA, regression, CI, merge-resolution, and
inline-fix mutations made after the initial review. Approve when the book tells the truth about
the system *within that scope* — as a description of the system as it now stands, not as a
changelog of this story. In particular, for the surfaces this story touched:

- every new or changed service, screen, component, interaction, CLI command, endpoint,
  invocation, flow, concept, and format has the correct typed node and reachable relationships;
- any greenfield journey slice implemented by this story has a `flow` node under
  `docs/features/<service>/flows/` with linked `steps:` through the as-built surfaces; the author
  journey plan alone is not OKF documentation;
- structured bullets contain the full behavioral contract, including states, fields,
  preconditions, effects, errors, accessibility, and boundaries where applicable;
- each normative bullet carries **one provable claim** (`references/bullet-grammar.md`; which
  keys are normative is in the type's own reference). Flag a bullet whose success effect, error
  cases, persistence and emissions are fused into one sentence, and name the seams to split it
  on; the repair is repeating the key, not rewording. Splitting a bullet does **not** by itself
  owe a new check per fragment — a `verify:` above a group of normative bullets binds to the
  node's contract and covers all of them, so do not file `verify-overclaim` against bullets the
  previous lap correctly split;
- `code:` and `tests:` cite real implementation and tests without using broad or invented refs,
  and every ref names something that currently exists. A symbol or file this story deleted needs
  no citation at all; do not send the author back to add one, and flag a bullet that still cites
  something deleted as a defect to remove;
- `verify:` declares the **observation**, not a ref, and is judged by
  `references/check-vocabulary.md` (a check outside that vocabulary or carrying a test id is
  `unparsed-check`) and by the document-order attribution rule in `references/bullet-grammar.md`
  (a check written above the claim it observes is credited to the previous claim — a defect to
  reorder). A check that cannot go red on the defect its claim forbids is `verify-overclaim`;
  the bar is in `references/defect-kinds.md`;
- every node this story touched that mints obligations **declares at least one observation**
  (`undeclared-obligation`, doctor's warn — which is why this review is where it gets caught);
- behavior this story changed on an in-scope node is described completely enough to guide a
  behavior-equivalent implementation, and behavior it did not change was not *degraded* —
  a bullet the author deleted or weakened is a defect, a bullet that was already thin before
  this story is not;
- author-owned requirements were not weakened to match code;
- `not_required` is used only when the diff is genuinely internal and changes no observable or
  reusable contract. A new service, screen, component, endpoint, command, flow, concept, or format
  is never `not_required`.

## Query the graph, don't infer it from the file

Reading the markdown tells you what a heading *looks like* it belongs to. `ostler graph` tells
you what it actually parsed as, which is the thing the book is judged on and the thing a
mis-nested heading silently changes. Use it to prove a structural finding before you file it —
and to withdraw one when the graph says the file is fine. The recipes, verbatim; the `ostler`
skill's `references/command-interface.md` has the rest.

```bash
ostler graph --surface acme                          # the whole service, as an outline tree
ostler graph --path 'concept:Widget / field'         # a concept's fields (/ = descendant, > = direct)
ostler graph --path 'concept:Widget / field' --tree  # …with the nesting shown
ostler graph --type field --under <id> --depth 1     # a node's direct children of one type
ostler graph --bullet 'code=mod.py::Sym' --ids       # is this symbol already grounded, and where
ostler graph --orphans                               # nodes no edge reaches
```

Do not spend the review guessing flags. If a query does not exist above, it is not the one to
reach for — read the file and say what you saw.

**In `semantic` multi-repo mode, repository-local `ostler doctor` cannot resolve service-repo
`code:` paths beneath the separate docs root.** Its `dangling-code-ref` and `missing-code-symbol`
findings are yours to judge against the real tree, not evidence on their own: the author is
excused from returning `blocked` for those two codes alone, so do not file a `grounding` finding
that rests only on them. Every other doctor error is blocking for the author and fair game here.

{% if workhorse_var('review_notes') %}
## Re-review discipline

This is not a fresh exploratory review. First verify each prior semantic finding above. If a
prior item is now resolved, do not restate it. If it is still wrong, keep the same item number
and make the requested correction more exact. Add a new item only for a material blocking defect
that is in the files/anchors this story touched, that would make the current book false, and
that **the author's repair introduced** — a defect that was already there last pass was in
scope last pass, and raising it now is the failure mode this discipline exists to stop. If every
prior item is resolved and the repair introduced nothing, approve.
{% endif %}

When returning `status=revise`, write numbered checklist findings with stable IDs and exact
targets, for example:

```text
D1 [node-type] docs/features/acme/gui/screens/editor.md#insert-widget: browser click action is under ## Invocations; move it to ## Interactions.
D2 [overclaim] docs/features/acme/flows/widget.md: cited test clicks controls, so do not claim keyboard reorder behavior.
```

Each finding must name the file/anchor, classify the defect as one of `node-type`,
`missing-node`, `flow-coverage`, `overclaim`, `bullet-granularity`, `grounding`,
`verify-overclaim` or `author-decision` — each defined in the skill's
`references/defect-kinds.md`, and a defect that fits none of the eight is not a defect — and
state the smallest acceptable repair. Do not return a broad prose paragraph that the author must
reinterpret.

Return JSON only:

```json
{"status": "approved", "findings": [], "notes": "The current OKF book fully covers the reviewed implementation delta."}
```

Use `status=revise` only with at least one structured finding in `findings`. Use
`status=blocked` only when convergence requires a product or author decision. Never approve on
the promise of a later documentation update.

Each finding has this shape:

```json
{
  "status": "revise",
  "findings": [
    {
      "id": "D1",
      "kind": "node-type",
      "target": "docs/features/acme/gui/screens/editor.md#insert-widget",
      "issue": "Browser click action is under ## Invocations.",
      "repair": "Move it under ## Interactions as an interaction node."
    }
  ],
  "notes": "One or two sentence summary; the findings list is the repair contract."
}
```
