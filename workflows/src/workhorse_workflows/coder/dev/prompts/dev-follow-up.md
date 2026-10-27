---
agent: agent
---

# Continue The Phase

This turn continues the {{ workhorse_var('phase') }} phase of story
`{{ workhorse_var('story_id') }}` on this conversation. Its brief still governs it, and this
note carries only what changed since your last turn. When you no longer hold the brief, read
it again from `{{ workhorse_var('brief_path') }}` before you act.
{% if report %}

## The workflow sent this turn back

{{ workhorse_var('report') }}

Fix what this report names, and leave the rest of the work as it stands. Do not weaken, skip
or delete a check.
{% endif %}
{% if qa_findings %}

## Findings QA filed against this work

{{ workhorse_var('qa_findings') }}

Fix each one at its cause, across every case its criterion covers.
{% endif %}
{% if findings %}

## Findings filed against this work

These findings are open, and each one needs a section in the answer file:

{{ workhorse_var('findings') }}
{% endif %}
{% if review_prefix %}

A new review in this turn files its findings as `{{ workhorse_var('review_prefix') }}n`.
{% endif %}
{% if operator_context %}

## Operator answer (authoritative ground truth)

An operator answered a block on this story. Treat the answer as fact, fold it into the plan
section it moves, and do not raise the same block again.

{{ workhorse_var('operator_context') }}
{% endif %}
{% if note %}

## The task for this turn

{{ workhorse_var('note') }}
{% endif %}

## Result

End your reply with the JSON result the brief's result section describes, as the last thing
in your response, its keys at the top level. Every rule of the brief still holds: the story's
status line, the commit footers, and every gate green before you claim `ready`.{% if phase == "review" %}
Re-state the plan's full structure, because it replaces what the last turn returned.{% endif %}
