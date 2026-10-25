# `grpc-server`

A gRPC service: the surface that answers remote procedure calls. Reach for `grpc-server` for the service itself. Each method is an [`rpc`](rpc.md) node under this file's `## RPCs`.

Not a grpc-server: an HTTP service ([`server`](server.md)), the environment it runs in ([`environment`](environment.md)) or the recipe that brings it up ([`runbook`](runbook.md)). A grpc-server node carries a fallback launch contract, and a runbook supersedes it.

## Identity

File type under `docs/services/<service>/grpc/`, `type: grpc-server` in frontmatter. The `serves:` bullet names the proto services it answers for.

## Bullet keys

| key | required | what it does |
| --- | --- | --- |
| `serves` | yes | the full proto service names this server answers for, such as `ticket.v1.TicketService`. Readiness asks the running server's reflection for each name, so a different stack answering on the same port is not mistaken for this one |
| `contract` | no | link, **owns** its file. The proto folder the service is declared in |
| `code` | no | link, **owns** its file |
| `detail` | no | link — an explanatory [`concept`](concept.md) |
| `verify` | no | a check — what observing this server's claims looks like |
| `launch` | no | the bring-up command |
| `entry-url` | no | the address the service listens on, written `grpc://host:port`. A compiled QA plan's calls go there. The scheme also picks the readiness probe: `grpc://` asks the standard health service for SERVING, where `http(s)://` asks a path (`unparsable-bullet-value` for any other spelling) |
| `health-path` | no | unused by a `grpc://` address, which asks `grpc.health.v1.Health/Check` |
| `working-directory` | no | cwd for `launch`, relative to the repo root |
| `identity` | no | unused by a `grpc://` address, which proves identity through `serves:` |
| `stop` | no | teardown recipe |
| `boot-timeout` | no | seconds; ceiling on bring-up |

The seven keys from `launch:` down are the **fallback launch contract**, the same one a [`server`](server.md) carries. A [`runbook`](runbook.md) node supersedes them.

Plus the [shared normative keys](../bullet-grammar.md#keys-that-are-normative-on-every-type).

## Required sections

`## RPCs` — required and required to be non-empty. It links each [`rpc`](rpc.md) page.

## Relationships

A runbook exposes this node through `surfaces:`. RPCs inside it point at explanatory nodes with `detail:`.

## Minimal example

```bash
timeout 30 ostler scaffold grpc-server ticket-service --service acme
```

```markdown
---
type: grpc-server
---

# Ticket service

- entry-url: grpc://localhost:50051
- serves: ticket.v1.TicketService
- contract: [ticket protos](../../../../proto/ticket/v1)

## RPCs

- [get-ticket](get-ticket.md)
```

## Doctor codes it can trip

`missing-required-section`, `empty-required-section`, `missing-required-bullet`, `unparsable-bullet-value`, `dangling-code-ref`, `missing-code-symbol`, plus whatever its `rpc` children trip. See [../doctor-codes.md](../doctor-codes.md).

## When bullets are not enough

Bullets state what this service is. If a reader could pick the wrong service and still satisfy every claim on it, that belongs in a [`concept`](concept.md), pointed at with `detail:`.
