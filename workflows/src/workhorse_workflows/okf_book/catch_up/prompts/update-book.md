# okf-book catch-up — update one book to the app's HEAD

Bring the `{{ service }}` book up to date with the app. The book is the package `{{ package }}/`
under the book root, `{{ book_root }}`. Write only there. The app's source is in `{{ app_root }}`.
Its tests, test doubles and fixtures are no part of the book, so read none of them.

The format is the `ostler-book` skill. Load it first and follow its section on backfilling
commits:
{{ skill_command("ostler-book") }}
{% if stack_copy %}

The app already runs on this machine, as the stack copy `{{ stack_copy }}`. Start nothing and
stop nothing. The book writes each host as `ostler:` with no copy name after it, and every
command that reaches the app takes `--copy {{ stack_copy }}`.
{% endif %}

The book was last verified against the commit below, and the app has changed since. Each
element listed is one whose source changed. Each file listed as unnamed is a file the book
names nowhere. Reread each, and bring the book to what the diff says:

- Update each changed element, and the journeys and cells that rely on it.
- Add the route, screen, interaction or record that each unnamed file holds, with that file in
  its `source`. A file that holds no behaviour a user reaches goes in the service's
  `App(ignore=...)` instead.
- Write the decisions the change settles, and the entries of `DISAGREEMENTS.md` where the app
  breaks what the book intends. An entry in `UNDERSPECIFIED.md` is for a cell no source settles.
- A pointer to a file that no longer exists is fixed or dropped with the element it belongs to.

{% for section in sections %}
## `{{ section.module }}`, verified at `{{ section.verified }}`

Changed elements:
{% for element in section.elements %}
- `{{ element.name }}`{% if element.files %}: {{ element.files | join(", ") }}{% endif %}

{% else %}
- none
{% endfor %}

Files no element names:
{% for file in section.new_files %}
- `{{ file }}`
{% else %}
- none
{% endfor %}
{% if section.gone %}

Pointers to files that no longer exist:
{% for pointer in section.gone %}
- {{ pointer }}
{% endfor %}
{% endif %}

The diff of those files since `{{ section.verified }}`:

```diff
{{ section.diff }}
```
{% endfor %}
{% if gate %}

The last lap ended on this:

{{ gate }}
{% endif %}

Name each endpoint or interaction you add in `added`, spelled as its class. The run plays the
journeys of the changed elements and of those you name, so a name left out is a route that goes
unplayed.

You are done when, for each module below, `check` exits 0 and `stale` prints nothing under
`## Changed files no element names`, `## Changed functions no element names` and
`## Pointers to files that no longer exist`, from the book root. `## Stale elements` stays
listed until the run stamps the book, so it is no sign of work left:

```
{% for module in modules %}
python -m ostler.book check {{ module }} --app {{ app_root }}
python -m ostler.book stale {{ module }} --app {{ app_root }}
{% endfor %}
```

The run stamps the book itself, so do not run `verified`. Do not commit. Reply with one JSON
object and nothing else.

{{ result_schema }}
