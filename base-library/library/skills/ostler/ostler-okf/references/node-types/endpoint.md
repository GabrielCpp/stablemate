# `endpoint`

One route or channel of a [`server`](server.md): the request it answers and what answering it
does.

## Identity

File type. One page per endpoint, in the folder of its [`server`](server.md) page, named after
the endpoint. Its id is the page's path. The page's `server:` bullet links the server, and the
server's `## Endpoints` section links the page back. The invocations that call the endpoint
sit on its page under `## Invocations`.

A `### <id>` under a server's `## Endpoints` heading still reads as an endpoint. That is the
form older books wrote, and doctor reports each one as `inline-endpoint`. `ostler edit
carve-endpoints <server page>` moves each one to its own page and rewrites every link the move
touches. The okf-book run does this itself before the next lap.

## Bullet keys

| key | required | what it does |
| --- | --- | --- |
| `server` | yes, on a page | link — the one `server` page this endpoint is served from |
| `method` | no | the HTTP method |
| `path` | no | the route path |
| `channel` | no | locator — the channel, for non-HTTP transports |
| `message` | no | nested, entries; **mints an obligation** per frame |
| `does` | no | nested; **mints an obligation** per value |
| `emits` | no | **mints an obligation** (via the shared set) |
| `consumes` | no | **mints an obligation** (via the shared set) |
| `response` | no | a record — what comes back, as named properties |
| `status` | no | **mints an obligation** — the route's outcomes, one claim per value |
| `errors` | no | **mints an obligation** — the refusal arm |
| `error` | no | alias of `errors` |
| `auth` | no | **mints an obligation** — who may call it |
| `authorization` | no | alias of `auth` |
| `code` | no | link, **owns** its file |
| `openapi` | no | link, **owns** its file |
| `detail` | no | link — an explanatory [`concept`](concept.md) |
| `verify` | no | a check |
| `fixture` | no | a fixture |
| `arrange` | no | an act — a request body member the step's own performer sends |
| `capture` | no | a capture |
| `tests` | no | link — the test files covering it |

