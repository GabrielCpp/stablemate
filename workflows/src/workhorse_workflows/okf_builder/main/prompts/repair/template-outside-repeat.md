### `template-outside-repeat` — a templated name on a node that repeats over nothing

The `name:` carries balanced `{…}` holes, but the node declares no `one-per:` and inherits no
repeat scope from an ancestor — there is no iteration variable a hole could bind to. Every hole
is therefore opaque: consumers match the name as a wildcard, and the precision the author wrote
those braces to express is silently gone.

Repair from the rendering code, not from the bullet:

- If the source **does** render this control once per member of a collection, the node is a
  repeat missing its declaration: add `` one-per: `<var>` `` (with prose saying where the
  collection comes from), `` unique-by: `<var>.<key>` `` for the distinct key, and keep the
  template — its holes now bind.
- If the source renders the control **once**, the braces are decoration: read what the name
  actually renders as and write that literal text.
- **Never delete the holes just to clear the finding** — a wildcard name flattened into wrong
  literal text pins nothing and lies about it.
