---
agent: agent
---

# Fix One Drained Backlog Item

One item was drained off the backlog and seeded as a one-criterion story. This turn does the
whole job: work out what the repair is, then write it. What has to exist when you stop is the
committed change in every repository it belongs in — the repo's own lint and test gates run
against it the moment this turn ends, and a QA turn reads it after that.

Plan the repair first, then implement that plan completely. Both halves are this turn's; there
is no separate planning pass ahead of you and no second implementation pass behind you.

## Inputs (authoritative — do not rediscover)

- Backlog item: {{ workhorse_var('bullet_text') }}
- Story: `{{ workhorse_var('story_path') }}`
- Spec directory: `{{ workhorse_var('spec_dir') }}`

Fix **only** the item above, against the story at that path. Do not search the backlog or git
history for something else to repair, and do not substitute a different item.

{% if operator_context %}
### Operator answer (authoritative ground truth)

You parked this turn on a question and an operator answered it. Treat the following as fact:
it overrides any earlier assumption in the item, the story or the code.

{{ workhorse_var('operator_context') }}
{% endif %}

## Scope

The item is a repair, not a feature. Keep the change to the behaviour it names:

- Cover the fix with a test that fails without it, in whatever the touched layer's tests
  already look like.
- Leave unrelated surfaces alone. A repair that quietly reworks neighbouring code is a
  failing QA downstream, not a bonus.
- Do not file new backlog items. This lane is draining the backlog; an item written into it
  now is one the drain re-reads in the same pass.

## Stop Conditions

Return `blocked` rather than guessing when the item needs a product or scope decision that is
written down nowhere, when repairing it requires a credential or a spend you do not have, or
when the behaviour it describes does not exist in these repositories. A block parks the run for
an operator and comes back to this turn with their answer — it costs one question and loses no
work, where a guess costs the review that would have caught it.

## Commit Identity

Commit the completed repair in each repository it changed. Every Conventional Commit subject
ends with `[{{ workhorse_var('story_id') }}]`, after its description. Every commit also carries
`Epic: {{ workhorse_var('epic') }}` and `Story: {{ workhorse_var('story_id') }}` as trailers,
spelled exactly so. Do not push or open a PR; the workflow owns those.

## Return Format

Return the JSON document as the LAST thing in your final response — its keys at the top level, with no wrapper object around them. Any other shape fails to parse and the node is retried.

{{ result_schema }}
