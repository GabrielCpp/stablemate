- Every promise and refusal in the contracts is stated on some page, as a claim the product
  can be asked to demonstrate. None is missing, and the pages claim nothing the contracts do
  not.
- Each node is written to the spec depth its node type asks for. A one-line stub fails.
- Each bullet states one claim, and its `verify:` goes red on a product that breaks any part
  of that claim. A check that also passes on a violation fails. A pattern that matches a
  fragment of a message is such a check when the claim says the message names a path or a
  value.
- A claim whose check reads a file or a state has a `fixture:` above it that puts that file
  or state in place. The check never depends on another scenario having run first.
- The pages agree with each other. A fixture, a file, an exit code or a message is described
  the same way on every page that names it.
- Every interactive control has a role, an accessible name and a keyboard contract. Every
  structural component has a placement.
- A reader holding only the book understands what the product does here and why, and can
  drive it without the source.
