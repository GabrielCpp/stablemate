# `flow`

An end-to-end path through the system: the ordered walk from a starting condition to an
observable outcome. Reach for `flow` when the thing worth recording is a *sequence across
nodes* that no single node holds.

Not a flow: the boot sequence of a stack — that is a [`runbook`](runbook.md) and its
[`step`](step.md) children. Not a flow: a single control's behaviour, which is an
[`interaction`](interaction.md).

## Identity

File type under `docs/features/<service>/flows/`, `type: flow` in frontmatter.

## Bullet keys

| key | required | what it does |
| --- | --- | --- |
| `start` | no | **mints an obligation** — the starting condition |
| `steps` | no | nested; each child resolves as a link |
| `end` | no | **mints an obligation** — the observable outcome |
| `code` | no | link, **owns** its file — the implementation the flow's steps walk through |
| `detail` | no | link — an explanatory [`concept`](concept.md) |
| `verify` | no | a check |
| `fixture` | no | arranges the world the walk starts in — or `none, because ...` |
| `tests` | no | resolves as a link — the test files covering this flow |

`start:` and `end:` are the flow's claims, and the pair is what makes a flow provable: the
walk is only worth recording if there is a state it begins in and a state it ends in that a
scenario can assert.

On a `cli`, `start:` is observed before the first step, in the working directory the walk
begins in. No command has run at that moment, so its `verify:` is
`absent(subject="<file>")` on the exact relative path of a file the walk goes on to create.
A check that reads a command's output, or that compares the directory either side of a run,
has nothing to read there, and the compiler refuses it as `uncompilable-claim`. A starting
world that holds files is stated on `fixture:` instead.

`end:` spans the whole walk. A check on it that compares the directory either side, such as
`unchanged`, `created` or `removed`, reads the directory before the first step and again after
the last. So `end: unchanged(subject="<file>")` claims the walk as a whole left that file as
it found it. On a walk whose `start:` says the file is absent and whose first step creates
it, that claim is false for a correct app. A claim about one step, such as a preview that
writes nothing, is not the flow's claim. It goes on the command or invocation that step links
to, with a `fixture:` that puts the file in place and `verify: unchanged(subject="<file>")`.
The flow's `end:` then states what the whole walk leaves behind.

A flow's claims are about the world its steps left behind, and that world is the world they
started in plus the walk — so the starting world is part of the claim, and the flow states it.
`- fixture: <name> [args] — <state it leaves>` arranges it before the first step. A flow whose
claims hold in whatever world it finds says so with a reason: `- fixture: none, because the
first step creates everything the last step observes`. A flow that states neither is
`unarranged-journey`, and no scenario is compiled for it — a walk run against whatever the
previous scenario happened to leave asserts `end:` against accidental state, and the red it
produces is evidence about the run order, not about the service. A bare `- fixture:` or a bare
`- fixture: none` is the undecided case, not the second answer.

`tests:` is not an obligation and not evidence. Its one reader is the regression node, which
attributes a failing suite test back to the node that owns it — that reader needs a *path* and
can do nothing with an observation. That is why it split from `verify:` rather than sharing it.

