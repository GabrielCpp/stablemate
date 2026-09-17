### `unarranged-request-body` — the route needs a request body the book never stated

The obligation's route is a body-bearing method (`POST`/`PUT`/`PATCH`, anything other than
`GET`/`DELETE`/`HEAD`/`OPTIONS`), and no bullet on the node says what the request sends. Rather
than send the call with a fabricated or empty body — which would draw a false failure from the
app for a reason the claim never made — the compiler withholds the call entirely and gaps it here.

Add the body's shape to the node's prose or a `body:` bullet, whichever this surface's other
nodes already use. Name the fields the request actually carries; if the node's claim is about
the response only and the body's exact shape genuinely does not matter to it, state the minimal
body the endpoint requires to accept the call at all — the compiler still needs something to
send.

**This is not `unresolved-precondition`.** That code is a scenario state the compiler could not
reach after it started arranging one. This one is narrower and mechanical: the route is body-
bearing and the book is silent about the body, full stop — nothing else about the scenario is in
question.
