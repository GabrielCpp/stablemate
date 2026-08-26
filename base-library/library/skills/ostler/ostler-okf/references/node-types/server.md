# `server`

An HTTP service: the surface that answers requests. Reach for `server` for the service itself;
each route is an [`endpoint`](endpoint.md) node under this file's `## Endpoints`.

Not a server: the environment it runs in ([`environment`](environment.md)) or the recipe that
brings it up ([`runbook`](runbook.md)). A server node *carries* a fallback launch contract, but
a runbook supersedes it.

## Identity

File type under `docs/features/<service>/http/`, `type: server` in frontmatter.

## Bullet keys

| key | required | what it does |
| --- | --- | --- |
| `code` | no | link, **owns** its file |
| `openapi` | no | link, **owns** its file |
| `launch` | no | the bring-up command |
| `entry-url` | no | base URL the app serves on |
| `health-path` | no | readiness path under `entry-url` (default `/`) |
| `working-directory` | no | cwd for `launch`, relative to the repo root |
| `identity` | no | substring of the health body proving the stack is ours |
| `stop` | no | teardown recipe |
| `boot-timeout` | no | seconds; ceiling on bring-up |
| `walkthrough` | no | `true` on the one server the walk drives |

The eight keys from `launch:` down are the **walkthrough launch contract**. They are
documentation, not configuration — that is what lets a walk run standalone from the book. A
[`runbook`](runbook.md) node supersedes them; this is the fallback for a service that has none.

Plus the [shared normative keys](../bullet-grammar.md#keys-that-are-normative-on-every-type).

## Required sections

`## Endpoints` — required and required to be non-empty.

## Relationships

A runbook exposes this node through `surfaces:`. Endpoints inside it point at explanatory
nodes with `detail:`.

## Minimal example

```bash
timeout 30 ostler scaffold server links-api --service acme
```

```markdown
---
type: server
---

# Links API

- code: internal/api/server.go::NewServer
- entry-url: http://127.0.0.1:8080
- health-path: /healthz
- identity: links-api

## Endpoints

### create-link

- method: POST
- path: /links
- does: stores the URL under a generated slug
- status: 201 with the slug in the body
- code: internal/api/links.go::CreateLink
- verify: http_status(code=201)
```

## Doctor codes it can trip

`missing-required-section`, `empty-required-section`, `dangling-code-ref`,
`missing-code-symbol`, plus whatever its `endpoint` children trip. See
[../doctor-codes.md](../doctor-codes.md).

## When bullets are not enough

Bullets state what this service is. If a reader could pick the wrong service — a legacy API and
its replacement, each right in its own context — and still satisfy every claim on it, that
belongs in a [`concept`](concept.md), pointed at with `detail:`.
