---
agent: agent
---

# Specify The Story In The Book

No code for this story exists yet. You write what it will do, before anyone builds it. The
dev owner builds to what you write, and QA compiles its scored plan from your `verify:`
checks. A behaviour you leave out is one nobody builds on purpose and nobody checks. This turn
ends with the story's behaviour model written, the book delta derived from it, `ostler doctor`
green on the nodes you touched, and the JSON result below.

Your session is resumable. A later turn on this story continues this conversation with the
workflow's report or an operator's answer.

## Inputs (authoritative, do not rediscover)

- Story: `{{ workhorse_var('story_slug') }}` (id `{{ workhorse_var('story_id') }}`, epic `{{ workhorse_var('epic') }}`)
- Story path: `{{ workhorse_var('story_path') }}`
- Spec dir: `{{ workhorse_var('spec_dir') }}`
- Docs root: `{{ workhorse_var('docs_root') }}`
- OKF services root: `{{ workhorse_var('services_root') }}`
- Parent epic with authoritative user journeys: `{{ workhorse_var('epic_path') }}`
{% if report %}

## The checks failed

The workflow checked your last turn, and `ostler doctor` did not hold on the nodes you
touched. Its report:

{{ workhorse_var('report') }}

This turn repairs what the report names, and runs no new review. If the report points at a
`doctor-errors.txt`, read that file. Every node the report does not name stays as it is.
{% endif %}
{% if operator_context %}

## Operator answer (authoritative ground truth)

An operator answered a block on this story. Treat the answer as fact. It overrides any earlier
assumption in the story, the model or the book. Do not raise the same block again.

{{ workhorse_var('operator_context') }}
{% endif %}

## 1. The behaviour model

Load the skill and follow it: {{ skill_command("behaviour-model") }}

Write the model to `{{ workhorse_var('spec_dir') }}/model.md`, creating the folder when it is
missing. Its sources are the story's acceptance criteria, the epic's `## User Journeys`, and the
book as it stands for every record and surface the story reaches. The current code is a source
only for what already exists: read it to learn a record's present states, never to decide what
the story's new behaviour is.

The model is done when:

- every record the story touches has its states and the read that tells them apart,
- every action has the surface that reaches it and its inputs partitioned into classes, with a
  class named at each bound the story or the epic states or implies,
- every cell of every lifecycle matrix holds a transition with its observable effects, a
  `refuse`, a `no-op` or an `impossible` with its reason.

A cell you cannot decide from those sources is an open cell. Decide it by the convention the
book already follows for a similar record when one exists, and say so in the cell. A cell that
needs a product decision nobody has written down makes this turn `blocked`, with the question
in `notes`.

## 2. The book delta

Load the skill and follow it: {{ skill_command("ostler-okf") }}

Fold the model into the book as the current spec, with the scaffold, author, fmt and doctor
loop the skill carries:

- Every surface, element, behaviour, concept, format or flow the story adds gets its node,
  scaffolded with `ostler scaffold` when it is missing. A node the story changes is rewritten to
  the new behaviour, never annotated with what the story adds.
- Every decided cell becomes a normative bullet (`does:`, `raises:`, `states:`) on the node of
  the surface that reaches it, with a `verify:` under it that goes red on the defect the cell
  forbids. The empty value, the bound and the refusal each get their check, not only the happy
  path.
- A journey slice the story implements becomes a `flow` with its `start:`, linked `steps:`,
  `end:` and `verify:`.
- Write no `code:` and no `tests:` bullet for behaviour the story adds. The build pass grounds
  them after dev. Existing `code:` bullets stay as they are.
- Name a UI element by the role and accessible name the story, the epic or a mockup gives it,
  and an endpoint by the method and path the epic or the book's existing conventions give it.
  Where nothing names it, choose the name and state it in the node. Dev builds to that name.
- Run `ostler checks` before writing a check call not yet written this run. A guessed argument
  is a blocking `unparsed-check`.

{% include "shared/prompts/_step-cost.md" %}

## Seats

You write the model and the book yourself. Then hand one reviewer, started fresh on a strong
model, the story path, the epic path, `model.md` and the list of nodes you touched, never your
notes. It answers two questions and changes nothing:

1. Which acceptance criterion or journey step has no cell in the model, and which bound or
   refusal the story implies has no input class?
2. Which decided cell has no bullet with a `verify:` in the book, and which `verify:` would
   pass on the unchanged system?

Answer each real finding in the model and the book. A finding the story and the epic do not
support goes in `notes`.

When your harness offers agents named `lookup` or `worker`, send lookups to `lookup` and the
reviewer to `worker`.

## Converge

Run `ostler fmt <the docs you touched>`, then `ostler doctor` from the docs root (`-C` if
needed). Fix, re-run and repeat until `doctor` reports zero errors for the touched nodes.
`ostler doctor --json 2>/dev/null` emits `{org, profile, epics, errors, warnings, findings}`.
Keep stderr out of the pipe.

## Blocked

Return `blocked` only when the story cannot be specified without a decision that is not yours,
and name the decision in `notes`. A story whose acceptance criteria contradict each other, or
contradict an invariant the book already states, is such a decision.

## Output

Return the JSON document as the LAST thing in your final response, its keys at the top level, with no wrapper object around them. Any other shape fails to parse and the node is retried.

{{ result_schema }}
