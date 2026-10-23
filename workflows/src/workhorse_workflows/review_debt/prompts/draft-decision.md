# review-debt — draft a decision from one cluster

You are drafting one architecture decision. The records below share one cause. Each line is
one record: its id, its repository, its area, its status, the pattern of fix it calls for, and
its one-line summary, separated by tabs.

The cluster is named `{{ name }}`. Its shared cause: {{ cause }}

The register lives at `{{ shelf }}`. Each record is `<repo>/<area>/<id>/record.md` under it.
Open any `record.md` when its summary is not enough to tell what is wrong.

```
{{ listing }}
```

## Do this

1. Read the records and the code they name until you can state the shared cause in your own
   words.
2. Write the decision that removes the cause for good, not a fix for each record.
3. Name the code or the pattern, so a reader can check the decision against the source.
4. Say what changes for the callers and what the decision costs.

## Output (JSON only)

```json
{
  "title": "one line naming the decision",
  "context": "what the records show and why the cause recurs",
  "decision": "what to do about the cause",
  "consequences": "what changes after the decision, and what it costs"
}
```
