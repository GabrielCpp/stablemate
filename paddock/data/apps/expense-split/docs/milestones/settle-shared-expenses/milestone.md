---
type: milestone
title: Settle shared expenses
status: approved
---

# Settle shared expenses

## Outcome

A small group sharing costs, a trip or a shared flat, records who paid what and sees at
any moment who is owed money and who owes it. Today that lives in a chat thread and a
spreadsheet nobody trusts. After this release one HTTP API holds the group, its members,
its expenses and the balances that follow from them.

The product is one api and nothing else. The release matters to the benchmark because its
five journeys form a queue with real dependencies: a balance needs expenses, an expense
needs members, a member needs a group. That ordering is the property this workload exists
to exercise.

## Release Boundary

This is one milestone with one gate: the api answers all five journeys at
`http://localhost:18080`. Groups, members, expenses and balances must coexist at cutover,
because a balance over a group with no members is meaningless and a group that cannot
hold an expense settles nothing.

The first story proves one end-to-end path: a group is created with a name and read back.
Later stories widen that path through members, expenses and the settlement view.

## User Journeys

### Start a group with a name

- services: api

A person starts a group for a shared cost and gives it a name. The api creates the group,
answers with its identity, and the group can be read back by that identity. A group with
no name, or an empty one, is refused with a reason.

### Add members and see who is in the group

- services: api

A person adds the other people sharing the cost to a group, and sees who is in it. Each
member is added by name to an existing group, and reading the group lists every member in
the order they were added. Adding a member to a group that does not exist is refused, and
so is a member with no name.

### Record that someone paid for the group

- services: api

A person records that someone paid an amount for the group, with a short description of
what it was for. The payer must be a member of the group, the amount must be positive, and
the description must not be empty. The api answers with the recorded expense, including
when it was recorded.

### See every expense, newest first

- services: api

A person sees every expense recorded against a group, newest first, with who paid and how
much. A group with no expenses answers an empty list rather than an error.

### See who owes and who is owed

- services: api

A person sees, for each member of the group, whether they are owed money or owe it. Each
member's balance is what they paid minus their equal share of every expense, and the
amounts add up to zero across the group. A group with no expenses shows every member at
zero.

## Architecture Decisions

- The api is the only surface and the only writer of stored data. There is no web page,
  mobile screen or sign-in, so a round that implements the five journeys on the api has
  implemented them completely.
- Every expense is split equally among all current members of the group at the time the
  balance is read. Weighted splits are out of scope.
- Amounts are integer minor units, cents, so balances sum to exactly zero. A remainder from
  an equal split is assigned so that the group still sums to zero and the assignment is
  deterministic.
- Stored data survives the request that wrote it: the api keeps its data in a durable store
  of the implementing lane's choice, and reading the store at construction is code review's
  obligation rather than QA's, because QA cannot cross a process boundary.

## Constraints

- The api is a Go service.
- The api listens on port 18080, not the Go default 8080. The benchmark owns 18080 to
  18099 and nothing else. A run here once left the port unsaid, and its QA readiness probe
  on 8080 was answered by an unrelated service that already held the port.
- The api serves `GET /healthz`, which answers 200 once the api can serve requests, and QA
  waits on that route before it runs anything.
- QA drives the api at `http://localhost:18080`.

## Acceptance

The milestone is complete when, against a freshly started api at `http://localhost:18080`:

- `GET /healthz` answers 200.
- A group is created with a name, answers its identity, and is read back with that name.
- Two members added to a group are both listed when the group is read, in insertion order.
- An expense recorded by a member with a positive amount and a description is answered
  back and appears first in the group's expense list.
- The expense list of a group is ordered newest first.
- With two members and one expense of 1000 paid by the first, the balances read 500 and
  -500, and they sum to zero.
- A group with no name, a member with no name, an expense by a non-member, and an expense
  with a non-positive amount are each refused with a reason.

## Non-Goals

- No web page, mobile screen or sign-in.
- No weighted or percentage splits, no per-expense participant subsets.
- No currencies, conversion or rounding to display units beyond integer minor units.
- No recording of settlements, so balances are never cleared.
- No editing or deleting of groups, members or expenses.
