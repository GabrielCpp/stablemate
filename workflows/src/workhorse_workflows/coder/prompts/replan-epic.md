# Epic Workflow — Epic Replan Stage

You are running the **epic replan** stage of the autonomous epic workflow.

A story hit an operator block, and the operator chose to replan at the **epic** level — their answer revealed that the epic's premise or story breakdown is wrong, not just this one plan. Re-ground the epic and its stories to match reality.

Triggering story: `{{ story_path }}`
Spec/artifact directory: `{{ spec_dir }}`
Epic: `{{ epic }}`
Epic queue: the ostler-managed OKF index `docs/epics/index.md` (read with `ostler todo list`,
edit with `ostler todo add|prune|reorder`).

## Operator answer (authoritative ground truth)
Treat the following as fact. It overrides any earlier assumption in the epic or its stories. Do NOT re-derive or second-guess it; do NOT re-raise the block it answers.
{{ operator_context }}

## What to do
1. **Read before writing.** Read the epic doc (`docs/epics/{{ epic }}/epic.md` or equivalent), every story under it, and whichever of this repo's source trees are needed to confirm the *actual* state. Follow this repo's developer workflow skill and the layer skills that auto-load.
2. **Re-ground to reality.** Correct the epic and the affected stories so they reflect what the operator stated and what actually exists. Remove or rewrite assumptions the answer invalidated (e.g. environments, deploy targets, prerequisites that don't exist). Verify every claim against the real repo/infra state — **never invent** environments, targets, or facts to fill a gap. If something is still genuinely unknown, leave it as an explicit open question rather than fabricating.
3. **Adjust the queue and stories.** Reorder/prune/add epics in the queue with `ostler todo reorder|prune|add`; adjust this epic's story set in its `epic.md` `## Stories` (add/split via `ostler create story --covers --depends`, drop via `ostler delete story`) and set each story's status with `ostler set-status <slug> "<status>"` (or edit its `## Implementation Status` line) so the corrected set of stories is what gets executed next. The workflow re-reads the queue and the epic's stories immediately after this stage.
4. **Preserve completed work.** Do NOT delete or revert code, commits, or passing artifacts. Re-grounding changes plans and docs; it must not discard work that is already correct.
5. **No fabricated evidence.** Do not write simulated QA/deployment artifacts.

## Commit What You Wrote

The workflow does not commit on your behalf. Work still sitting in the working tree when the
story ends parks it for an operator instead of shipping it, so the last thing you do is record
what you wrote:

1. **Stage by explicit path** — never `git add -A`, `git add .` or `git commit -a`. Those sweep
   in whatever else is in the tree, and something else is usually working here. Anything that is
   not yours stays exactly where it is.
2. **One commit per repository**, its subject scoped to the package you changed:

   ```
   <type>(<package>): <lowercase imperative description>

{% if workhorse_var('epic') %}   Epic: {{ workhorse_var('epic') }}
{% endif %}{% if workhorse_var('story_slug') %}   Story: {{ workhorse_var('story_slug') }}
{% endif %}   ```

   `<type>` is `docs`: this commit writes specification, not product code, and must not
   release a version of anything. Subject ≤ 72 characters, no capital first word, no
   trailing period. Keep the trailers exactly as spelled — they are how the run record ties a
   commit back to its story.
3. **Do not push, open a pull request, or switch branches.** The workflow owns those.

## Output
Respond with JSON only after the epic and its stories are updated:
```json
{"status": "done|blocked", "notes": "<one-line summary of what was re-grounded>"}
```

- `done` — the epic, its stories and the queue now match what the operator stated, and every
  claim you wrote is grounded in something you read.
- `blocked` — **the answer does not let you re-ground the epic**, and rewriting it anyway would
  mean inventing the missing half. The answer contradicts what the repository actually contains,
  it settles a different question than the one that blocked the story, or the re-grounding needs
  a decision it does not make. The workflow re-reads this epic's stories immediately after this
  stage, so an epic rewritten around a guess is executed as though it were ground truth — hand
  it back instead. Name in `notes` the specific thing the answer left undecided.
