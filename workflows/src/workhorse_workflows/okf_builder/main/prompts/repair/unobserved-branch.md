### `unobserved-branch` — an alternative outcome nothing looks at

The parent list is declared `branches`: its children are alternative outcomes, and exactly
one of them happens on a run. This child has no check of its own, and the `verify:` sitting
under the list was written for a sibling outcome — on the run where *this* branch is taken,
that check does not observe it, it **refutes** it.

So the finding is not "a check is missing here". It is that a check exists which, credited
to this branch, turns a correct product into a red run and an incorrect one into a green.

To repair each one, split the list into sibling bullets, each with the observation that is
true of it:

```markdown
- does: a valid name is accepted and the policy is created
- verify: http_status(code=201, path="/api/policies")
- does: a duplicate name is refused with a message
- verify: http_status(code=409, path="/api/policies")
- verify: visible(selector="#name-error")
```

Each outcome now carries what would be observed *when that outcome happens*, and each is its
own obligation with its own evidence.

If the product genuinely has an alternative outcome nothing can observe from this surface —
a branch that leaves no trace a driver can reach — leave it declared and write no check.
It becomes a named gap in the compiled plan, which is the honest report. What it must not
become is a branch quietly covered by its sibling's check.
