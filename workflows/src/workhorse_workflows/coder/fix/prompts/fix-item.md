---
agent: agent
---

# Fix One Drained Backlog Item

One item was drained off the backlog and seeded as a one-criterion story. This turn does the
whole job: work out what the repair is, then write it. What has to exist when you stop is the
change itself, in the working tree of whatever repositories it belongs in — the repo's own
lint and test gates run against it the moment this turn ends, and a QA turn reads it after
that.

Plan the repair first, then implement that plan completely. Both halves are this turn's; there
is no separate planning pass ahead of you and no second implementation pass behind you.

## Inputs (authoritative — do not rediscover)

- Backlog item: {{ workhorse_var('bullet_text') }}
- Story: `{{ workhorse_var('story_path') }}`
- Spec directory: `{{ workhorse_var('spec_dir') }}`

Fix **only** the item above, against the story at that path. Do not search the backlog or git
history for something else to repair, and do not substitute a different item.

### Gate Report

{{ workhorse_var('gate_report') }}

If that section names a failing command, this is a repair lap: the change you already wrote is
in the tree and a gate rejected it. Re-run the named command in the directory it names, repair
what it printed, and leave the rest of the change alone.

### Operator Context

{{ workhorse_var('operator_context') }}

If that section is non-empty, it is the answer to a question this turn parked on earlier.
Treat it as settled and proceed.

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

## Return Format

Return this exact JSON object as the LAST thing in your final response — these keys at its top
level, with no wrapper object around them. Any other shape fails to parse and the node is
retried:

```json
{"status": "done|applied|no_changes_needed|needs_changes|blocked", "notes": "what you changed, where, and how you exercised it"}
```

- `status`: `done` or `applied` when the repair is written and exercised; `no_changes_needed`
  when the item was already fixed in the tree; `needs_changes` when you got part of the way and
  the rest is still open; `blocked` for a stop condition above. There is no blank answer — a
  turn that cannot name one of these five has not reported, and the node is retried.
- `notes`: the files changed, the commands you ran to exercise them, and for a non-`done`
  status the specific thing that stopped you. This text is handed to the operator gate and to
  the QA turn that follows, so it has to be enough to act on.
