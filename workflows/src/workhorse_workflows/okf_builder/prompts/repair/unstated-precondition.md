### `unstated-precondition` — a lifecycle claim observed only afterwards

A bullet on this node says something is created, added, registered, issued, deleted, removed or
revoked, and every check it declares reads the state **after** the action. That cannot tell a
creation from a no-op: a present id and a `201` look identical when the subject was already there,
and an absence afterwards looks identical when the subject never existed.

The vocabulary has the paired form for exactly this. `created(subject=…)` and `removed(subject=…)`
make the harness assert the negative before the action and the positive after, so the change is
attributable to the action rather than to history:

```markdown
# unstated — green on a no-op
- does: issues an API key for the caller
- verify: http_status(201, path="/keys")
- verify: json_path(path="$.key.id", absent=false)

# stated — the before-state is part of the observation
- does: issues an API key for the caller
- verify: created(subject="an API key owned by the caller")
- verify: json_path(path="$.key.scopes", equals="the caller's granted scopes")
```

Keep the after-reads that assert a *value* — they answer a different question (what the created
thing looks like) and are worth having. What replaces the presence check is the pair, not the whole
set.

Name the subject concretely enough that the harness can resolve the same thing twice: "the caller's
API key", not "the record". Read the source for what identifies it.

The rule generalises past existence: any claim of the form *X changed* needs the read before it —
that is what `unchanged`, `keys_unchanged`, `persists` and `conflict_on_stale` are for, and none of
them can be spelled as a single after-read.

If the bullet's verb is lifecycle-shaped but the claim is not (an idempotent upsert that legitimately
tolerates the subject already existing), that is the heuristic misfiring. Leave the checks as they
are and say so in `doc_status`, naming the node — a human decides whether it becomes a waiver.
