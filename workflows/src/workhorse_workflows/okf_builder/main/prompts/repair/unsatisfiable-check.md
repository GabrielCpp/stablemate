### `unsatisfiable-check` — no observation could ever satisfy this call

The check is not weak and it is not untested. It is impossible. Each check declares a
satisfiability rule over its own arguments beside the verifier that reads them, and
`ostler doctor` asks that rule before the sensitivity experiment runs. This finding is
that rule refusing the call: whatever the product does, the verifier compares the
declared argument against a value it can never equal, so the check can only ever fail.

Three shapes reach it today, and the finding names which one you have:

```markdown
# impossible — the verifier compares the URL's path, which stops at the first `?`
- verify: http_status(200, path="/health?deep=true")
# observable — the route, without the query string it was asked with
- verify: http_status(200, path="/health")

# impossible — every observation has a document root, so it is never absent
- verify: json_path("$", absent=true)
# observable — the field the claim actually forbids
- verify: json_path("$.debug", absent=true)

# impossible — the pattern matches the empty subject, so it matches every subject
- verify: omits(subject="$.message", matches=".*")
# observable — the thing that must not leak
- verify: omits(subject="$.message", matches="(?i)password|secret")
```

Read the source before rewriting the argument. The claim above the check is what the
observation has to turn on, so pick the value that claim would change: the route the
request reaches, the field below the root, the text that must not appear. Do not delete
the `verify:` bullet to clear the finding, and do not weaken it to something that admits
everything — that trades this error for `weak-check` or `insensitive-check`.
