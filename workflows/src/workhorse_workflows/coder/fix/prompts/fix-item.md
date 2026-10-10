---
agent: agent
---

# Own One Drained Backlog Item

One item was drained off the backlog and seeded as a one-criterion story. You own it end to
end. Your subagents fix it and QA it, and you triage what QA finds and have it repaired, all
inside this turn. What has to exist when you stop is the committed repair in every
repository it belongs in, and a QA record that shows it works.

## Inputs (authoritative, do not rediscover)

- Backlog item: {{ workhorse_var('bullet_text') }}
- Story: `{{ workhorse_var('story_path') }}`
- Spec directory: `{{ workhorse_var('spec_dir') }}`
- QA directory: `{{ workhorse_var('qa_dir') }}`
- Target environment: `{{ workhorse_var('target_env') }}`

Fix **only** the item above, against the story at that path. Do not search the backlog or git
history for something else to repair, and do not substitute a different item.
{% if report %}

## The checks failed

The workflow ran the repo's own gates over your last turn, and they did not hold. Its report:

{{ workhorse_var('report') }}

This turn repairs what the report names. Run each command exactly as written, in the
directory it names. Find why this item's change caused it, and fix the cause. Do not weaken,
skip or delete a gate to make it pass. Run QA again only when the repair changed behaviour.
{% endif %}
{% if operator_context %}

## Operator answer (authoritative ground truth)

You parked on a question and an operator answered it. Treat the answer as fact. It overrides
any earlier assumption in the item, the story or the code. Do not raise the same block again.

{{ workhorse_var('operator_context') }}
{% endif %}

## How to work

1. **Read.** Read the story, its acceptance criterion and the repo's `AGENTS.md`. Look in the
   spec directory first. A turn that was interrupted may have left a plan or a `qa.md` there.
2. **Fix.** Have a fixer write the repair, with a test that fails without it.
3. **QA.** Once the gates below are green, have a fresh QA checker exercise the change.
4. **Triage.** Have a triager sort what QA found: a defect of this fix, a pre-existing failure
   outside its surface, or behaviour the story asks for.
5. **Repair.** Send the real defects back to a fixer, then QA again. Repeat until QA passes.
6. **Commit** and return the result.

## Subagents

Spawn subagents through your harness's own task or agent tool. Pick each one's model by the
task: a lookup on the strongest model wastes it, and a QA check on the cheapest misses what
it is there to catch.

| Seat | Model | Sees | May touch |
| --- | --- | --- | --- |
| Lookup: find callers, summarise a file or a log | the cheapest and fastest | the question | nothing |
| Fixer | a strong one | the item, the story and the files it names | the files the repair needs |
| QA checker | a strong one, in a fresh context | the story, the plan and the diff, never your reasoning | `<spec_dir>/qa.md` only |
| Triager | a strong one | QA's findings, the story and the diff | nothing |

Give each seat its inputs in the brief, and the check that proves its part. You stay the
owner: read what every fixer changed, run the gates yourself, and write the result yourself.
No seat edits the story's status.

### The QA checker's brief

The QA checker establishes what the story claims to fix, from its acceptance criterion. It
runs the narrowest verification that proves it: the touched packages' tests, the layer's lint
gate and, for a user-visible change, the behaviour itself. It rules out the failures a green
suite hides: a 5xx swallowed by the client, a console error, a partial write, a test that
asserts presence rather than the behaviour. It confirms the fix stayed inside its scope.
Pre-existing failures outside the fix's own surface are noted, not counted against it.

It writes what it ran, what it observed and the criterion each observation covers to
`<spec_dir>/qa.md`. It creates that file through `ostler` first:
`timeout 30 ostler create spec <story-name> qa.md`, where `<story-name>` is the folder name of
the spec directory. That stamps the `type: spec.qa` frontmatter. It writes below the `---`
frontmatter block and leaves that block in place.

## Scope

The item is a repair, not a feature. Keep the change to the behaviour it names:

- Cover the fix with a test that fails without it, in whatever the touched layer's tests
  already look like.
- Leave unrelated surfaces alone. A repair that quietly reworks neighbouring code fails QA.
- Do not file new backlog items. This lane is draining the backlog, and an item written into
  it now is one the drain re-reads in the same pass.

## The checks after this turn

The workflow runs each changed repository's own gates (lint, then test). Whatever fails comes
back to you as the next turn in this session, with the report attached. Run those gates
yourself before you return `done`, and leave them green.

## Blocked

Return `blocked` only for a decision an operator alone can make: a product or scope call
written down nowhere, a credential, a spend, or behaviour the item describes that does not
exist in these repositories. First try every route the repo offers: its docs, its
`docs/decisions/` records, its skills. On `blocked`, `notes` holds the one question that
would unblock you and what you ruled out. A block loses no work. The answer comes back to
this session.

## Commit Identity

Commit the completed repair in each repository it changed. Every commit carries
`Epic: {{ workhorse_var('epic') }}` and `Story: {{ workhorse_var('story_id') }}` as footers,
spelled exactly so, and nowhere else in the message. Do not push and do not open a pull
request. The workflow owns both.

## Return Format

`status` is `done` once the repair is committed, the gates are green and QA passed, or
`blocked`. `notes` says what you fixed and what QA observed, or the blocker.

Return the JSON document as the LAST thing in your final response, its keys at the top level,
with no wrapper object around them. Any other shape fails to parse and the node is retried.

{{ result_schema }}
