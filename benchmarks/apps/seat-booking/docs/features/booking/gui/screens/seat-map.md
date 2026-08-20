---
type: screen
slug: seat-map
title: Seat map
---
# Seat map

- route: `/`
- requires:
  - none; the showing is public and the page carries no session.
- params:
  - none
- entry: yes

The only page the product has. It is rendered on the server by
[the page renderer](../../concepts/seat-ledger.md) reading the same
[seat](../../concepts/seat.md) map [GET /api/seats](../../http/seat-booking-api.md#get-seat-map)
returns, so the page and the API cannot disagree about what is free — there is no client state to
drift.

There is no build step and no client framework: the document arrives complete, with a banner, a
labelled seat-map region, one button per seat, and a live summary of how many seats are left. That is
deliberate rather than minimal — it means the accessibility tree a browser reads is the one the
server wrote, and every locator the book names is addressable the moment the page is served.

## Components

### seat-map-region

- selector: `section[role="region"]`
- role: region
- name: Seat map
- placement: width 40-100%, x 0-30%, y 10-100%
- keyboard: reachable by `Tab` from the document start, with no shortcut of its own.
- parent: [Seat map](#seat-map)
- code: app/page.py::render
- does: holds every seat button for the showing and nothing else.
- verify: visible(locator="region:Seat map")

### seat-button

- selector: `button.seat`
- role: button
- name: Seat A1
- keyboard: `Tab` to the seat, `Enter` or `Space` to act on it.
- parent: [Seat map](#seat-map)
- states: carries the seat's state as `data-state`, one of `free`, `held` or `booked`.
- states: a seat that is not free is rendered `disabled`, so a sold seat cannot be clicked at all.
- code: app/page.py::_seat_button
- does: renders one button per seat in the showing — twelve, in three rows of four.
- verify: count(subject="seat buttons", equals=12)
- does: names the button by its seat id alone, so the name a scenario addresses does not change when
  the seat does.
- verify: visible(locator="button:Seat A1", text="A1")
- verify: visible(locator="button:Seat A1", text="free")
- verify: visible(locator="button[data-state='booked'][disabled]")
- refs: [seat](../../concepts/seat.md)

### free-seat-summary

- selector: `p.summary`
- role: status
- name: seats free
- keyboard: none, because it is announced rather than operated.
- parent: [Seat map](#seat-map)
- code: app/page.py::render
- does: states how many of the showing's seats are still free, out of the total.
- verify: visible(locator="status", text="12 of 12 seats free")
- does: counts only seats in state `free`, so a held seat reads as taken while somebody is deciding.
- verify: visible(locator="status", text="11 of 12 seats free")
