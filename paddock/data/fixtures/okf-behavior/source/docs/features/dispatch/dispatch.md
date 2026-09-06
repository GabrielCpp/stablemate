---
type: concept
slug: dispatch
title: Dispatch a bounded batch
---
# Dispatch a bounded batch

## Methods

### dispatch

- sig: `dispatch(items: list[str], sent: list[str], limit: int = 2) -> dict[str, object]`
- does: Omitting the limit uses a limit of exactly two items.
- does: Appends the selected items, in input order, to the supplied sent list.
- returns: For nonempty input, an object with status `sent` and count equal to the number of selected items.
- returns: For empty input, an object with status `empty` and count zero, without changing the sent list.
- raises: A negative limit raises `ValueError` with message `limit must be nonnegative` before changing the sent list.
- code: service.py::dispatch
