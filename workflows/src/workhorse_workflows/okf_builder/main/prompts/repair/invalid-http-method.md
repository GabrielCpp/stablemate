### `invalid-http-method` — `method:` does not spell a recognized HTTP verb

An `endpoint`'s `method:` bullet, or a journey step's `method:`, does not parse as one of
`GET`/`POST`/`PUT`/`PATCH`/`DELETE`/`HEAD`/`OPTIONS` (case-insensitive). `method:` names the
role the value plays — the verb this route answers to — and declaring a role does not declare
what the value may say: a typo, a placeholder, or a made-up verb parses as nothing rather than
as some verb the harness can send. A value that did not parse is undetermined, and undetermined
must not walk on to build a call, so the compiler withholds it entirely and gaps it here, naming
the value that failed.

Fix the `method:` bullet to spell one of the recognized verbs:

```markdown
- method: POST
- path: /widgets
```

**This is not `unarranged-request-body`.** That code fires once a route's method is already
known to need a body and no `arrange:` bullet supplies one — the method itself parsed fine.
This one fires earlier, when the method never parsed at all, so there is no verb yet to ask
"does this need a body." Fixing the spelling here is what lets `unarranged-request-body`
become the applicable question, not the other way around.

**This is not `uncompilable-claim`.** That code is for a node the book gives no `route:` to
act on at all — no `method:`/`path:` pair present. This one is for a `method:` that is
present and spells something, just not a recognized verb.
