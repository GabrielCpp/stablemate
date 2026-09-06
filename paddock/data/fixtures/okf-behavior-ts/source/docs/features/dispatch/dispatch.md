---
type: concept
slug: dispatch
title: Dispatch a bounded batch
---
# Dispatch a bounded batch

## Methods

### dispatch

- sig: `dispatch(items: string[], sent: string[], limit: number): { status: string; count: number }`
- does: Appends the selected items, in input order, to the supplied sent list.
- returns: For nonempty input, status `sent` and the number of selected items. Selects the first min(limit, items.length) items; a zero limit selects none.
- returns: For empty input and a nonnegative limit, status `empty` and count zero, without changing the sent list.
- raises: A negative limit throws an `Error` with message `limit must be nonnegative` before changing the sent list, including when input is empty. No other input throws.
- code: service.ts::dispatch
