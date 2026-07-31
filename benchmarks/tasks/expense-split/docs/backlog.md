# Expense split backlog

Benchmark worklist for the workload run. The app settles shared expenses inside a small
group — a trip, a shared flat — through an HTTP API. One surface, five bullets: enough
scope that the stories form a queue with real dependencies in it, which is the property
this spec exists to exercise.

Surfaces this app ships:

- **api** — Go service, the only surface, and the only writer of stored data

Bullets are user-observable behavior, not implementation tasks. Every bullet is in scope
for decomposition and none may be dropped.

## Groups and the people in them

- [group-create] A person starts a group for a shared cost and gives it a name.
- [group-members] A person adds the other people sharing the cost to a group, and sees who is in it.

## Recording what was spent

- [expense-record] A person records that someone paid an amount for the group, with a short description of what it was for.
- [expense-list] A person sees every expense recorded against a group, newest first, with who paid and how much.

## Settling up

- [balance-settle] A person sees, for each member of the group, whether they are owed money or owe it, and the amounts add up to zero across the group.
