The subject is the story graph of epic `{{ workhorse_var('epic') }}`, in the directory `{{ workhorse_var('subject') }}`. The deterministic validator already confirmed that every seed is claimed by some story and that the graph is valid. You judge what a script cannot.

Read:

- `{{ workhorse_var('subject') }}/epic.md`, including its `## Seeds` and `## Stories` sections.
- Each `story.md` under `{{ workhorse_var('subject') }}/stories/`. Its `## Dependencies` section is the dependency graph and its `services:` frontmatter lists the books it changes.
- The repo's planning method, which holds the split to its slicing and sequencing rules: {{ find_by_tags("planning") | default("(none installed: hold the split to vertical slices, where the first story is the thinnest end-to-end journey step and later stories widen it)", true) }}.

Story bodies are empty by design at this stage. The stage before you decides the set of stories and records each one's title and `covers` under `## Stories`. It scaffolds a `story.md` per story with its blockers, and it does not write story bodies. The per-story authoring stage does that after the split is settled. An empty `## Context`, `## Acceptance Criteria`, `## Non-Functional Acceptance Criteria` or `## Technical Notes` is the correct state. Do not fail an angle for a blank story body, an absent QA method or missing acceptance text. The split stage cannot fix them, so such a finding only sends the graph around a lap that changes nothing.

Judge coverage against `epic.md`: its seeds with their researched `surface`, `backing` and `prerequisites`, its `## Stories` coverage edges, and each story's `## Dependencies`.
