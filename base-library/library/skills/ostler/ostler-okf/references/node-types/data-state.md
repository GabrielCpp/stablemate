# `data-state`

One situation a record on the server can be in, told apart by reading it back. Reach for
`data-state` when a route moves a record between situations, such as a bill that is issued and
then paid, or when a case depends on the record being in one of them. Name a lifecycle only then.
A flag that always answers the same is not a state. A value such as a limit or a role is not a
state either.

## Identity

Section type. A `### <title>` under a `## Data states` heading in a [`server`](server.md) or
[`cli`](cli.md) file, and in no other page type. Its id is `path#anchor`. The heading is
`Data states`, not `States`, so it never reads as the screen [`state`](state.md) section.
`of:` groups the states of one lifecycle: states on one page with the same `of:` are siblings.

## Bullet keys

| key | required | what it does |
| --- | --- | --- |
| `of` | yes | one plain word naming the record, such as `bill` |
| `observe` | yes | link: the [`endpoint`](endpoint.md) or [`command`](command.md) that reads the record |
| `verify` | yes | one or more checks on that read's answer. They tell this state apart from its siblings |
| `fixture` | no | a fixture that puts a record in this state. A state only another system writes is reached this way |
| `code` | no | link, **owns** its file |
| `detail` | no | link: an explanatory [`concept`](concept.md) |

A data state owes one obligation, and each `moves:` row that lands on it owes one. A walk covers
the state when it reads a record in it. A flow step covers the state by the read-back after a
`moves:` row that lands on it. A route or case that moves a record to it says so with `moves:` on
the [`endpoint`](endpoint.md) or [`invocation`](invocation.md).

A move no flow takes gets a one-move walk. The walk arranges the starting state's `fixture:`, reads
the record through that state's `observe:`, sends the move's request and reads the record back.
For `to B` the starting state is the first sibling of B with a `fixture:`, else B. A starting state
with no `fixture:` leaves the move uncovered, and the gap names that state.

A state with a `fixture:` that no walk reaches is read on its own. The walk arranges the fixture and
holds the state's `verify:` rows on the answer of its `observe:` request. A state with no `fixture:`
stays `unreached-data-state`, and so does one with `fixture: none`, which no walk can arrange.

## How a walk uses it

A walk step whose route or case carries a `moves:` row naming a target state is followed by a
read-back. The walk sends the target state's `observe:` request, with the path bound from the
walk's captures and fixtures. It runs the target's `verify:` rows on the answer. When they fail,
the walk runs each sibling's rows on the same answer and names the first sibling that holds. When
none holds, it says that no state of the lifecycle holds.

Two sibling states must be told apart. When both observe the same endpoint, some `verify:` row of
one and some row of the other must check the same field, by the same check name and the same
`path=` or `subject=`, and expect different values. Otherwise doctor raises `indistinct-states`.
States that observe different endpoints are treated as told apart.

## Minimal example

```markdown
## Data states

### Bill issued

- of: bill
- observe: [read the bill](#get-bill)
- verify: json_path(path="$.status", equals="issued")

### Bill paid

- of: bill
- observe: [read the bill](#get-bill)
- verify: json_path(path="$.status", equals="paid")
```

The pay route then carries
`- moves: [Bill issued](#bill-issued) to [Bill paid](#bill-paid)`.

## Doctor codes it can trip

`data-state-shape` on an `of:` that is not one word or an `observe:` that does not link exactly
one endpoint, `indistinct-states` on two siblings no check tells apart, `misplaced-section` on
any page that is not a server or command-line page, `missing-required-bullet` on a state without
`of:`, `observe:` or `verify:`, and `unresolved-relation` on a broken `fixture:` link, plus the
structural codes every section type can trip. See [../doctor-codes.md](../doctor-codes.md).
