# `rpc`

One method of a [`grpc-server`](grpc-server.md): the request it answers and what answering it does.

## Identity

File type. One page per rpc, in the folder of its [`grpc-server`](grpc-server.md) page, named after the method. Its id is the page's path. The page's `server:` bullet links the grpc-server, and the grpc-server's `## RPCs` section links the page back.

A `### <id>` under a grpc-server's `## RPCs` heading still reads as an rpc. Doctor reports each one as `inline-endpoint`, the code every hosted page shares.

## Bullet keys

| key | required | what it does |
| --- | --- | --- |
| `server` | yes, on a page | link — the one `grpc-server` page this rpc is served from |
| `name` | yes | the full method, `package.Service/Method`. A run calls exactly this name |
| `streaming` | yes | `unary` or `server`. The client sends one request, and a `server` rpc answers with a stream of messages |
| `does` | no | nested; **mints an obligation** per value |
| `emits` | no | **mints an obligation** (via the shared set) |
| `consumes` | no | **mints an obligation** (via the shared set) |
| `request` | no | a record — what the call carries, as named properties |
| `response` | no | a record — what comes back, as named properties |
| `status` | no | **mints an obligation** — the gRPC code of an outcome, one claim per value. It opens with one of the 17 canonical code names |
| `errors` | no | **mints an obligation** — the refusal arm |
| `error` | no | alias of `errors` |
| `auth` | no | **mints an obligation** — who may call it |
| `authorization` | no | alias of `auth` |
| `code` | no | link, **owns** its file |
| `contract` | no | link, **owns** its file. The proto that declares the method |
| `detail` | no | link — an explanatory [`concept`](concept.md) |
| `verify` | no | a check |
| `fixture` | no | a fixture |
| `arrange` | no | an act — a request member or a metadata row the step's own performer sends |
| `capture` | no | a capture |
| `tests` | no | link — the test files covering it |

`emits:`/`consumes:` carry no `normative` flag of their own here. They are normative because the [shared set](../bullet-grammar.md#keys-that-are-normative-on-every-type) makes them so on every type.

The outcome keys are declared in this order so `fmt` can place them between the effect and its grounding: `does → status → errors → auth → code → verify`. A `verify:` written under one binds to that one. See [document order is the binding](../bullet-grammar.md#document-order-is-the-binding).

## `name`

The method a run calls, written the way grpcurl and the proto spell it. The package is dotted lower snake, and the service and the method are PascalCase: `ticket.v1.TicketService/GetTicket`. Any other spelling is `unparsable-bullet-value`.

When the hosting grpc-server states `contract:`, doctor checks the book's rpc pages against the proto: a declared method with no page is `rpc-missing`, and a page whose name the contract lacks is `rpc-phantom`.

## `status`

The gRPC code the call ends with. It declares the `grpc-code` value kind, so `- status: NOT_FOUND when the ticket is unknown` parses and `- status: 404` is `unparsable-bullet-value`. The 17 names are `OK`, `CANCELLED`, `UNKNOWN`, `INVALID_ARGUMENT`, `DEADLINE_EXCEEDED`, `NOT_FOUND`, `ALREADY_EXISTS`, `PERMISSION_DENIED`, `RESOURCE_EXHAUSTED`, `FAILED_PRECONDITION`, `ABORTED`, `OUT_OF_RANGE`, `UNIMPLEMENTED`, `INTERNAL`, `UNAVAILABLE`, `DATA_LOSS` and `UNAUTHENTICATED`.

A claim proves its status with `grpc_status(code="NOT_FOUND")` and its reply with `json_path` rows, which read the reply message.

```markdown
- status: NOT_FOUND when the ticket is unknown
- verify: grpc_status(code="NOT_FOUND")
- arrange: body(field="id", value="no-such-ticket")
```

## `request` and `response`

Each is a **record**: one thing with named properties, written as a nested block whose direct children are `- name: value` pairs. The four properties are `media:`, `body:`, `notes:` and `field:`, as on an [`endpoint`](endpoint.md) response. Neither mints an obligation. What the call answers with is already claimed by `status:` and `errors:`.

## Sending a credential

A call that refuses an anonymous caller answers `UNAUTHENTICATED`. The caller's credential rides as metadata, arranged with the `header(name*, value*)` act, and the value names a runbook secret:

```markdown
- arrange: header(name="authorization", value="Bearer $TICKET_TOKEN")
```

The run substitutes `$TICKET_TOKEN` from the secret the [`runbook`](runbook.md) mints at bring-up. The value never reaches the plan, the evidence or the report.

## Minimal example

```bash
timeout 30 ostler scaffold rpc get-ticket --in docs/services/acme/grpc/ticket-service.md
```

```markdown
---
type: rpc
title: get-ticket
---
# get-ticket

- server: [Ticket service](ticket-service.md)
- name: ticket.v1.TicketService/GetTicket
- streaming: unary
- fixture: none, because the call reads a seeded ticket
- status: NOT_FOUND when the ticket is unknown
- verify: grpc_status(code="NOT_FOUND")
- arrange: body(field="id", value="no-such-ticket")
```

## Doctor codes it can trip

`compound-normative-bullet`, `overlong-normative-bullet`, `undeclared-obligation`, `weak-check`, `unparsed-check`, `unarranged-scenario`, `misnested-bullet`, `missing-required-bullet`, `unparsable-bullet-value`, `endpoint-without-server`, `unlisted-endpoint`, `inline-endpoint`, `rpc-phantom`. See [../doctor-codes.md](../doctor-codes.md).