Plus the [shared normative keys](../bullet-grammar.md#keys-that-are-normative-on-every-type).

## Required sections

None. The `steps:` chain is the body.

## Relationships

Each child of `steps:` links to the node that performs it — an interaction, an invocation, an
endpoint. `ostler graph` is the structural authority for what a flow reaches.

A step may link more than the node that performs it. When a child links an interaction,
invocation, endpoint or command, that link is the step, and every other link in the child is
context the walk performs nothing for: the screen it sits on, the component it mounts, the field
it reads. A child that links only screens, components or fields says what the reader sees and
adds no step. An endpoint that one of the journey's invocations names as its `on:` is that
invocation's request, so a browser journey that links the endpoint its page calls stays one
browser journey.

On a `cli`, a step performs one command line, so the node it links states exactly one distinct
`run:` in its own bullets. That node is usually an invocation. The compiler refuses a step whose
node states no `run:`, or several different ones, because it cannot tell which run the step
means.

On an `http` surface, a step whose endpoint's `route:` carries a path variable, such as
`GET /{key}`, requests the value the walk already holds for that name. An earlier step's
endpoint supplies it with `capture: key from $.key`, so the request goes to the link the walk
just made. Without such a capture, the flow's `fixture:` supplies it when exactly one fixture
`provides:` a key of that name. A name neither supplies stays a template, and the compiler
files it as `unresolved-precondition` on the step.

On a `web` surface, a step whose node fires on `trigger: load` or `trigger: navigate` is an
arrival. The reader reaches it by typing or following an address, not by a click. The walk
performs the node's own `arrange:` acts, so `arrange: visit(path="/de")` opens `/de`. A node
that arranges nothing opens the screen it sits on, by the book's navigation path. The compiler
files an arrival that has neither as `uncompilable-claim`.

A step on an `http` surface sends what its endpoint arranges. Its headers and body are the
endpoint's `arrange:` acts under its claims, never the ones under its `errors:`. Its query
string is the one the endpoint's own `http_status` row spells. A flow carries no `arrange:` of
its own. A step that sends a fact a fixture provides, such as `Bearer @signed-in-editor.token`,
needs that fixture on the flow's own `fixture:` row, because a flow runs only the fixtures it
names. A flow with `fixture: none` sends no credential, so a route that refuses an anonymous
caller answers 401 on every walk.

Every step before the last must succeed. A step that answers 4xx or 5xx stops the walk, and the
flow's checks never run. Each `verify:` on a flow observes the one response its last step got,
so a flow checks one outcome. A refusal such as 401 or 403 is a claim on the endpoint's
`errors:`, not a second `end:` of the flow.

**A journey whose steps cross targets is legal, and today it compiles to nothing.** A step's
target is its node type paired with the `driver:` of the surface it lives on, so a flow that
walks a mobile app and then a web app — or drives an api and then a browser — names two. One
compiled scenario binds one driver to one service, so there is no shape for that journey yet,
and the compiler says so with `needs-multi-target-runtime` rather than asking anyone to change
the book. One case is a defect: a browser journey that links the endpoint its page calls,
from an invocation whose `on:` names something else. Make that endpoint the invocation's `on:`.
**A journey that crosses targets is not otherwise a defect in the flow.** Write the
journey the user actually performs; a journey that is really two, performed by two people or
two sittings, is two flows, and splitting it to make the compiler happy records a walk nobody
takes.

## Minimal example

```bash
timeout 30 ostler scaffold flow shorten-and-follow --service acme
```

```markdown
---
type: flow
---

# Shorten and Follow

- fixture: signed-in-editor
- start: a signed-in editor with no links
- verify: count(subject="links owned by the signed-in editor", equals=0)
- steps:
  - [create-link](../http/create-link.md)
  - [follow-link](../http/follow-link.md)
- end: the browser lands on the original URL
- verify: http_status(code=302, path="/{slug}")
- tests: tests/e2e/shorten_test.go
```

The `fixture:` signs the editor in, so the create-link step sends the credential its endpoint
arranges. That endpoint's `capture: slug from $.slug` hands the new slug to the follow-link
step's `/{slug}`.

The steps here are http calls, so a token sign-in arranges them. A flow whose steps a browser
performs needs the session in that browser instead. Its fixture opens the sign-in screen and
acts on it, as [fixture.md](fixture.md#signing-a-browser-in) shows.

## Doctor codes it can trip

`unresolved-relation` on a `steps:` child, `undeclared-obligation` when `start:`/`end:` are
stated with no check, `unarranged-journey` when the flow neither arranges a world nor says it
needs none, `weak-check`, `compound-normative-bullet`, `overlong-normative-bullet`. See [../doctor-codes.md](../doctor-codes.md).

## When bullets are not enough

The chain states the path. If a reader could follow the wrong path — a legacy flow and its
replacement, each right in its own context — and still satisfy every claim on it, that belongs
in a [`concept`](concept.md), pointed at with `detail:`.
