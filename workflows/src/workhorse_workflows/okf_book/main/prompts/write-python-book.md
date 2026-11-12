Write the Python book for this repository's `{{ service }}` service, reached by: {{ kind }}.

The book is the package `{{ package }}/` under the repository root, `{{ repo_root }}`. Write only
there. The app's source is the repository's `{{ source_folder }}/`. Its tests, test doubles and
fixtures are no part of the book, so read none of them.

The format is the `ostler-book` skill. Load it first, then open the reference it names for each
of those surfaces, and hold the book to its bar:
{{ skill_command("ostler-book") }}
{% if kinds | length > 1 %}

The service is reached by more than one surface, so the book is one shared model under
`{{ package }}/model/` and one service per surface, each at `{{ package }}/<surface>/service.py`
with its own surface, journeys and `index.tsv`. A record or a rule lives once, in the model.
{% endif %}

`services/farrier/` is a finished book for a command-line tool. Read it for the shape of each
file, and take nothing of farrier's own behaviour into this book.

Some of the book may already be there. Keep what is right, fix what is wrong, and add what is
missing. A book that turns out shaped wrong for the app gets restructured: move the model,
split a matrix or merge two fixtures where that makes the app easier to read. The first
version of a book is never the final one.
{% if gate %}

The last lap ended on this:

{{ gate }}
{% endif %}

You are done when every `check` and `run` below exits 0, from the repository root, and each
`index` has rewritten its `index.tsv`:

```
{% for module in modules %}
python -m ostler.book check {{ module }}
python -m ostler.book run {{ module }}
python -m ostler.book index {{ module }}
{% endfor %}
```

A run that fails names the cell the app answered differently. Decide, from the source, whether
the book or the app is wrong. A wrong book gets fixed. A wrong app gets an entry in the book's
`DISAGREEMENTS.md` and the cell keeps what the source intends. A cell whose intent no source
settles gets an entry in `UNDERSPECIFIED.md`.

Do not commit. Reply with one JSON object and nothing else. `done` says what the book now
covers. `blocked` says, only when you could not finish, what an operator must decide or fix:

```json
{"done": "", "blocked": ""}
```
