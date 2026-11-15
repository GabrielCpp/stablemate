Write the Python book for the `{{ service }}` service, reached by: {{ kind }}.

The book is the package `{{ package }}/` under the book root, `{{ book_root }}`. Write only
there. The app's source is `{{ source_root }}/`. Its tests, test doubles and fixtures are no part
of the book, so read none of them.

The format is the `ostler-book` skill. Load it first, then open the reference it names for each
of those surfaces, and hold the book to its bar:
{{ skill_command("ostler-book") }}
{% if kinds | length > 1 %}

The service is reached by more than one surface, so the book is one shared model under
`{{ package }}/model/` and one service per surface, each at `{{ package }}/<surface>/service.py`
with its own surface, journeys and `index.tsv`. A record or a rule lives once, in the model.
{% endif %}
{% if "-" in service %}

The service's name holds a hyphen, so no `import` statement can spell the package. Every
module of the book imports its siblings relatively, as `from .model import ...` does, and
`python -m ostler.book` loads the package by the module name below.
{% endif %}
{% if references %}

The book root already holds finished books:
{% for reference in references -%}
- `{{ reference }}/`
{% endfor %}

Read one that is reached the way this service is, for the shape of each file.

A finished book is also the only place this book learns what another service does. Read no
source outside `{{ source_root }}/`. Where this service calls a service whose book is in that
list, this book refers to that service's records by name, as the skill's reference on
neighbours says. Where it calls a service with no book in the list, the reference names the
record by a word.
{% endif %}
{% if stack_copy %}

The app already runs on this machine, as the stack copy `{{ stack_copy }}`. Start nothing and
stop nothing. The book writes each host as `ostler:` with no copy name after it, and every
command that reaches the app takes `--copy {{ stack_copy }}`. `ostler env ls` lists the
services that copy runs.
{% endif %}

Some of the book may already be there. Keep what is right, fix what is wrong, and add what is
missing. A book that turns out shaped wrong for the app gets restructured: move the model,
split a matrix or merge two fixtures where that makes the app easier to read. The first
version of a book is never the final one.
{% if gate %}

The last lap ended on this:

{{ gate }}
{% endif %}

The book answers for every file under `{{ source_root }}/`. The `source` of the element that
describes a file names it: a screen, an interaction, an endpoint or a record. A file that holds
no behaviour a user reaches, such as a test, a generated file or a style sheet, is matched
instead by a pattern in the service's `App(ignore=...)`. A file that holds a page, a route or a
command is never ignored. It gets its element.

You are done when every `check`, `run` and `missing` below exits 0, from the book root, and each
`index` has rewritten its `index.tsv`:

```
{% for module in modules %}
python -m ostler.book check {{ module }}
python -m ostler.book run {{ module }}{% if stack_copy %} --copy {{ stack_copy }}{% endif %}
python -m ostler.book missing {{ module }} --app {{ app_root }}{% if source_folder %} --under {{ source_folder }}{% endif %}
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
