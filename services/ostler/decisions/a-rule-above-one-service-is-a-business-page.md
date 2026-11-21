story: none
date: 2026-11-21
elements: SearchBook, ListBusinessPages
sources: ostler/ostler/book/business.py, ostler/ostler/book/index.py::cmd_search_book

A rule that sits above any one service has no decision to live in, because a decision must name elements of one
service's book. The product's own words, a constraint no story may break and the place where the truth for a
calculation lives go in `business/<slug>.md` beside `services/`. A page has a `date:` line, an optional `sources:`
line naming who said it or where it is written, a blank line, then prose whose first line is its statement. It names
no story and no element.

`book search` reads the business pages in every case, with a service named or not, and prints their hits under the
heading `== business` in the same lines as a decision's. The kind `business` shows only them and every other kind
leaves them out. A book with no `business/` folder prints exactly what it printed before.

`book business` lists one line for each page: the slug, the date and the statement. With `--check` it prints each page
with no `date:` line or an empty body and exits 1, else exits 0. It takes no service because a page belongs to none.
The sandbox's small book holds no business page, so the book sees the command exit 0 and no more.
