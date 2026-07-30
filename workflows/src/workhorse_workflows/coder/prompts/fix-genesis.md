# Repair the new repository so it satisfies the main loop's preconditions

`validate-genesis.py` checked the repository at `{{ workhorse_var('target_dir') }}` against
the preconditions the coder and author workflows assume, and it failed.

Each error below names a precondition that some later stage depends on **silently** — the
stage does not crash without it, it stops asserting anything and reports success. That is why
these are checked here rather than discovered later.

## Errors to fix

```
{{ workhorse_var('genesis_errors') }}
```

{% if workhorse_var('genesis_warnings') %}
## Warnings (fix if you can; they do not block)

```
{{ workhorse_var('genesis_warnings') }}
```
{% endif %}

## How to approach these

- **ostler binds to the wrong root** — the most serious one. It means ostler resolved to an
  *ancestor* directory, so ids would be allocated from that repo's registry and docs written
  into its tree, with no error anywhere. Almost always this is a missing or failed `git init`
  in the target. Fix the target repo; never "fix" it by changing where ostler looks.
- **Missing service marker** — the native init tool did not produce it, or produced it in a
  subdirectory. Re-run the stack's real init command in the right directory. Do not hand-write
  a stub `go.mod` / `package.json` / `pubspec.yaml` to satisfy the check: the marker is
  evidence that a working skeleton exists, and forging it makes the check lie.
- **Empty `instructions` map in `.agents/agents-context.json`** — `farrier install` did not run
  or installed no packs. Check `agents.yml`'s `packs:` list, then re-run
  `farrier install --repo {{ workhorse_var('target_dir') }}`.
- **Missing `docs/epics/` or `docs/backlog.md`** — the docs scaffold did not render. Re-run it
  rather than hand-creating the tree, so the repo matches the scaffold every other repo uses.

Fix the underlying cause in the repository. Do not modify `validate-genesis.py`, and do not
adjust `agents.yml` so the assertion passes against a repo that has not actually changed — the
validator exists to catch exactly that.

## Output

Return this exact JSON in your **final response**:

```json
{
  "fix_result": {
    "status": "fixed" | "blocked",
    "notes": "Per error: the underlying cause and what you changed. If blocked: which error you could not resolve and what is needed."
  }
}
```
