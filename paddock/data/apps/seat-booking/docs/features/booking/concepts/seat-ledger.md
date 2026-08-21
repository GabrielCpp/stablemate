---
type: concept
slug: seat-ledger
title: Seat ledger
---
# Seat ledger

- code: app/store.py::Store
- code: compose.yml
- extends:

The ledger is the whole of the service's state: one JSON file holding every
[seat](seat.md) in the showing with its state, its version, its current hold and its booking. It is
read on every request rather than cached, and written atomically. Both properties are load-bearing
rather than tidy: a store that answers out of the memory of the process that wrote it cannot tell a
commit from a cache, and a torn write would surface as a lost booking blamed on the wrong rule.

It is the durable half of [the seat booking API](../http/seat-booking-api.md); the transitions that
mutate it are [the seat's methods](seat.md#methods), and the page reads it through the same seat map.
Durability is half this module and half `compose.yml`, which is why the node cites both: the file is
written atomically to a path that only survives a restart because the service is deployed with that
path on a volume. A ledger written correctly into a container's own filesystem loses every booking
at the next restart, and the defect would look like a store bug from every surface that reads it.

## Methods

### read

- sig: `read() -> dict`
- abstract: the current ledger, completed from the empty showing so an absent seat reads as free.
- verify: count(subject="seats", equals=12)
- verify: persists(subject="seat A1 booking")
- does: returns every seat in the showing, whether or not the file mentions it.
- does: reads the file on each call, so a booking written by another process is visible to the next
  request rather than at the next restart.
- parent: [Seat ledger](#seat-ledger)

### write

- sig: `write(ledger: dict) -> None`
- abstract: replaces the ledger atomically.
- verify: keys_unchanged(subject="seats")
- verify: persists(subject="seat A1 booking")
- does: writes a temporary file and renames it over the ledger, so a reader never observes half a
  showing.
- persistence: a booking is on disk before the response that announces it, and survives a restart of
  the service.
- parent: [Seat ledger](#seat-ledger)
