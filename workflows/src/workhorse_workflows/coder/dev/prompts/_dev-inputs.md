{{ workhorse_var('resume_note') }}

Your session is resumable, and it may be compacted mid-story. The resume note above is the
run's state, read from disk at the start of this turn. After a compaction, trust it over
your memory of earlier turns. The worklist file it names holds the same state, and you may
read it again at any point in the turn.

## Inputs (authoritative, do not rediscover)

- Story: `{{ workhorse_var('story_slug') }}` (id `{{ workhorse_var('story_id') }}`, epic `{{ workhorse_var('epic') }}`)
- Story path: `{{ workhorse_var('story_path') }}`
{% if story_services and not opening_brief %}
- Services this story changes (book names under `docs/services/`): {% for name in story_services %}`{{ name }}`{% if not loop.last %}, {% endif %}{% endfor %}
{% endif %}
- Spec dir: `{{ workhorse_var('spec_dir') }}`
{% if branch and not opening_brief %}
- Run branch: `{{ workhorse_var('branch') }}`
{% endif %}
- Worklist: `{{ workhorse_var('worklist_path') }}`
- This brief, kept on disk for later turns: `{{ workhorse_var('brief_path') }}`
{% if opening_brief %}
- The brief that opened this conversation: `{{ workhorse_var('opening_brief') }}`

That opening brief set the rules that hold for the whole story: its inputs, the follow-up it
works if any, its standards and branch, its scope, when to block, its status line and its
commit footers. Each still holds for this turn, and this brief does not repeat them. When you
no longer hold either brief, read it again from its path before you act.
{% else %}

Work **only** the story at that path. Do not search git history or branch state for a
different story to work.

This story runs in three phases on this one conversation: plan, build, then review. Each
phase opens with its own brief. A later turn of the same phase sends only what changed and
points back at the brief's path above. When you no longer hold this brief, read it again
from that path before you act.
{% endif %}
{% if follow_up_title and not opening_brief %}

## This turn works a follow-up

An earlier turn of this story filed this follow-up, and the run now hands it back to you:

- **Title:** {{ workhorse_var('follow_up_title') }}
- **Reason:** {{ workhorse_var('follow_up_reason') }}

The follow-up is the scope of this work, not the whole story. Its plan goes into `plan.md`
under its own heading, and the story's plan stays as it stands. A follow-up files no
follow-ups of its own, so return `follow_ups` empty wherever the result has them. A failure
you meet while working it is yours to fix, by the rule under Scope and follow-ups. An
improvement you notice beyond it goes in `notes`.
{% endif %}
{% if note %}

## The task for this turn

The workflow sent this instruction for this turn. It takes priority over the default flow
below. It is most often a rescope note from QA.

{{ workhorse_var('note') }}
{% endif %}
{% if operator_context %}

## Operator answer (authoritative ground truth)

An operator answered a block on this story. Treat the answer as fact. It overrides any
earlier assumption in the story, the plan, the code or a finding. Do not re-derive it, and
do not raise the same block again.

{{ workhorse_var('operator_context') }}

Fold the answer into the plan section it moves, not into a new "Open Questions" section.
{% endif %}
