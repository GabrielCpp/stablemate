---
type: fixture
slug: book-todo-scratch
title: book todo scratch
---
# book todo scratch

- lifetime: scenario

Seeds `book-todo/`, a copy of the todo service book the ostler tests keep: one service `services.api` for a todo list on a loopback HTTP server, with five journeys, a lifecycle matrix for the chore and for the app, and five declared divergences. The directory holds `services/` and the todo server `app.py`, so every `ostler book` verb runs there with `-C book-todo` and no import path set. Its stack starts `app.py` on a loopback port and stops it when the run ends. The book is sound, so `check` reports no findings and a full `run` passes with every answer witnessed.

## Steps

### copy-the-todo-book

- kind: seed
- run: rm -rf book-todo && cp -r ostler/tests/fixtures/book_todo book-todo
