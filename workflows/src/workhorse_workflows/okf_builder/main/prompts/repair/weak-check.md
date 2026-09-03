### `weak-check` — every check on this node passes on the defect it names

The node declares checks, so `undeclared-obligation` is quiet, but each of them is green on the
nearest plausible bug:

- `json_path(path=…, absent=false)` — presence with no value. It passes on the empty string, on
  `null`, and on whatever default the defect also produces.
- `http_status(2xx)` with neither `path:` nor `title:` — says a request succeeded, and nothing about
  which request or what it answered.

Repair by naming what the claim actually turns on:

```markdown
# weak — true the day the field is hard-coded empty
- verify: json_path(path="$.invoice.total", absent=false)
# discriminating — the value is the claim
- verify: json_path(path="$.invoice.total", equals="the sum of the line items")

# weak — some request returned 200
- verify: http_status(200)
# discriminating — this route, this answer
- verify: http_status(200, path="/invoices/{id}", title="Invoice")
```

Read the source to pick the value. The rule is not "add an argument": `json_path(path="$.state",
equals="published")` is discriminating for a state machine and a rubber stamp on a field the code
hard-codes to `"published"`. Doctor cannot see that difference — you can, which is why this is a
warn and why the value has to come from what the code does rather than from the bullet's wording.

If the check really is the strongest observation available for this claim (a genuinely
presence-only contract), leave it standing and say so in `doc_status`, naming the node and the
reason. Standing is the outcome — adjudication reads your note with the source in hand — and
dressing the check up with an argument the code does not support is worse than the finding.
