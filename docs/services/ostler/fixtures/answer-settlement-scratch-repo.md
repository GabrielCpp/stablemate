---
type: fixture
slug: answer-settlement-scratch-repo
title: answer settlement scratch repo
---
# answer settlement scratch repo

Seeds `answer-scratch/`, a small repo of its own under the checkout: one epic with a story `sx`,
and a markdown Answer list in its spec directory naming three findings. `F1` is fixed with a path
cited as evidence, `F2` is declined with a reason, and a fourth heading is malformed (no `:
fixed|declined`), so it never becomes an answer at all. `F3` is left unanswered.

## Steps

### write-answer-story

- kind: seed
- run: mkdir -p answer-scratch/docs/epics/0001-first/stories/sx && printf -- '---\ntype: epic\nid: TST-01M585PEGMRE3FWETV74QRSSY3\ntitle: First epic\nstatus: planned\n---\n# Epic: First epic\n\n## Seeds\n\n## Stories\n\n### sx\n- title: Story sx\n- id: TST-01M585PFWZZXH4Y6KNMH1VK58H\n- covers: (none)\n' > answer-scratch/docs/epics/0001-first/epic.md && printf -- '---\ntype: story\nid: TST-01M585PFWZZXH4Y6KNMH1VK58H\nslug: sx\nstatus: Not started\n---\n# Story: Story sx\n\n## Dependencies\n\n(none)\n\n## Fixtures\n\n(none)\n\n## Context\n\n(none)\n\n## Acceptance Criteria\n\n## Non-Functional Acceptance Criteria\n\n## Technical Notes\n\n## Implementation Status\n\n- **Status**: Not started\n' > answer-scratch/docs/epics/0001-first/stories/sx/story.md

### write-review-answers

- kind: seed
- run: mkdir -p answer-scratch/art/specs/TST-01M585PFWZZXH4Y6KNMH1VK58H && printf -- '## F1: fixed\n- path: src/thing.py\n\n## F2: declined\nReason: out of scope for this story\n\n## F4 fixed\n' > answer-scratch/art/specs/TST-01M585PFWZZXH4Y6KNMH1VK58H/review-answers.md
