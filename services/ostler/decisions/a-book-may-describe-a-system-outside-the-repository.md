story: none
date: 2026-11-22
elements: CheckBook
sources: ostler/ostler/book/domain.py::Documentation, ostler/ostler/book/service.py::Service, ostler/ostler/book/check.py::web_faults, ostler/ostler/book/check.py::under_site, ostler/ostler/book/sources.py::is_web, ostler/ostler/book/sources.py::no_code, ostler/ostler/book/cli.py::cmd_stale, ostler/ostler/book/cli.py::cmd_missing, ostler/ostler/book/cli.py::cmd_verified, ostler/ostler/book/cli.py::cmd_affected, ostler/ostler/book/cli.py::load

A book states what a service does so that the service can be operated without reading its code. The product also calls
systems it has no code for, such as a vendor's API. That system is known only from its documentation and from its live
behaviour, and the owner needs its book as much as any other.

Until now a book had to name code. A documentation address in `source` was a blocking finding, and a book with no `app`
made `stale` and `missing` exit 2, which stopped the coder workflow on any story that named the book.

A service now declares where its truth lives in one of two ways, never both. `app=App(...)` is code in the repository and
nothing changes for it. `documentation=Documentation(sites=(...))` is an outside system. `Service` refuses a declaration of
both when it is built and again when `ostler book` loads it, because a test or a tool may assign `app` after the build.
`Documentation` refuses an empty list of sites and a site that is no http or https address.

In a documented book each `source` is a web address, with the usual `::<anchor>` suffix, of the documentation of what the
element states. `check` holds the address to the declared sites: it is good when it starts with one of them, and a pointer
that is no web address or lies under no site is a blocking finding that names the pointer and the sites. An element with no
pointer is the same warning as in any book. A decision's `sources:` entry under a declared site is accepted. A web address
in a book with an `app` or with neither declaration is still blocking, and its message names the declaration to add.

The sites are declared because a pointer can then be held to something with no network. Without them any string that looks
like an address passes, and a pointer to a page of another system passes as well. With them a typo, or a page copied from
the wrong vendor, is a finding the author sees in seconds on any machine.

`check` makes no network call. A page can move or disappear, and the book is proven the way every book is, by playing it
against the live system with `run`. A fetch in `check` would make a seconds-long, offline gate depend on a vendor's uptime.

`stale`, `affected` and `missing` compare code with the book, and there is none. They print `<name> describes an outside
system: no code to compare` and exit 0, so a workflow that asks whether a story touched the book finds nothing stale and
nothing to stamp. `verified` prints `not stamped: <name> describes an outside system` and exits 0, and writes no stamp file.
`run`, `index`, `search` and `explain` read a documented book as any other.

The purpose of a book, operating software without its code, is why such a book exists: the code a book cannot name is no
reason to leave the system without one.

The book of ostler plays `check` in its demo world. The four commands that read a git checkout are not played there, so
their new answer is stated here and in the module docstring of the commands.
