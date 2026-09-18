"""The `driver:` vocabulary of `docs/okf-runbook.md` §4.1, as a value code can be held to.

The doc stays authoritative for authors — §4.1's table cell is what someone writing a
`runbook` page reads before typing `driver: http`. This module exists for the readers that
are code, not people: every table in this package that is keyed by driver either names all
seven values or, where it deliberately doesn't, declares by value the reason it omits each
one. A test joins this tuple back to §4.1's own table bidirectionally, so neither side can
drift out from under the other — a value added to one and not the other is a defect this
module exists to make visible rather than a silent gap.
"""

from __future__ import annotations

#: §4.1's own order.
DRIVERS: tuple[str, ...] = ("web", "mobile", "http", "cli", "artifact", "iac", "none")
