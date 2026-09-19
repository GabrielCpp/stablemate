# `invocation`

Something the *system* does without a person driving it: a webhook arriving, a scheduled job
firing, a queue consumer waking. Reach for `invocation` for a machine-driven action; the
human-driven counterpart is an [`interaction`](interaction.md).

The two types share most of their shape on purpose — the difference is the actor, and that is
the distinction the `node-type` defect kind exists for.

## Identity

Section type. A `### <id>` under an `## Invocations` heading. Its id is `path#anchor`.

## Bullet keys

| key | required | what it does |
| --- | --- | --- |
| `on` | **yes** | link — the node this acts on |
| `trigger` | **yes** | what fires it |
| `when` | no | **mints an obligation** — the condition it applies under |
| `extends` | no | link — the base invocation this one narrows |
| `same-as` | no | link, multi-valued — another node documenting this same job |
| `does` | **yes** | nested; **mints an obligation** per value |
| `emits` | no | **mints an obligation** (via the shared set) |
| `consumes` | no | **mints an obligation** (via the shared set) |
| `status` | no | **mints an obligation** — one claim per value |
| `errors` | no | **mints an obligation** — the refusal arm |
| `error` | no | alias of `errors` |
| `auth` | no | **mints an obligation** — who may cause it |
| `authorization` | no | alias of `auth` |
| `code` | no | link, **owns** its file |
| `detail` | no | link — an explanatory [`concept`](concept.md) |
| `verify` | no | a check |
| `fixture` | no | a fixture |
| `capture` | no | a capture |
| `tests` | no | link — the test files covering it |

`emits:`/`consumes:` are normative through the
[shared set](../bullet-grammar.md#keys-that-are-normative-on-every-type), not through a flag of
their own — one obligation per value either way. The outcome keys sit between the effect and
its grounding so a `verify:` written under one binds to that one.

An invocation carries no `role:`/`name:`/`keyboard:`: there is no operator to announce
anything to. If those apply, it is an interaction.

`same-as:` says this invocation and the one it names are the *same* documented job,
described again in a second place — not a narrower version of it, and not a winner over a
loser. It is symmetric and must be declared on both sides. Its consumer is the QA obligation packet: a change to the cited symbol maps to every node that cites it, and without `same-as:` one thing written in three places reads as three things and trips the container fan-out demotion that exists to catch sprawl. `same-as:` is the declared fact that collapses them back into one family.

The occurrences must also *agree*: each states the same normative claims, not two different
ones. A member that omits a key is not a disagreement — silence just means that occurrence
was written cheaply, without repeating a claim another occurrence already made — but two
members that both state a key must state the same value; `doctor`'s `same-as-disagreement`
finds it when they don't.

Contrast it with `extends:`, which says the node is a narrower version of the thing it
names rather than another writing of the same thing.

## Relationships

`on:` links the node acted on. `detail:`, `extends:` and `same-as:` all point at another node.

## Minimal example

```bash
timeout 30 ostler scaffold invocation expire-stale-links --in docs/features/acme/http/links-api.md
```

```markdown
### expire-stale-links

- on: [links-api](links-api.md)
- trigger: the nightly scheduler, at 03:00 UTC
- when: a link has not been followed for 90 days
- does: marks the link expired and stops resolving it
- verify: removed(subject="the stale link from the active index")
- emits: link.expired, one per expired link
- verify: emitted(event="link.expired", count=1)
- code: internal/jobs/expire.go::ExpireStale
- fixture: link_last_followed_91_days_ago
```

`invocation` declares no `response:` key at all, yet books written against an HTTP-shaped
invocation still nest a `- response:` block with `- status:`/`- errors:` children under it —
`status:` and `errors:` are bullet keys this type *does* declare. Because `response:` is not a
key `invocation` recognizes, those children fall back to the flat-subtree grammar and flatten
into strings nothing reads as this node's own `status:`/`errors:` claims; the claims a scenario
is actually held to are then absent. `misnested-bullet` fires on this shape exactly as it does
when the buried child sits under a *declared* record on another type, except the message says
the parent (`response:`) is undeclared, because that is why the child is invisible rather than
merely misplaced. Fix it by promoting `status:`/`errors:` to top-level bullets of the node.

## Doctor codes it can trip

`missing-required-bullet` (`on:`, `trigger:`, `does:`), `undeclared-obligation`, `weak-check`,
`unstated-precondition`, `compound-normative-bullet`, `unresolved-relation`, `one-way-same-as`
if `same-as:` is used, `same-as-disagreement` if a `same-as:` family disagrees about a shared
normative key, `misbound-status-check`, `misnested-bullet` if a child spelled like a declared
bullet key is buried under a key `invocation` does not declare (`response:`, most commonly).
See [../doctor-codes.md](../doctor-codes.md).

## When bullets are not enough

Bullets state what this job does. If a reader could pick the wrong one — a legacy job and its
replacement, each right in its own context — and still satisfy every claim on it, that belongs
in a [`concept`](concept.md), pointed at with `detail:`.
