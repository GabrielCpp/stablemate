---
agent: agent
---

# Repair the Gate on a Drained Backlog Item

The change you wrote for this item is in the working tree and one of the repo's own gates
rejected it. Your only job is to make that gate pass, leaving the rest of the change alone.

## Inputs (authoritative — do not rediscover)

- Backlog item: {{ workhorse_var('bullet_text') }}
- Story: `{{ workhorse_var('story_path') }}`
- Spec directory: `{{ workhorse_var('spec_dir') }}`

### What the gate reported

{{ workhorse_var('gate_report') }}

{% if operator_context %}
### Operator answer (authoritative ground truth)

You parked this turn on a question and an operator answered it. Treat the following as fact:
it overrides any earlier assumption in the item, the story or the code.

{{ workhorse_var('operator_context') }}
{% endif %}

## Steps

1. **Reproduce it.** Run the command above in the directory above, exactly as written. Do not
   substitute one you believe is equivalent — the gate re-runs this one.
2. **Read what it points at.** Open every file and line the output names, and work out why the
   change this item made caused it, before editing anything.
3. **Fix the cause, minimally.** Do **not** weaken, suppress or delete the gate to make it
   pass — that removes the check instead of the defect. A targeted suppression is defensible
   only when the rule is wrong for one specific line, and then you say why in the notes.
4. **Re-run the command and confirm it is clean.** The workflow re-runs it deterministically
   the moment this turn ends, so a still-red tree simply comes back to you.

Repair only what the gate objected to. A neighbouring surface you pass through is not this
item's, and reworking it is a failing QA downstream rather than a bonus.

Commit the completed repair in each repository it changed. Every commit carries
`Epic: {{ workhorse_var('epic') }}` and `Story: {{ workhorse_var('story_id') }}` as footers,
spelled exactly so and nowhere else in the message — not bracketed into the subject. Do not push or open a PR; the workflow owns those.

## Stop Conditions

Return `blocked` rather than guessing when the gate can only be satisfied by a product or
scope decision that is written down nowhere, or when passing it requires a credential or a
spend you do not have. A block parks the run for an operator and comes back to this turn with
their answer — it costs one question and loses no work.

## Return Format

Return the JSON document as the LAST thing in your final response — its keys at the top level, with no wrapper object around them. Any other shape fails to parse and the node is retried.

{{ result_schema }}
