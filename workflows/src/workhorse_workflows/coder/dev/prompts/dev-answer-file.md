---
agent: agent
---

# The Answer File

The answer file holds one section for every finding filed against the story: each one a
review reported, and each one QA or an earlier turn filed. It holds no other `##` heading,
because a parser reads every level-2 heading as an answer. Keep the sections earlier turns
wrote, and leave every accepted section as it stands.

## A fixed finding

The section names its evidence:

```markdown
## acme-story/review-1.2: fixed
- commit: 3f9c2a1
- path: api-service/src/links/validate.py
- test: test_rejects_relative_destination
```

One fix for several findings is answered under each of their ids.

## A declined finding

The section gives its reason:

```markdown
## acme-story/review-1.3: declined
Reason: the story's AC 4 asks for the redirect to keep the query string, so the change is intended.
```

A "not a defect" decline opens its reason with those words, and names the test that drives
the finding's own case and passes, above the reason:

```markdown
## acme-story/review-1.4: declined
- test: test_keeps_trailing_slash_on_redirect

Reason: not a defect. The redirect keeps the trailing slash, and the test drives the reported URL.
```

## What the workflow checks

The workflow checks every fixed answer: the commit exists in one of the story's repos, the
path is among the files the story changed, and the test name appears in a file the story
changed. It checks every "not a defect" decline too: it names a test, and the test name
appears in a tracked file of the story's code repos. A finding with no section, or an answer
that fails a check, comes back to the review phase in the next turn.

A decline that passes is final, so its reason must hold for a reviewer. Three reasons hold:
the issue is not a defect, the story asks for the behaviour, or the change is an improvement
the working slice does not need. A failure is never declined. "Too much work" is not a
reason.
