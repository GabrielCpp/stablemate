# review-debt — group the register's records by shared cause

You are reviewing the whole debt register. Each line below is one record: its id, its
repository, its area, its status, the pattern of fix it calls for, and its one-line summary,
separated by tabs. Closed records are listed on purpose: a dropped record whose cause recurs
is a trend.

The register lives at `{{ shelf }}`. Each record is `<repo>/<area>/<id>/record.md` under it.
Open any `record.md` when its summary is not enough to tell its cause.

```
{{ listing }}
```

## Do this

1. Group the records by the cause they share, not by area alone. Two records in different
   areas or repositories belong together when the same code or the same pattern is wrong in
   both.
2. A cluster holds two or more ids. Every id that shares its cause with no other record is a
   singleton.
3. Every listed id appears exactly once across the clusters and the singletons. Do not leave
   one out, do not repeat one, and do not invent one.
4. Each cause names the code or the pattern it is about, so a reader can check it against the
   source.
5. Write the summary as a short paragraph for the maintainer: which causes recur most and
   which cluster to fix first.
{% if feedback %}

## Your last report did not pass

{{ feedback }}

Fix exactly this, and keep every other id where it was.
{% endif %}

## Output (JSON only)

```json
{
  "clusters": [{"name": "short name", "cause": "one line naming the code or pattern", "ids": ["id-1", "id-2"]}],
  "singletons": [{"id": "id-3", "cause": "one line naming the code or pattern"}],
  "summary": "a short paragraph for the maintainer"
}
```
