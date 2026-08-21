# link-shortener — decision sheet

The product decisions the backlog deliberately does not make. The backlog is written at
the level of observable behaviour ("a person arrives at the destination"), which is the
right level for a *benchmark input* — it leaves the design work to the author lane. But
the author lane's grill gate is human by construction: it parks and waits for an operator
to settle exactly these questions before epics are split. An unattended round therefore
never gets past it, and an attended one is answered by whoever is watching, differently
each time — so two rounds of the same task are not measuring the same product.

This sheet is that operator, frozen. `_greenfield.py` injects it at the gate, records the
injection in the round's ledger, and reports the sha it applied.

It is written as a **contract**, not as replies to the questions a particular round's
grill happened to ask. Question wording drifts between rounds; what the author lane folds
into the backlog is settled decisions, so decisions are what this file holds. A round
whose grill asks something this sheet does not settle stays **parked** and is reported
parked — that is a finding about this file (extend it, and note the capture), never a
guess made at gate time.

These decisions were first given by hand, at the gate, on the `conda` round. They are
reproduced here verbatim so that round and every later one describe the same product.

**Link lifetime** and **Repeated destinations** were added later, and the capture that
demanded them is worth recording. Two rounds of this task ran against the sheet without
them and behaved *differently* at the same gate: one parked and waited, the other noted
"identifier lifecycle unspecified" and carried on. The park was the system working; the
carrying-on was a give-up in politer clothes. A gap in this file does not merely cost a
round, it makes two rounds incomparable — which is the one thing a benchmark input may not
do. The sha of this file is the fixture's identity: two rounds are comparable only at equal
sha, and any number quoted against a different one must say so.

**Link lifetime** was then rescoped, and that capture belongs here too. Its first version
demanded that a created link survive a restart of the service. The round that ran against it
parked in the *coder* lane, not the author lane: the QA runner has no way to cross a process
boundary inside a scenario, so the lane could neither prove the criterion nor discharge it
without substituting a passing test suite for runtime evidence — which it correctly refused to
do. A sheet may only ask for what the harness can observe about the running product. Asking for
more does not make the fixture stricter; it makes it stall, and a stalled round measures nothing.
The tooling gap itself is recorded as a flex finding rather than treated as this fixture's problem
to solve.

## Surface scope

The api is the only surface. A round that implements the three bullets on the api has
implemented them completely — there is no web page and no mobile app to be missing, and a
judge should not read one into "a person submits a long URL". The backlog says the same
thing; it is repeated here because this sheet is what stands in for the operator, and this
is the answer that operator would give.

## Creation contract

`POST /links` with a JSON body `{"url": "<the long URL>"}`.

On success, `201 Created` with a JSON body carrying both the short link's key and the
absolute URL a person can share:

```json
{"key": "<key>", "short_url": "http://localhost:18081/<key>"}
```

Following a short link is `GET /<key>`, answered with `302 Found` and a `Location` header
holding the original URL — a redirect, because [link-follow] says the person *arrives at*
the destination rather than reads it.

## Accepted destinations

A destination is valid when it is an absolute URL with an `http` or `https` scheme and a
non-empty host.

Everything else — a relative path, a missing or empty `url` field, a `javascript:` or
`file:` scheme, a malformed URL — is refused with `400 Bad Request` and a JSON body
`{"title": "..."}` naming the reason.

The scheme restriction is part of the decision rather than an implementation detail: a
public redirector that will emit any scheme is a redirect gadget, and [link-create] says
the short link is meant to be shared.

## Link lifetime

A created short link works indefinitely. There is no expiry, so there is no expired-key
response to define: a key either was created and redirects, or was never created and is the
[link-missing] 404.

**The implementation is durable.** The ledger is a JSON file on disk — the shape the other
frozen fixtures already use — not state held in the memory of the process that wrote it.

**The acceptance criterion is that a created link is persisted to that on-disk ledger**, and
the evidence is the file: after a successful `POST /links`, the ledger contains the new key
and its destination. This is the `persists` pattern, and it is provable against the running
product today.

**Restart survival is a consequence of durability, not an acceptance criterion here.** It is
not provable under the current QA runner, and that is a property of the tooling rather than a
softening of the promise: `ostler/ostler/qa/run.py:364` fixes the lifecycle at
`start → scenarios → stop`, `background(...)` is contractually a daemon started before the
first scenario and stopped after the last (`qa-plan-authoring.md:71-80`), and the plan-lint
allowlist bars the process and OS modules that would fake a seam. There is no way for a
scenario to cross a process boundary, so an acceptance criterion demanding one can only be
discharged by substituting a test suite or a manual note for runtime evidence — which the QA
rules correctly forbid. The startup-reload path is therefore **code review's** obligation, not
QA's: a reviewer reads that the repository loads its ledger from the file at construction.

*Why it is written this way:* [link-follow] promises a person *arrives at* the destination, and
a promise that lapses when a process ends is a smaller promise than the bullet makes — so
durability stays. What changed is what QA is asked to prove about it. An acceptance criterion
the harness cannot express is not a stricter fixture; it is a fixture that stalls, and the
first version of this section stalled a round exactly that way. Checking the file keeps most of
the `persists` vocabulary this section was written to exercise, and the gap it exposed is
recorded as a flex finding rather than papered over.

## Repeated destinations

Every successful `POST /links` allocates a **distinct new key**, including for a
destination that was submitted before. Both keys redirect to that destination. The status
is always `201 Created`.

*Why:* `201 Created` asserts a resource was created, and returning a pre-existing key
would make that assertion false or force a second success status. Reuse would also drag in
a canonicalisation rule (are `http://x.com/a` and `http://x.com/a/` the same destination?)
and a concurrency rule, neither of which a three-bullet fixture should carry — and the
epic's Non-Goals already exclude a duplicate-submission policy.

## Missing link

`GET /<key>` for a key that was never created answers `404 Not Found` with a JSON body
`{"title": "Not Found"}`.

Not a redirect and not a 500 — [link-missing] names both of those as the outcomes it
exists to rule out.
