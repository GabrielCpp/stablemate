---
type: concept
slug: dispatch
title: Dispatch a bounded batch
---
# Dispatch a bounded batch

## Methods

### dispatch

- sig: `dispatch(array $items, array &$sent, int $limit): array`
- does: Appends the selected items, in input order, to the supplied sent list.
- returns: For nonempty input, status `sent` and the number of selected items. Selects the first min(limit, count(items)) items; a zero limit selects none.
- returns: For empty input and a nonnegative limit, status `empty` and count zero, without changing the sent list.
- raises: A negative limit throws an `InvalidArgumentException` with message `limit must be nonnegative` before changing the sent list, including when input is empty. No other input throws.
- code: service.php::dispatch
