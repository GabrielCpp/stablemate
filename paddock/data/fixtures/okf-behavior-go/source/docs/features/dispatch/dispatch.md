---
type: concept
slug: dispatch
title: Dispatch a bounded batch
---
# Dispatch a bounded batch

## Methods

### dispatch

- sig: `Dispatch(items []string, sent *[]string, limit int) (string, int, error)`
- does: Appends the selected items, in input order, to the supplied sent list.
- returns: For nonempty input, status `sent`, the number of selected items, and nil error. Selects the first min(limit, len(items)) items; a zero limit selects none.
- returns: For empty input and a nonnegative limit, status `empty`, count zero, and nil error, without changing the sent list.
- raises: A negative limit returns empty status, count zero, and a non-nil error with message `limit must be nonnegative` before changing the sent list, including when input is empty. It does not panic.
- code: service.go::Dispatch
