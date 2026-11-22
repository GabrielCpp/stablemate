story: none
date: 2026-11-21
elements: SearchBook, ListBookPages
sources: ostler/ostler/book/pages.py, ostler/ostler/book/index.py::cmd_search_book

A rule that sits above any one service has no decision to live in, because a decision must name elements of one
service's book. Such a rule goes in a page of one of three books, by how far it reaches. The product book is
`products/<product>/<slug>.md` in the artifacts dir: the product's own words, a constraint no story may break and the place where the
truth for a calculation lives. The team book is `teams/<team>/<slug>.md` in the artifacts dir: how one team builds
across products, as ADRs, RFCs and conventions. The company book is `company/<slug>.md` in the artifacts dir: the rules
every team follows. Agents write product pages. People write team and company pages.

The product is `book.product` in the code repository's `agents.yml`, else the repository's name. With `book.home: repo`
the product book stays `product/<slug>.md` beside `services/`. Started in the artifacts folder, `book pages` lists every
product folder under `products/`, and a product page's search heading is `== product <name>`.

The team is `book.team` in the code repository's `agents.yml`, else in the manifest found from the book root. With no `book.team` the team book is not read, and another
team's folder is never read. A folder that does not exist is skipped without a word.

A page has a `date:` line, an optional `sources:` line naming who said it or where it is written, an optional `status:`
line of free text such as proposed, accepted or superseded by another slug, a blank line, then prose whose first line is
its statement. It names no story and no element.

When two books disagree, the order of authority is company, team, product, service decision, story. A reader that finds
a conflict reports it and picks neither side.

`book search` reads the three levels in every case, with a service named or not. It prints their hits before the
service books', under `== company`, `== team <name>` and `== product` (`== product <name>` when the book has a named product), in that order, in the same lines as a decision's.
The kinds `company`, `team` and `product` each show only that level and every other kind leaves the levels out. A page
whose status starts with superseded is still found, and its hit line ends with `(superseded)`. A book with none of the
folders prints exactly what it printed before.

`book pages` lists one line for each page: the level, the slug, the date, the status when there is one and the
statement. `--level` keeps one level. With `--check` it prints each page with no `date:` line or an empty body and
exits 1, else exits 0. It takes no service because a page belongs to none. The sandbox's small book holds no page, so
the book sees the command exit 0 and no more.
