---
agent: agent
---

# Specify The Story In The Book

No code for this story exists yet. You write what it will do, before anyone builds it. The
dev owner builds to what you write, and the book lane plays the claims you write. A behaviour
you leave out is one nobody builds on purpose and nobody checks. This turn ends with the
story's behaviour model written, the book delta derived from it, `ostler book check` exiting 0
for every service, and the JSON result below.

Your session is resumable. A later turn on this story continues this conversation with the
workflow's report or an operator's answer.

## Inputs (authoritative, do not rediscover)

- Story: `{{ workhorse_var('story_slug') }}` (id `{{ workhorse_var('story_id') }}`, epic `{{ workhorse_var('epic') }}`)
- Story path: `{{ workhorse_var('story_path') }}`
- Spec dir: `{{ workhorse_var('spec_dir') }}`
- Docs root: `{{ workhorse_var('docs_root') }}`
- Book root: `{{ workhorse_var('book_root') }}`
- Parent epic with authoritative user journeys: `{{ workhorse_var('epic_path') }}`
{% if report %}

## The checks failed

The workflow checked your last turn, and `ostler book check` did not hold. Its report:

{{ workhorse_var('report') }}

This turn repairs what the report names, and runs no new review. Every file the report does not name stays as it is.
{% endif %}
{% if operator_context %}

## Operator answer (authoritative ground truth)

An operator answered a block on this story. Treat the answer as fact. It overrides any earlier
assumption in the story, the model or the book. Do not raise the same block again.

{{ workhorse_var('operator_context') }}
{% endif %}

## The decisions the executable books keep

These services have an executable book at `{{ workhorse_var('service_books') }}/<name>/`, with a
`service.py`: {% for name in book_services %}`{{ name }}`{% if not loop.last %}, {% endif %}{% endfor %}. For each one, read `{{ workhorse_var('service_books') }}/<name>/decisions/*.md` and
`{{ workhorse_var('service_books') }}/<name>/DISAGREEMENTS.md` before you model. A decision says why the service behaves as
it does and which story settled it. Where the story changes a behaviour a decision explains,
name the decision in the model and say whether the story keeps it or overturns it.

Then run `ostler book pages` from `{{ workhorse_var('book_root') }}` and read every page it lists. They are few. They hold the product's words and the rules above any one service, at the company, team and product levels. Use its words.

## 1. The behaviour model

{% if has_skill("behaviour-model") %}
Load the skill and follow it: {{ skill_command("behaviour-model") }}
{% else %}
The model names every record the story touches with its states, every action that reaches a
record with its inputs, a state × action matrix per record, and the invariants that hold in
every state.
{% endif %}

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

### The executable books

{% if has_skill("ostler-book") %}Load the skill and follow it: {{ skill_command("ostler-book") }}
{% else %}This repo does not install the skill that holds the book's format, so nothing tells you how to write a claim the run reads. Return `blocked` and say that the `ostler-book` skill is missing.
{% endif %}
Write the story's claims into each covered service's book as intent, before any code exists:

- New or changed journeys, cells, rules, fixtures and endpoints, each stated as the behaviour the
  story owes. A book element the story changes is rewritten to the new behaviour, never annotated
  with what the story adds.
- Every decided cell of the model becomes a claim the run can judge. The empty value, the bound and
  the refusal each get their own, not only the happy path.
- A decision the story settles goes in `{{ workhorse_var('service_books') }}/<name>/decisions/` with the story that settled it.
- Name an endpoint by the method and path the epic or the book's existing conventions give it.
  Where nothing names it, choose the name and state it in the book. Dev builds to that name.
- A claim no call or backstage step can observe stays in the model and out of the book. Say so in
  `notes`.

You do not run the app, and you do not play the book. The new claims are expected to fail against
the current app until the build. Edit only under `{{ workhorse_var('service_books') }}/<name>/` and the spec dir.

Run every `ostler book` and `ostler env` command from `{{ workhorse_var('book_root') }}`.
Run `ostler book check {{ workhorse_var('service_package') }}.<name>` for each service until it exits 0. It builds
everything the book declares with no stack, so a claim the format cannot read fails there. The
workflow reads the changed book paths from the tree.

{% include "shared/prompts/_step-cost.md" %}

{% include "shared/prompts/_time-allowance.md" %}

## Seats

You write the model and the book yourself. Then hand one reviewer, started fresh on a strong
model, the story path, the epic path, `model.md` and the list of book paths you touched, never your
notes. It answers two questions and changes nothing:

1. Which acceptance criterion or journey step has no cell in the model, and which bound or
   refusal the story implies has no input class?
2. Which decided cell has no claim in the book that a run can judge, and which claim would
   pass on the unchanged system?

Answer each real finding in the model and the book. A finding the story and the epic do not
support goes in `notes`.

When your harness offers agents named `lookup` or `worker`, send lookups to `lookup` and the
reviewer to `worker`.

## Converge

Run `ostler book check {{ workhorse_var('service_package') }}.<name>` for each service. Fix, re-run and repeat until
each exits 0.

## Blocked

Return `blocked` only when the story cannot be specified without a decision that is not yours,
and name the decision in `notes`. A story whose acceptance criteria contradict each other, or
contradict an invariant the book already states, is such a decision.

## Output

Return the JSON document as the LAST thing in your final response, its keys at the top level, with no wrapper object around them. Any other shape fails to parse and the node is retried.

{{ result_schema }}
