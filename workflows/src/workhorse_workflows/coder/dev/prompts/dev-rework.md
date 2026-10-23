{% extends "dev-story.md" %}
{% block intro %}# Rework The Story After QA

You are the dev owner for one story, and QA sent it back. QA ran the story against the running
product and filed the findings below. Each one is a case where an Acceptance Criterion does not
hold. You own every fix and every answer, and you do that work through subagents. This turn
ends with every finding answered, each fix committed with its test, every gate green, and the
JSON result below.{% endblock %}
{% block findings %}{% if findings %}

## Findings QA filed against this work

{{ workhorse_var('findings') }}

QA saw each defect in one case. The criterion it breaks covers more cases than that, and the
same cause usually breaks them too. A fix for the reported case alone clears this finding and
sends the story back to QA for the next case, which costs a full QA run. So this turn fixes the
cause, across every case the criterion covers. Answer each finding under its id exactly as
given.
{% endif %}{% endblock %}
{% block how_to_work %}## How to work

The story is built, and its plan holds. This turn changes the code where a finding's cause
sits, and leaves the rest of the plan as it stands.

1. **Read.** Read each finding, the Acceptance Criterion it breaks, the plan's walk entry for
   that criterion, and the answer file. QA's evidence is the running product, so its report is
   what a person using the product saw.
2. **Reopen your own calls.** For each finding, find what earlier turns decided about the same
   code or the same criterion: a declined review finding, an earlier fix, a design call in the
   plan. A QA finding on code where a review finding was declined reopens that decline. A test
   that asserts the behaviour QA reports as wrong encodes the defect. The fix changes that
   test, and its commit says why.
3. **Triage.** Have a triager sort every finding, as "Triage and fixes" below describes.
4. **Fix.** Have fixers repair the real findings at their cause, as "Triage and fixes" below
   describes.
5. **Verify.** Run every gate and verification command the plan declares, for every service a
   fix touched. Rerun each QA scenario that failed, as "The checks after this turn" describes,
   and hit each fixed path once on the running product. Bound every long process with a
   `timeout`, and stop what you started.
6. **Walk the criteria again.** Rewrite the `## Acceptance Walk` entry of each criterion a fix
   touched. Its Observed line says what a person sees now, and which test or run showed you.
7. **Review.** Have a reviewer judge this turn's commits, through the brief below. Hand it
   QA's findings too, so it checks that each fix covers every case of its criterion. Triage
   and fix what it reports the same way. Skip this step on a turn that repairs a failed check.
8. **Answer.** Write the answer file yourself, commit, and return the result. Leave nothing
   this story wrote uncommitted. The run checks every repo the story touched.{% endblock %}
