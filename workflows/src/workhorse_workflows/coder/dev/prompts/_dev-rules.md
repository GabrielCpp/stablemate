{% if not opening_brief %}
{% include "dev/prompts/_dev-standards.md" %}

{% include "dev/prompts/_dev-scope.md" %}

## Story Status

Leave the story's `status:` frontmatter and its `## Implementation Status` **Status** line
exactly as you found them. Record what you ran as prose under that heading instead. A gate
re-reads that line after the review phase and sends the story back to you if it changed.

## Commit Identity

Every commit carries `Epic: {{ workhorse_var('epic') }}` and
`Story: {{ workhorse_var('story_id') }}` as footers, spelled exactly so, and nowhere else in
the message. Do not push and do not open a pull request. The workflow owns both.

Name every path a commit takes on the command itself: `git commit --only -m <message> --
<paths>`, after a `git add -- <path>` for each new file. Never a bare `git commit`, never
`git commit -a` and never `git add -A` or `git add .`. The checkout's index can hold changes
somebody else staged, and a commit with no paths takes them under this story's name.

{% include "shared/prompts/_step-cost.md" %}
{% endif %}
