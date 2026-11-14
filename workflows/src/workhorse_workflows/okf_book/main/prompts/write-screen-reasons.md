Write why the screens below of the `{{ service }}` book behave as they do. The book's Python
already says what each screen shows. You add the reasons, as decision files.

The book is the package `{{ package }}/` under the book root, `{{ book_root }}`. The app's source
is `{{ source_root }}/`, in the repository `{{ app_root }}`.

The format is the `ostler-book` skill. Load it first and read what it says of `decisions/` and
of `QUESTIONS.md`:
{{ skill_command("ostler-book") }}

Read the decisions the book already holds under `{{ module_dir }}/decisions/`. Write yours in
their form and their tone.

Your screens:

{% for screen in screens -%}
- {{ screen }}
{% endfor %}

`python -m ostler.book explain {{ module }} <Screen>`, run from the book root, prints everything
the book says of one.

For each screen, find what was written down about why it is so:

- the history of each file its `source` names, read in `{{ app_root }}` with
  `git log --follow --format='%h %s%n%b' -- <file>`, and the stories or plans those commits add
  or cite;
- the folders of `{{ app_root }}` and of `{{ book_root }}` that hold the project's own account
  of its intent, such as its docs, its decisions, its epics and its stories;
- the comments and the texts in the screen's own code.

The app's tests are no part of this, so read none of them.

Then write one decision file per reason under `{{ module_dir }}/decisions/`:

- Every screen gets the reason it exists: who opens it, for which job, and what would be missing
  without it.
- Beyond that, write one reason per behaviour a reader would otherwise have to guess the reason
  of: who may open the screen and who is sent away, what one kind of account sees and another
  does not, what the screen refuses.
- A reason explains something a user meets on the screen. Why the code is built one way and not
  another, such as which call it makes or how it keeps its state, is no decision.
- The prose says why and never how. It holds no label, field, address or step. It names a screen
  by its class name and stops there, because the Python holds the specifics.
- `story:` holds the id of the story or the epic the reason comes from, or `none`.
- `sources:` names where the reason is written, in the pointer forms the skill gives. A commit
  that only moved or merged a file is no source: name the commit or the file that states the
  reason.

A behaviour whose reason nothing written gives gets no decision. It gets one line in
`{{ module_dir }}/QUESTIONS.md`: the screen's class name, a colon, and the question its owner
would answer in a sentence.

Write only under `{{ module_dir }}/decisions/` and in `{{ module_dir }}/QUESTIONS.md`. Do not
commit.

You are done when this command, run from the book root, prints no finding that names one of your
decisions or one of your questions:

```
python -m ostler.book check {{ module }} --app {{ app_root }}
```

Reply with one JSON object and nothing else.

{{ result_schema }}
