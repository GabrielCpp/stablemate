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

{% include "shared/prompts/_step-cost.md" %}
{% endif %}
