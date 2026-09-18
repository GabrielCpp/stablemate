### `unarranged-request-body` — the route needs a request body the arm never arranged

The obligation's route is a body-bearing method (`POST`/`PUT`/`PATCH`, anything other than
`GET`/`DELETE`/`HEAD`/`OPTIONS`), and the arm (or, for a journey step, the node) arranges no
body the HTTP driver can send — no `arrange:` bullet at all, an `arrange:` bullet that failed to
parse, an act declared that no HTTP driver can perform, or two acts stating different values for
the same field. Rather than send the call with a fabricated, empty, partial, or contradictory
body — which would draw a false failure from the app for a reason the claim never made — the
compiler withholds the call entirely and gaps it here.

Add one `arrange: body(field="…", value=…)` bullet per field the request actually carries,
under the `status:` arm the body belongs to (a journey step reads its node's arms merged
instead, so put it on the step's own node). `field=` is the request member's name; `value=` is
a JSON scalar (`str`/`int`/`float`/`bool`) sent literally, not typed as a string the way a
person's `fill:` is:

```markdown
- status: 201
- arrange: body(field="name", value="Widget A")
- arrange: body(field="quantity", value=3)
```

If the node's claim is about the response only and the body's exact shape genuinely does not
matter to it, state the minimal body the endpoint requires to accept the call at all — the
compiler still needs something to send.

**This is not `unresolved-precondition`.** That code is a scenario state the compiler could not
reach after it started arranging one. This one is narrower and mechanical: the route is body-
bearing and the arm arranges no body the driver can send, full stop — nothing else about the
scenario is in question.
