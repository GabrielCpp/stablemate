### `misbound-status-check` — a status check landed on the wrong claim

A `verify:` calling `http_status(...)`/`exit_status(...)` binds to the **nearest normative
bullet above it**, by document order — not to whichever claim it happens to be about. When a
node is written with every claim first and every `verify:` last, the last claim above the block
— usually `auth:` on an endpoint, `errors:` on a command — is what every one of those checks
binds to, whatever code each actually names:

```markdown
- status: 200
- errors:
- auth: none
- verify: http_status(200, path="/healthz")
```

Here `verify:` binds to `auth:1`, not `status:1` — the claim that actually says 200. This code
fires only when that misbinding is provable: the check names a code absent from the claim it
bound to, and that same code is present, verbatim, on this node's own `status:` (`endpoint`/
`invocation`) or `exits:` (`command`) bullet — the one bullet that could only have meant to
ground it.

The repair is one move:

1. **Move the `verify:` bullet** to sit immediately after the `status:`/`exits:` bullet naming
   its code, so document order binds it to the claim it actually observes:

   ```markdown
   - status: 200
   - verify: http_status(200, path="/healthz")
   - errors:
   - auth: none
   ```

**Never edit the check's arguments to match the claim it landed on.** The check is right and
the claim is right; only their order is wrong. Rewriting `http_status(200, ...)` to whatever
code `auth:` happens to be about would make the check agree with a binding that was never the
point, and leave `status:` with nothing observing it at all. **Deleting the check is not the
repair either** — a node with the misbinding removed and no check in its place has been made
green by losing the observation, not by fixing where it sits.

**This is narrower than `uneven-claim-coverage`.** That code flags the imbalance a misbinding
like this one leaves behind — a claim with too many checks next to a sibling with none — however
it happened. This one fires only on the specific, provable shape: a status-shaped check whose
own code names the claim it should have bound to. A finding here usually clears an
`uneven-claim-coverage` finding on the same node as a side effect of the move; the reverse is
not true; fix each on the coverage it names.
