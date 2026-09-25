The format. Each node type below is written where it says, with its bullets in the order
listed. A `code:` or `tests:` citation is `` `path::symbol` ``, with a symbol the file
declares:

{{ rules }}

The checks a `verify:` may call, each with its arguments and the defect it excludes. Call
one with the arguments its signature names, as `name(arg=value)`, and nothing else:

{{ checks }}

Every claim you write compiles into a check run against the product, and a page with a claim
that does not compile is refused. The check reads the page by document order, so the shape is
strict:

- A claim is a bullet at the node's top level whose key the format lists as a claim. A `run:`
  and a `verify:` at that same top level bind to the nearest claim above them.
- A `run:` or a `verify:` nested under a claim's child is never read, and that claim counts
  as unchecked.
- A claim with more than one nested child states how its children combine, as its own value.
  `all` says they are parts of one effect, and the `run:` and `verify:` below the list check
  every child.
- Alternative outcomes are not children of one claim. Write each as a sibling bullet of the
  same key, followed by its own `run:` and `verify:`:

  ```markdown
  - exits: `0` when the input is valid
  - run: invoke(argv=["<binary>", "<command>", "<valid input>"])
  - verify: exit_status(code=0)
  - exits: `2` when the input is missing
  - run: invoke(argv=["<binary>", "<command>"])
  - verify: exit_status(code=2)
  ```

- A `run:` holds one call and nothing else. The condition it sets up goes in the claim above it.
- Each direct child of `flags:` or `provides:` is one value, and its own children are that
  value's properties. None of them is a claim, and none takes a `verify:`.
- A `fixture:` names a fixture page that is in the book or that you write.
- Each child of a flow's `steps:` links the one node that step performs, a node whose own
  bullets state exactly one distinct `run:`, usually an invocation. A step whose node states
  no `run:`, or several different ones, does not compile.
