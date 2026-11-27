# okf-book catch-up — update one book to the app's HEAD and the book format

Bring the `{{ service }}` book up to date. The book is the package `{{ package }}/`
under the book root, `{{ book_root }}`. Write only there. The app's source is in `{{ app_root }}`.
Its tests, test doubles and fixtures are no part of the book, so read none of them.

The format is the `ostler-book` skill. Load it first and follow its section on backfilling
commits:
{{ skill_command("ostler-book") }}
{% if stack_copy %}

The app already runs on this machine, as the stack copy `{{ stack_copy }}`. Stop nothing. The
book writes each host as `ostler:` with no copy name after it, and every command that reaches
the app takes `--copy {{ stack_copy }}`. A host the book reaches that the copy does not publish
is one the book's own stack leaves out: name it in `reaches:` in `{{ package }}/ops/stack.yml`,
then `ostler env up {{ service }} --copy {{ stack_copy }}` adds it to the copy.
{% endif %}

{% if app_changed %}
The book was last verified against the commit below, and the app has changed since. Each
element listed is one whose source changed. Each file listed as unnamed is a file the book
names nowhere. Reread each, and bring the book to what the diff says:

- Update each changed element, and the journeys and cells that rely on it.
- A publish the diff adds or removes (a bus `Publish`, `PutEvents` or `publish`) changes what
  the action emits. Rewording `does` is not enough. Declare the event, list it in the service's
  `events`, and set `emits` and `announces` on the action, as the `ostler-book` skill's grpc
  reference says. The environment the play runs in must name a delivery that taps the event.
  Without one, the played report lists the event under "events with no tap" and no play sees it.
- Add the route, screen, interaction or record that each unnamed file holds, with that file in
  its `source`. A file whose code runs when a route, screen or heard event of the book is served
  is named in the `source` of each element that runs it, however deep in the call chain and
  however pure, such as arithmetic, parsing or a query file. Only a file no served request runs
  goes in the service's `App(ignore=...)`: build and tool configuration, generated code whose
  source is named, command-line tools that are not the service, test support.
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
{% endif %}
{% if findings %}

The book is behind the current book format. The check of this book reports these findings.
Each one names what the current format asks. State it from what the app's code shows, and
never invent a statement to silence a finding. Keep every behaviour the book states.
{% for section in findings %}

`{{ section.module }}`, {{ section.count }} findings:
{% for line in section.lines %}
- {{ line }}
{% endfor %}
{% if section.unlisted %}
- {{ section.unlisted }} more are not listed here: run the check below to read them all.
{% endif %}
{% endfor %}
{% endif %}
{% if notes %}

The check also reports notes. A note does not fail the check, and each one is work: the current
format asks for what it names. The notes below are this batch's share of them, each kind with
its count and its elements:
{% for group in notes %}

{{ group.kind }}: {{ group.count }} notes
{% for element in group.elements %}
- {{ element }}
{% endfor %}
{% endfor %}

For each note, do one of two things. State what it asks, from what the app's code shows. Or
decline it, with one line in `declined` saying why it does not apply to that element, spelled
`<Element>: <reason>`, for example a screen the app truly never links to. When a whole kind of
note is not about the format this book is moving onto, one line `<kind>: <reason>` declines
every note of that kind. A note left with neither is unfinished work, and the run sends you
another lap with the notes that remain.

State each link the app has, even though the play then checks each landing: a landing the play
can check is the point. Play the journeys that land on what you stated, and correct what does
not land{% if stack_copy %}:

```
python -m ostler.book run <module> --only <Interaction> --copy {{ stack_copy }} --out <a scratch folder>
python -m ostler.book run <module> --partial --journey "<title>" --copy {{ stack_copy }} --out <a scratch folder>
```
{% else %}, with `python -m ostler.book run <module> --only <Interaction>` or
`python -m ostler.book run <module> --partial --journey "<title>"`.
{% endif %}

Never mark a screen `first` to silence a note when the app reaches it by a link.
{% endif %}
{% if batch %}

This batch is {{ batch.size }} items. Do exactly these. For each one, state what it asks from the
app's code, or decline it with a reason in `declined`. Play what you stated, then reply. Do not start
on any note that is not listed here: the run hands out the next ones when this batch is committed.
The run records what you touched outside this list. The run writes each line of `declined` into the
book's `DECLINED.md`, so do not edit that file.
{% endif %}
{% if format %}

The book format changed since this book was last judged against it. For each change, apply it
wherever this book uses the old form, following the current `ostler-book` skill, or say why it
does not apply to this book. Keep every behaviour the book states. The changes, oldest first:

{% for commit in format.commits %}
- `{{ commit.short }}` {{ commit.subject }}
{% endfor %}

Their diff:

```diff
{{ format.diff }}
```

Name each change in `format`, one line each, spelled `<short sha> applied: <what you changed>` or
`<short sha> not applicable: <why>`. The run plays only the calls and journeys your edits to the
book select, so a form left in the old shape fails there.
{% endif %}
{% if gate %}

The last lap ended on this:

{{ gate }}
{% endif %}

Name each endpoint or interaction you add in `added`, spelled as its class.{% if app_changed %} The run plays the
journeys of the changed elements and of those you name, so a name left out is a route that goes
unplayed.{% endif %} Name each pattern you added to `App(ignore=...)` in `ignored`, as written there.

You are done when, for each module below, `check` exits 0{% if notes %}, every note listed above is stated or declined,{% endif %} and `stale` prints nothing under
`## Changed files no element names`, `## Changed functions no element names` and
`## Pointers to files that no longer exist`, run from the app root `{{ app_root }}` or from the book root with `--app`. `## Stale elements` stays
listed until the run stamps the book, so it is no sign of work left:

```
{% for module in modules %}
python -m ostler.book check {{ module }} --app {{ app_root }}
python -m ostler.book stale {{ module }} --app {{ app_root }}
{% endfor %}
```

Update the book yourself. A subagent may answer a narrow question about the app's source, and
never writes or plays a part of the book: each one loads the skill, the book and the source again,
and each of its waits on a play rebuilds that context.

{% if stack_copy and app_changed %}
Before you reply, play the journeys of the endpoints and interactions among the changed elements
and of those you added, with their names, comma separated, after `--only`, and repair the book
until it reads 0 fail:

```
python -m ostler.book run <module> --only <names> --copy {{ stack_copy }} --out <a scratch folder>
```

A run that fails names the cell the app answered differently. Decide, from the source, whether
the book or the app is wrong. A wrong book gets fixed. A wrong app gets an entry in the book's
`DISAGREEMENTS.md` and the cell keeps what the source intends. A cell whose intent no source
settles gets an entry in `UNDERSPECIFIED.md`. A run that exits 3 could not judge the environment.
Do not repair the book for it. Say so in `blocked`.

{% endif %}
The run stamps the book itself, so do not run `verified`. Do not commit. Reply with one JSON
object and nothing else.

{{ result_schema }}
