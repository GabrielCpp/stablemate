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
- entry: `/`

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
- verify: visible(locator="#seat-map-region")
- role: region
- verify: visible(locator="#seat-map-region")
- name: Seat map
- verify: visible(locator="#seat-map-region")
- placement: width 40-100%, x 0-30%, y 10-100%
- keyboard: reachable by `Tab` from the document start, with no shortcut of its own.
- parent: [Seat map](#seat-map)
- code: app/page.py::render@0a3567061b49

Holds every seat button for the showing and nothing else.

### seat-button

- selector: `button.seat`
- verify: count(subject="seat buttons", equals=12)
- role: button
- verify: visible(locator="#seat-button")
- name: Seat A1
- verify: visible(locator="#seat-button", text="A1")
- keyboard: `Tab` to the seat, `Enter` or `Space` to act on it.
- verify: focusable(locator="#seat-button", activates="Enter")
- parent: [Seat map](#seat-map)
- states: carries the seat's state as `data-state`, one of `free`, `held` or `booked`.
- verify: visible(locator="#seat-button", text="free")
- verify: visible(locator="#seat-button", text="held")
- verify: visible(locator="#seat-button", text="booked")
- states: a seat that is not free is rendered `disabled`, so a sold seat cannot be clicked at all.
- verify: inert(locator="#seat-button")
- code: app/page.py::_seat_button@0a3567061b49
- refs: [seat](../../concepts/seat.md)

Renders one button per seat in the showing — twelve, in three rows of four. Names the button by its
seat id alone, so the name a scenario addresses does not change when the seat does. A seat's `booked`
or `disabled` state is a fact about *this* control, not a second component that exists only to carry
it: `selector:` has to stay a form `ostler vet`'s render census can resolve (`#id`, `tag.class`, or a
role match), and an attribute-value predicate like `[data-state="booked"]` is not one of those forms.
The state a seat is in is also rendered as visible text inside the button (`<span class="state">`),
so `booked` and `held` are checks the book can already make: `visible(locator=..., text=...)` against
the seat's own anchor. `disabled` has no such text, and no check in this book's vocabulary asks
whether an element can be acted on rather than merely seen — that question needs a check of its
own (`actionable`), tracked as a separate piece of work, not invented here. Until it lands this
claim stays a documented, unverified `states:` bullet rather than a `verify:` nobody can satisfy —
deferred, not dropped: defect D7 (`disabled = ""` unconditionally, visually silent) is exactly the
regression this claim exists to catch, and the corpus is blind to it until `actionable` exists.

### free-seat-summary

- selector: `p.summary`
- verify: visible(locator="#free-seat-summary", text="12 of 12 seats free")
- verify: visible(locator="#free-seat-summary", text="11 of 12 seats free")
- role: status
- verify: visible(locator="#free-seat-summary")
- name: none
- verify: visible(locator="#free-seat-summary", text="seats free")
- keyboard: none, because it is announced rather than operated.
- parent: [Seat map](#seat-map)
- code: app/page.py::render@0a3567061b49

States how many of the showing's seats are still free, out of the total. Counts only seats in state
`free`, so a held seat reads as taken while somebody is deciding.
