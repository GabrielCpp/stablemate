- Every promise and refusal in the contracts is stated on some page, as a claim the product
  can be asked to demonstrate. None is missing, and the pages claim nothing the contracts do
  not.
- Each node is written to the spec depth its node type asks for. A one-line stub fails.
- Each bullet states one claim, and its `verify:` goes red on a product that breaks any part
  of that claim. A check that also passes on a violation fails. A pattern that matches a
  fragment of a message is such a check when the claim says the message names a path or a
  value. The `run:` above it names that path or value, so the pattern quotes it.
- A step's `verify:` is the exception. It is a link to the output that shows the step ran, not
  a check, and it states no claim about the product. A claim that output shows goes on the node
  that makes it, under that node's own `verify:`.
- A page's claims run as one scenario. Every fixture the page names is put in place first,
  then each claim's call runs in page order, so each check reads the state the calls above it
  left. A claim whose check reads a file or a state has a `fixture:` or a claim above it that
  puts that file or state in place, and no check depends on another page having run. A claim
  that needs a state a claim above it changed either runs above that claim, or its call names
  a path of its own, such as a file no claim above it wrote. A page is never split to get a
  fresh state.
- The pages agree with each other. A fixture, a file, an exit code or a message is described
  the same way on every page that names it.
- Every interactive control has a role, an accessible name and a keyboard contract. Every
  structural component has a placement.
- A reader holding only the book understands what the product does here and why, and can
  drive it without the source.
