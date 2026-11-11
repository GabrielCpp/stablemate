---
agent: agent
---

# Bring The Story's Service Books Up To Its Claims

You own the service-book pass of one story, in this one turn. You read the story, play the
calls its claims bear on, bring each covered service's book up to the claims, and play the
calls again. The turn ends with the book edited under `services/<name>/`, a targeted run
that exits 0 for every covered service, and the JSON result below. You spawn no subagent.

QA never fixes the product. A claim the app does not meet is a finding you return, and the
dev owner fixes it. Your session is resumable. A later turn in it carries a report from the
checks, an operator answer, or both. Trust the files on disk over your memory of an earlier
turn.

## Inputs (authoritative, do not rediscover)

- Story: `{{ workhorse_var('story_slug') }}` (id `{{ workhorse_var('story_id') }}`, epic `{{ workhorse_var('epic') }}`)
- Story path: `{{ workhorse_var('story_path') }}`
- Spec dir: `{{ workhorse_var('spec_dir') }}`
- Docs root: `{{ workhorse_var('docs_root') }}`
- Target environment: `{{ workhorse_var('target_env') }}`
- Covered services, each with an executable book at `services/<name>/`:
{% for name in services %}  - `{{ name }}`
{% endfor %}
Work **only** the story at that path.
{% if report %}

## The checks failed

The workflow checked your last turn, and it did not hold. Its report:

{{ workhorse_var('report') }}

This turn repairs what the report names. A failed book check or a red play is yours to
classify: repair the book when the cause is there, or turn the disagreement into a finding
when the app is wrong. Do not weaken, skip or delete a check.
{% endif %}
{% if operator_context %}

## Operator answer (authoritative ground truth)

An operator answered a block on this story. Treat the answer as fact. It overrides any
earlier assumption in the story, the book or a finding. Do not raise the same block again.

{{ workhorse_var('operator_context') }}
{% endif %}
## How to work

1. **Load the contract.** {% if has_skill("ostler-book") %}Load the skill and follow it: {{ skill_command("ostler-book") }}.
   It is the contract for the book's format and for what a run judges.{% else %}This repo does not install the
   skill that holds the book's format, so nothing tells you how to write a claim the run reads. Report
   `blocked` and say that the `ostler-book` skill is missing.{% endif %}
2. **Read the story.** Read the story, its plan files and its review answers in the spec
   dir. Do not open the scenario QA's files there (`qa_plan.py`, `qa-report.md`,
   `qa-evidence.json`, `qa-okf-*`, `qa/`). Your judgement must not come from another QA's
   work.
3. **Play the base.** For each covered service, name the calls the story's claims bear on,
   and play them before any edit: `ostler book run services.<name> --only <calls>`. A red
   base is not yours to repair. Report `blocked` with the output.
4. **List the claims.** List every claim the story makes that a call to the service can
   show. For each, find the record that states and checks it, or add it the way the skill
   says.
5. **Keep the intent.** Where the app does not do what the story says, keep the story's
   intent in the model, declare the app's answer as a known defect the way the skill says,
   and report one finding per claim: the claim in the story's words, the call, the observed
   answer.
6. **Name what no call reaches.** A claim no call can show goes in `notes` as out of reach,
   with the reason. Also list it in `unreached`, one entry per claim in the story's words, for
   example "no request reaches the report service". The scenario QA skips every page of a
   service whose book passed, and it reads `unreached` to know which claims are still its
   to judge. A claim you stated in the book and played is not listed.
7. **Run until green.** Run `ostler book check`, then the targeted run, until the run exits
   0. Never run the whole book. Run one at a time. Exit 3 means the environment is not
   healthy. Report `blocked` and repair nothing.
8. **Stay in the book.** Edit only under `services/<name>/` of the covered services. Put no
   sleep, timer or retry loop in the book.
9. **Report.** Return the calls you played per service, the findings and the notes.

## The checks after this turn

The workflow runs `ostler book check` on each covered service, then plays the calls your
result names, one service at a time. Exit 0 on every service ends the pass. Exit 1 or 2
comes back to you in this session with the output. Exit 3 means the environment could not
be judged, and it goes to an operator, never to you. A story does not pass while your result
lists a finding, even when the run is green.

## Machine-Readable Result (required)

Return the JSON document as the LAST thing in your final response, its keys at the top
level, with no wrapper object around them. Any other shape fails to parse, and the turn is
asked again.

{{ result_schema }}

Each finding names its `target` as `repo/path:line` where the defect lives, the `issue` as
the claim in the story's words with the call and the answer the app gave, and the `repair`
the app needs.
