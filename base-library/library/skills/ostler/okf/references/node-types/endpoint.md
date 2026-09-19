# `endpoint`

One route or channel of a [`server`](server.md): the request it answers and what answering it
does.

## Identity

Section type. A `### <id>` under a `## Endpoints` heading in a `server` file. Its id is
`path#anchor`.

## Bullet keys

| key | required | what it does |
| --- | --- | --- |
| `method` | no | the HTTP method |
| `path` | no | the route path |
| `channel` | no | the channel, for non-HTTP transports |
| `message` | no | the message shape, for non-HTTP transports |
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

## Minimal example

```bash
timeout 30 ostler scaffold endpoint create-link --in docs/features/acme/http/links-api.md
```

```markdown
### create-link

- method: POST
- path: /links
- does: stores the submitted URL under a generated slug
- verify: created(subject="a link row for the submitted URL")
- status: 201 with the slug in the body
- verify: http_status(code=201, path="/links")
- errors: 409 when the requested slug is already in use
- verify: http_status(code=409, path="/links")
- auth: any signed-in editor
- code: internal/api/links.go::CreateLink
- fixture: signed_in_editor
```

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
`invalid-http-method`, `misnested-bullet`, `unarranged-scenario`,
`misbound-status-check`. See
[../doctor-codes.md](../doctor-codes.md).

## When bullets are not enough

Bullets state what this route does. If a reader could pick the wrong route — a v1 endpoint and
its replacement, each right in its own context — and still satisfy every claim on it, that
belongs in a [`concept`](concept.md), pointed at with `detail:`.
