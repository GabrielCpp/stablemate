### `malformed-template` — the name template does not parse

The `name:` value contains `{` / `}` that do not pair up. Hole *classification* cannot fail — a
hole the dot-path grammar rejects is simply opaque and becomes a wildcard — so the only way a
template breaks is an unbalanced brace, usually a truncated paste or a hole never closed.

Read the rendered accessible name in the source and rewrite the template to match it, every `{`
closed by a `}`. If the accessible name genuinely contains a literal brace, double-check the
render before writing — that is the one case where the fix is not mechanical.
