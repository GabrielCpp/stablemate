# resource

An outside system the book's claims depend on or look at, such as a booking service that leases a
lab camera or a CLI tool the stack shells out to. A `resource` page says how the harness reaches
the system, how it asks whether the system is there, and which records of its own a claim may
read back. A [`fixture`](fixture.md) acts on the resource with `kind: borrow` and `kind: release`
steps, and a claim reads the resource with an `observe:` bullet. The page holds neither the
borrowing nor the claims, because the fixture holds the facts and the claim names the fixture.

## Identity

A `resource` node is **file-level** (`kind="file"`, `context="resources"`). The whole file is
the node. Its id is the repo-relative path (`docs/services/<service>/resources/<name>.md`), and
the name other bullets reference it by is the file's stem: `camera-booking.md` is named
`camera-booking`. A step's `on:` and a claim's `observe:` both write that stem or link the page.

## Bullet keys

| key | required | what it does |
| --- | --- | --- |
| `reach:` | **yes** | How the harness talks to the system: `http` or `cli`. Anything else is `resource-reach-shape`. |
| `base:` | with `reach: http` | The URL every request path is appended to. It may carry `$NAME`, which the harness expands from its own environment at run time. A `$NAME` that is unset is a capability fault on the resource, so every claim that needs it is gapped. |
| `credential:` | no, `http` only | Nested. `- header: Authorization` and `- secret: CAMERA_BOOKING_TOKEN` are both required. The harness sends `<header>: <value of the env var>` on every request on this resource. `- scheme: Bearer` is optional and prefixes the value. The `secret:` is an environment-variable NAME, never a value. |
| `binary:` | with `reach: cli` | The program name the steps' `run:` commands call. The harness looks it up with `which` before the first step on the resource. A missing program is a capability fault. |
| `secrets:` | no, `cli` only | Nested. Environment-variable NAMES the harness puts in the environment of every `run:` on this resource. A name unset in the harness's environment is a capability fault. |
| `install:` | no, `cli` only | One line telling a person how to get the binary. The gap detail prints it. |
| `code:` | no | Link, **owns** its file, the same as on the other types. |

A key from the other reach is `resource-reach-shape`: an `http` page with `binary:`, `secrets:`
or `install:`, and a `cli` page with `base:` or `credential:`.

**The secret rule.** The value of a credential lives in the harness's environment and nowhere
else. The page names the variable. No page, plan or transcript carries the value. The harness logs
a request as `METHOD url` and never logs a header value, nor a body that a `secrets:` value was
substituted into.

## `## Probe`

Exactly one step, a `### <id>` heading with `kind: probe`. The id is free. An `http` resource
states `request: GET <path>` and a `cli` resource states `run: <command>`. The probe answers yes
when the request returns a 2xx status or the command exits 0.

The harness runs the probe once per harness process, before the first step or observation on the
resource. A no answer gaps every claim that needs the resource. The claim reads
`gapped: <resource name> absent`, where the name is the resource's stem with its dashes as
spaces. A writer never sees a gapped claim, because only a person can bring the system back.
Name the page after the system, so `camera-booking.md` gaps its claims as
`gapped: camera booking absent`.

## `## Observations`

One step per observation, a `### <name>` heading with `kind: observe`. An `http` observation
states `request: GET <path>` and a `cli` observation states `run: <command>` that prints JSON on
stdout. The JSON the request returns or the command prints is the document a claim's checks read.
The path may carry `@<fixture>.<key>` and `$<captured-name>` references, the way a route path
does.

A claim reads an observation with `observe: @<stem>.<name>`. See
[bullet-grammar.md](../bullet-grammar.md#a-claims-side-observation).

The section may be empty. A resource with no observation offers no side check.

## Relationships

- A fixture step names the resource with `on: [Camera booking](../resources/camera-booking.md)`
  or the bare stem. An `on:` that resolves to no `resource` page is `unresolved-relation`.
- A claim names an observation with `observe: @camera-booking.leases`.
- `ostler explain <name>` prints the page, its probe, its observations, the fixtures that borrow
  it and the claims that reach it.

## Minimal example

```bash
timeout 30 ostler scaffold resource camera-booking --in docs/services/acme/resources/
```

A resource that leases a device, behind a bearer token:

```markdown
---
type: resource
title: Camera booking
---
# Camera booking

The booking service that leases the lab camera to one run at a time.

- reach: http
- base: http://booking.example.internal:8080
- credential:
  - header: Authorization
  - scheme: Bearer
  - secret: CAMERA_BOOKING_TOKEN

## Probe

### answers

- kind: probe
- request: GET /health

## Observations

### leases

- kind: observe
- request: GET /leases
```

A resource the app only writes to, with one record of its own to read back:

```markdown
---
type: resource
title: Camera
---
# Camera

- reach: http
- base: http://camera.example.internal:9000

## Probe

### answers

- kind: probe
- request: GET /health

## Observations

### recordings

- kind: observe
- request: GET /recordings
```

## Doctor codes it can trip

See [`../doctor-codes.md`](../doctor-codes.md): `resource-reach-shape`, `resource-probe-shape`,
`resource-observation-shape`, `missing-required-section` on a page with no `## Probe`,
`unresolved-relation` on a step's `on:`, `step-request-shape`, `step-reach-mismatch`,
`unknown-observation`, and `fixture-probe-local` when `base:` names `localhost`, `127.0.0.1`,
`0.0.0.0` or `[::1]`.

## When bullets are not enough

A system that needs a different reach for each of two operations is two resources. A fact about
why the system is leased, or when a person may lease it by hand, belongs in a
[`concept`](concept.md) linked from the page.
