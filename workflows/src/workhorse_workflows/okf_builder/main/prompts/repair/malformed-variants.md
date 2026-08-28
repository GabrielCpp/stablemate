### `malformed-variants` — the variants axis does not parse

The machine value of `variants:` is exactly one backticked span holding: a dot-path rooted at
the `one-per:` variable, `=`, then literal tokens separated by `|` —

```markdown
- variants: `field.type = text | number | select | date` — from the FieldType union
```

Prose belongs after ` — `, never inside the backticks. Take the token list from the source's own
enumeration — a union type, an enum, the arms of a switch — and repair the spelling to that
shape. Do not compress an open-ended value into a fake enumeration: a `variants:` axis is for a
closed set the code visibly switches on; anything else is prose, or no bullet at all.
