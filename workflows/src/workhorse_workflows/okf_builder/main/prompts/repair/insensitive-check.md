### `insensitive-check` — every check on this claim stayed green through every perturbation tried

`weak-check` catches the two shapes doctor can see statically in the call itself — a bare
2xx `http_status`, a presence-only `json_path`. This is the same defect widened past those
two shapes: `sensitivity.report` actually perturbed the product the way a real bug would
and re-verified, and every check declared for the claim still passed. The check runs; it
just cannot go red.

The finding names which calls survived which perturbations. Repair the same way
`weak-check` is repaired — read the source and assert a value the defect would actually
change, not an argument that merely looks stricter:

```markdown
# insensitive — passed even with the route perturbed to answer someone else's request
- verify: http_status(200)
# discriminating — this route, this answer
- verify: http_status(200, path="/invoices/{id}", title="Invoice")
```

If the check really is the strongest observation available for this claim, leave it
standing and say so in `doc_status`, naming the claim and the reason — the same escape
`weak-check` has, for the same reason: dressing the check up with an argument the code
does not support is worse than the finding.