`emits:`/`consumes:` carry no `normative` flag of their own here — they are normative because
the [shared set](../bullet-grammar.md#keys-that-are-normative-on-every-type) makes them so on
every type. The effect is the same: one obligation per value.

The three alias pairs are accepted spellings kept for the books that wrote them. `ostler
scaffold` stubs only the primary; prefer the primary in new writing.

The outcome keys are declared in this order so `fmt` can place them between the effect and its
grounding — `does → status → errors → auth → code → verify` — and so a `verify:` written under
one binds to that one. See [document order is the
binding](../bullet-grammar.md#document-order-is-the-binding). Writing every claim first and
every `verify:` last still parses — `fmt` does not reorder prose — but it hands each check to
whichever claim happens to sit last above it rather than the one it actually observes; when
the check is `http_status(...)` and the code it names belongs to `status:` instead, `doctor`
catches it as `misbound-status-check`.

## Relationships

`detail:` points at a `concept`. `openapi:` grounds the route in a spec file it also owns.

## `method`

Names the HTTP verb this route answers to — declaring that role does not declare what the
value may spell. `method:` must parse as one of `GET`/`POST`/`PUT`/`PATCH`/`DELETE`/`HEAD`/
`OPTIONS` (case-insensitive); anything else is undetermined, and undetermined must not emit a
call, so `compile_plan` withholds it — `invalid-http-method` (see
[../doctor-codes.md](../doctor-codes.md)), naming the value that failed to parse.

That is the consequence at *compile* time, and it is only ever reached by an endpoint some
scenario actually calls. `method:` also declares the `http-method` value kind, so the book is
checked on its own: `- method: fetch-data` is `unparsable-bullet-value` the moment `doctor`
reads the page, whether or not a plan is ever compiled from it. Two observers, one rule —
the doctor code is a statement about the book, the compiler code a statement about a call it
refused to emit.

## `path`

The route this endpoint answers on. It declares the same `route` value kind `screen.route`
does, and is held to the same bar: it must spell a path. A parameterised path (`/links/{id}`)
is ordinary and legal here — an endpoint is a route *family* by nature, and nothing downstream
asks an endpoint to identify one page.

The run calls the path a claim's `http_status(path=...)` row spells, and falls back to `path:`
only when no row spells one. That row is where a parameterised route gets a real value, most
often a fact a fixture provides, and where a route that requires a query string gets it:

```markdown
- status: 200
- verify: http_status(code=200, path="/links/@seeded-link.id?format=full")
```

A flow step that walks the endpoint sends the query string that row spells, too.

A claim whose path still holds a `{…}` template variable when it is called is
`unresolved-precondition`, since no run can send it.

## `channel` and `message`

An endpoint answers one address family or the other — `method:`/`path:` for HTTP, or
`channel:` for a non-HTTP transport such as a websocket. `channel:` carries `locator=True,
address=True`, exactly as `method:`/`path:` do: it is where the endpoint is reached, not
something claimed about it, so like them it is inert while `normative=False`.

`message:` is `nested`, `entries`: a list of things that have claims, not a flat list and not
a record. A channel returns differently-shaped frames — each with its own direction, trigger
and payload — so a direct child of `message:` is one frame, and that frame's own bullets are
its grandchildren. `entries` mints one obligation per frame, never one for the whole block and
never one per grandchild.

```markdown
- channel: ws://events
- message:
  - update
    - direction: server-to-client
    - payload: `Update`
  - ack
    - direction: client-to-server
    - payload: `Ack`
```

Two frames, two obligations — `update` and `ack` — each carrying its own `direction:`/
`payload:` as properties, not as claims of their own.

## `response`

`response:` is a **record**: one thing with named properties, written as a nested block whose
direct children are `- name: value` pairs.

```markdown
- response:
  - media: `application/json`
  - body: `{"claim": {"id": str, "status": str}}`
```

It is the third container shape the grammar has, and the distinction is what a *child* is.
`does:` is a flat list of claims, so every descendant is itself a value. `provides:`/`flags:`
are lists of things that have claims, so a direct child is one value and a grandchild is that
value's property. A record is *one* thing, so a direct child is a property of it. Written as
the first shape — which is what an undeclared key falls back to — `- media:` and `- body:`
flatten into the strings `"media: ..."` and `"body: ..."`, and splitting them back apart means
picking a colon, which every JSON body written here has several of.

`response:` states nothing normative and mints no obligation. What the route answers with is
already claimed by `status:` and `errors:` above it, and a second claim about one fact is a
fact that can disagree with itself.

**Do not nest a bullet key under it.** `- status: 200` written under `- response:` is a
property of the response, and this endpoint's own `status:` claim — the one a scenario is held
to — is then absent. Both readings are grammatical, so the nesting is reported rather than
guessed at: `misnested-bullet`, remedied by promoting the bullet to the node's top level.

`response:` admits exactly four properties: `media:` (the content type), `body:` (an example
or a shape), `notes:` (anything else true of the response as a whole) and `field:` (one named
member of the body, repeated once per member). A child spelled any other way — `- schema: …` —
is a property this record's vocabulary does not carry, reported as `unknown-record-property`;
spell it as one of the four, or move the fact to the bullet that actually owns it.

The same collision fires under a key `endpoint` never declared at all. `request:` is not a
bullet key of this type, so `- method:` and `- path:` written under it are not read as this
node's own `method:`/`path:` — they flatten into the same strings an undeclared key's children
always flatten into, and nothing consults them there. `misnested-bullet` fires for this shape
too, because the buried child is spelled like a bullet key `endpoint` does declare; the message
says the parent is undeclared, since that is why the child is invisible rather than merely
misplaced. The remedy is the same: promote `method:`/`path:` to top-level bullets of the node.

## Arranging a request body

`consumes:` describes the shape a route accepts; it is a schema, not a value the run can send.
A `status:` arm whose method is not GET/DELETE/HEAD/OPTIONS needs an actual request body to
call the route at all, and only the performer of the step — an HTTP client — can send one, so
it is arranged the same way a browser step arranges state on its own surface: with `arrange:`,
using the `body(field*, value*)` act (see
[check-vocabulary.md](../check-vocabulary.md#the-act-vocabulary--the-other-closed-list)).

```markdown
- status: 201
- arrange: body(field="name", value="Widget A")
- arrange: body(field="quantity", value=3)
```

`arrange:` binds to the arm it is written under, same as `verify:`. A `status:` arm whose
method needs a body and arranges none compiles nothing for it — `unarranged-request-body`
(see [../doctor-codes.md](../doctor-codes.md)).

A route that reads nothing from its request, such as a `POST` that triggers a refresh, says so
with `arrange: no_body()`. The run then sends the call with no body. `no_body()` beside a
`body(...)` act contradicts it, and the call is withheld.

A body member may name a fact a fixture provides, as `value="@seeded-acme.id"`. The run sends
the value the fixture left, not the characters of the reference.

## Sending a credential

A route that refuses an anonymous caller answers 401 to every claim the book makes about it.
The caller's credential rides on the request, so it is arranged with the `header(name*, value*)`
act. The value names the fact the sign-in fixture provides, and the run substitutes it before
sending:

```markdown
- status: 200
- arrange: header(name="Authorization", value="Bearer @signed-in-editor.token")
```

A `header` act is the caller's, not one arm's. The run sends it with every claim of the
endpoint, and leaves it off a claim whose `http_status` row expects 401, because that claim is
about the anonymous caller. Arrange the credential once per endpoint.

The fixture has to mint the credential for real, against the app's own sign-in or its auth
emulator, and provide it under the key the header names. A fixture that only writes a file
naming a caller leaves the route anonymous. A header that names a fact no fixture in the
scenario provides is `unresolved-precondition`.

## A server fault is not a claim

A healthy app answers no request with a 5xx, so nothing a scenario sends can observe one. An
`http_status` row that expects 500 or above is `unarrangeable-server-fault`, and the run does
not send it. Say in the section's prose that the route answers 500 when a dependency fails.
Do not write it as an `emits:`, `errors:` or `status:` bullet, because each of those mints an
obligation the run owes a check.

## Minimal example

```bash
timeout 30 ostler scaffold endpoint create-link --in docs/features/acme/http/links-api.md
```

The command writes `docs/features/acme/http/create-link.md` and adds
`- [create-link](create-link.md)` under the server's `## Endpoints`.

```markdown
---
type: endpoint
slug: create-link
title: create-link
---
# create-link

- server: [Links API](links-api.md)
- method: POST
- path: /links
- fixture: signed-in-editor
- arrange: header(name="Authorization", value="Bearer @signed-in-editor.token")
- does: stores the submitted URL under a generated slug
- arrange: body(field="url", value="https://example.com/docs")
- verify: json_path(path="$.slug", matches="^[a-z0-9-]+$")
- capture: slug from $.slug
- status: 201 with the slug in the body
- arrange: body(field="url", value="https://example.com/docs")
- verify: http_status(code=201, path="/links")
- errors: 400 when the submitted URL is not absolute
- arrange: body(field="url", value="not-a-url")
- verify: http_status(code=400, path="/links")
- auth: any signed-in editor
- arrange: body(field="url", value="https://example.com/docs")
- verify: http_status(code=401, path="/links")
- code: internal/api/links.go::CreateLink
```

The `fixture:` and the credential sit above every claim, so they arrange each one. Each claim
sends its own request, so each arm carries its own `body` and its own `verify:`. The `auth:`
arm expects 401, so the run sends it without the credential. The `capture:` keeps the slug
for a later step of a [flow](flow.md).

The `fixture:` bullet is also what makes the endpoint's claims observable at all. An
endpoint's checks run in a scenario compiled per book file, and that scenario's world is
whatever the file's `fixture:` bullets arrange — so a file whose endpoints arrange nothing
is observed against whatever the scenario before it left behind. An endpoint whose claims
hold in whatever world the scenario finds says so with a reason: `- fixture: none, because
the route lists whatever is there`. A file that states neither is `unarranged-scenario`, and
no scenario is compiled for it.

## Doctor codes it can trip

`compound-normative-bullet`, `overlong-normative-bullet`, `undeclared-obligation`,
`weak-check`, `unstated-precondition`, `unparsed-check`, `misfiled-test-ref`,
`dangling-code-ref`,
`missing-code-symbol`, `unknown-book-fixture`, `unarranged-request-body`,
`unarrangeable-server-fault`, `deletes-shared-fixture`, `invalid-http-method`, `misnested-bullet`, `unarranged-scenario`,
`misbound-status-check`, `endpoint-without-server`, `unlisted-endpoint`, `inline-endpoint`. See
[../doctor-codes.md](../doctor-codes.md).

## When bullets are not enough

Bullets state what this route does. If a reader could pick the wrong route — a v1 endpoint and
its replacement, each right in its own context — and still satisfy every claim on it, that
belongs in a [`concept`](concept.md), pointed at with `detail:`.
