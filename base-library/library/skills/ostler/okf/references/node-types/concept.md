# `concept`

The one type in the registry with **no normative keys at all**. Its whole bullet vocabulary is
`code:` and `extends:` — so it mints no obligation, no check is required of it, no QA plan is
ever asked to prove it. Its body *is* its content.

That is not an oversight in the registry. It is the escape hatch, and this file is the
documentation it never had.

## Why the escape hatch is needed

Every other type is mechanical. Its keys mint obligations, resolve as links, and are graded.
That is what makes the book checkable — and it is also its ceiling. A registry can describe
*what a node is*. It can never say *whether you should be using it*.

Take a codebase with two notification services: one legacy, one current, each correct in a
different context. Both produce perfectly conformant nodes — accurate `code:` grounding,
well-split `does:` bullets, discriminating `verify:` checks. `ostler doctor` is green on both.
Every claim on both is true. And a reader arriving at either one has no way to learn the only
thing that mattered: which one to reach for, and when.

Nothing in the bullet format says it, and the near-misses are worth naming so nobody reaches
for one by mistake:

- **`exclusive-with:` is not supersession.** Despite the name it is a DOM co-render assertion,
  consumed only by locator-collision suppression — two controls that share a role+name but
  never appear together.
- **`extends:` is inheritance**, not replacement: this node is a specialization of that one.
- **`legacySurface`** exists only on epic *seeds*, in the planning layer. It never reaches the
  book.
- **The `legacy` in doctor's reachability rules** is an unrelated root waiver, not a marker on
  a node.

So the answer is not a new flag. It is prose, in the one type built to carry it.

## What belongs in a concept

- **Which of two implementations to reach for, and when.** The selection rule, stated as a
  rule, with the context each side is correct in.
- **What is deprecated, and what still legitimately uses it.** A deprecation with no list of
  legitimate remaining callers reads as "delete this", which is usually wrong.
- **Invariants that span nodes** — something true of the pair that neither node can state
  alone.
- **The rationale a future reader needs before choosing.** Why it is this way, and what
  changes if it stops being.

## The linking convention

A concept nobody can find is a concept nobody reads. **Each competing node points at the
concept**, so the selection rule is reachable from either side rather than discoverable only
by browsing.

`detail:` is the key for exactly this:

```markdown
- detail: [notification delivery](../concepts/notification-delivery.md)
```

It works on **any** node type. It is a *relation* key, and relations are handled globally by
key name rather than per type: the link resolves and `unresolved-relation` guards it wherever
it is written, and relation keys are excluded from the load-bearing set, so it never raises
`unknown-bullet` on a type that does not list it. Every implementation-bearing type also
declares it — screen, cli, server, format, flow, component, interaction, invocation, method,
[`command`](command.md) and [`endpoint`](endpoint.md) — which means `ostler fmt` has a
canonical slot for it, right after the `code:` grounding it qualifies.

A prose link from the node's body works too, and is the better choice when the pointer needs a
sentence of its own to be useful.

## Identity

File type under `docs/features/<service>/concepts/`, `type: concept` in frontmatter.

## Bullet keys

| key | required | what it does |
| --- | --- | --- |
| `code` | no | link, **owns** its file — `path::symbol` |
| `extends` | no | resolves as a link — the concept this one specializes |

Plus the [shared normative keys](../bullet-grammar.md#keys-that-are-normative-on-every-type).
These are the one way a concept *can* mint an obligation — a `consistency:` or `persistence:`
rule that spans the nodes it governs. Use them when the concept genuinely states a checkable
system-wide invariant; do not reach for them to make prose feel more official.

## Required sections

None. `## Methods` and `## Fields` are conventional when the concept is a type with an API.

## Relationships

Pointed at by `detail:` from any node that needs it, and by prose links from node bodies. Points at another concept with `extends:`.

## Minimal example

```bash
timeout 30 ostler scaffold concept notification-delivery --service acme
```

```markdown
---
type: concept
---

# Notification Delivery

Two delivery paths exist and both are current.

`NotifyV2` is the default for every new call site: it batches per recipient, retries with
backoff, and is the only path that honours per-user quiet hours. Reach for it unless one of
the exceptions below applies.

`LegacyNotifier` remains in use for the billing dunning sequence alone, because dunning
requires the synchronous send receipt that V2's batching cannot produce. It is not deprecated
and must not be migrated without replacing that receipt; it is also not a general-purpose
option, and a new call site reaching for it is a defect.

- code: internal/notify/v2.go::NotifyV2
- code: internal/notify/legacy.go::LegacyNotifier
```

## Doctor codes it can trip

`okf-missing-type`, `dangling-code-ref`, `missing-code-symbol`, `unresolved-relation` on
`extends:`, and — if it uses the shared normative keys — `undeclared-obligation` and
`weak-check`. See [../doctor-codes.md](../doctor-codes.md).

Prose is not checked, deliberately. Nothing in this file's body can trip a doctor code, which
is precisely why the judgment it carries has to be written where a reader will find it.
