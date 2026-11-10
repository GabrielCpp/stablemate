---
type: concept
slug: service-book
title: A service book
---
# A service book

A service book is one backend service written as a model that ostler can run. It lives in the package `services/<name>/` of a repo and imports `ostler.book` and its own modules, nothing else. The model says what each call does to the state of the service. A run plays the same steps on the model and on the live service and compares what each answers and what each lists afterwards. The [ostler book commands](../book-runtime.md) build it, search it and play it.

The book is made of these parts, each declared once in Python and registered in the `ALL` or `__all__` of its package:

- The model keeps one record type per thing the service stores, a state with one collection per record, the rules the service refuses by with its messages word for word, and the actions a call performs.
- The endpoints give one declaration per route, or per unary gRPC call, with every answer it may give and the shape of each body. Each endpoint carries the model action it performs and points at the source that handles it.
- The lifecycle matrix gives each record a table: its scenes as rows and its actions as columns, so every state a record can be in meets every action that can reach it.
- The fixtures are what a caller sends: a base factory per request and variants that fill one thing in. A fixture learns the id the service assigns when its answer comes back.
- The journeys are stories a user lives through, one class per file, played in order on one long-lived account.
- The health journeys read the standing world every other journey relies on and make one round trip through the core of the product.
- The service declaration names the environments, the stack to start, the refusals shared by every endpoint, the answers a run may not see, the input classes the service accepts and the book refuses, and the source roots the book follows.

Decisions a story settled sit as markdown files under `decisions/` beside the service, each naming the Python elements it explains. The file `index.tsv` beside the service lets `search` answer without importing it.

A book follows the service's source commit by commit. The service declares the source roots it covers and the file that records the commit it was last verified at. `stale` lists what changed since then and `verified` records the new commit once every change is named.

- rule: a service book imports `ostler.book` and its own modules and no other library, so a run needs nothing the book does not declare
- rule: an endpoint, journey, rule or fixture that no `ALL` or `__all__` lists does not exist for ostler, and `check` names it
- rule: an endpoint that no lifecycle matrix places is played in every state of the service
- rule: a service book covers HTTP and gRPC services, and web and mobile surfaces come with a later release
- rule: the book is spec first, so when the service and the book disagree the run reports which one is wrong and a person decides
- code: ostler/ostler/book/service.py::Service@9dc13c88a409
- code: ostler/ostler/book/__init__.py::__all__@3a67e49102c3
- code: ostler/ostler/book/state.py::Axes@0d0318cd1dd0
- code: ostler/ostler/book/journey.py::Journey@b8acde935846
- code: ostler/ostler/book/sources.py::stale@6d1d50984121
- code: ostler/ostler/book/index.py::write@87b10c1277f3
- code: ostler/ostler/book/decisions.py::load@d6263527fc11
- tests: ostler/tests/test_book_todo.py::test_check_finds_nothing_wrong_with_the_book
