---
type: concept
slug: prices-override-entry-fields
title: Prices override entry fields
---
# Prices override entry fields

`groom/groom/prices.py::_overrides` is the sole parser for a `[models."<id>"]` entry in the
override file, and it is the parser cited by all four of that entry's fields — `input`,
`output`, `cache_read`, `cache_write` — because they are read together, from the same table
entry, in the same pass. There is no alternate parser and no source-defined ranking between
these fields: they are not competing implementations of one concern, they are four distinct
properties of one entry, each fully documented on its own field node.

`input` and `output` are read first and are required — an entry missing either is logged and
skipped entirely, before `cache_read` or `cache_write` are considered. `cache_read` and
`cache_write` are then read as optional overrides on top of the defaults `_rates()` derives
from `input` alone: `cache_read` defaults to `input * 0.1`, `cache_write` to `input * 2.0`, the
same multipliers the built-in table uses. Reading any one field's semantics does not depend on
choosing it over another; the entry documents all four to be complete, not to offer alternatives.

- code: groom/groom/prices.py::_overrides
- rule: read `input` and `output` for the two required rates that gate whether the entry is used
  at all; read `cache_read` and `cache_write` for the two optional rates that default from
  `input` when the override omits them; none is a different implementation or a deprecated
  alternative to another.
- tests: groom/tests/test_prices.py
