Add one skeleton screen per entry file below to the `{{ service }}` book. A skeleton says what a
user sees on the screen once it has loaded. What the screen does is written later, by the book's
owner.

The book is the package `{{ package }}/` under the book root, `{{ book_root }}`. The app's source
is `{{ source_root }}/`.

{% if gate %}The last attempt at these ended on this:

{{ gate }}

{% endif %}The format is the `ostler-book` skill. Load it first, then read its screens reference whole:
{{ skill_command("ostler-book") }}

Read two screens the book already has, a small one and a large one, and the file that registers
the book's screens. Write yours the same way, one module per entry file, beside them.

Your entry files:

{% for file in files -%}
- {{ file }}
{% endfor %}

For each entry file:

1. Read it, and every file it imports that belongs to this screen alone. Stop at the parts the
   whole app shares, such as its navigation, its theme and its translations library.
2. Write one `Screen` class for it:
   - `route` is the address the app declares for it, with `{name}` for each parameter.
   - `name` is the screen's title as the app shows it.
   - `first = True` when a person can open it directly, by its address or at launch. How a user gets
     there from another screen is the `leads_to` of the interaction that follows the link, the
     redirect or the press: state it on that interaction, not on the screen.
   - `source` names the entry file first, then each file you read that belongs to this screen
     alone, spelled the way the book's other pointers are.
   - One component per thing a user sees when the screen has loaded with ordinary data: each
     heading, field, button, link, tab and notice. Its label holds the text in every language the
     book's service declares, each copied from the app's own texts. Its last argument says what
     the thing is for, in a few plain words.
3. A dialog or a tab the screen opens is a `Screen` class of its own in the same module. It has
   no `route`. It states `inside` as the screen that hosts it and `shown_in` as the phase of that
   screen in which it is shown.
4. Register each class where the book registers its screens.

A component that a screen the book already has also shows is imported from that screen's module.
It is written once.

A text you cannot find in every language stays out of the screen and goes in `left`. An entry
file a user sees nothing of, such as a redirect, gets no screen and goes in `left` with the
reason.

Write only screen modules and the file that registers them. The app keeps running untouched. Do
not commit.

You are done when both commands below, run from the book root, say this: `check` prints no
finding that names one of your classes, and `missing` lists each of your entry files under
`## What the book names`, or you named the file in `left`:

```
python -m ostler.book check {{ module }} --app {{ app_root }}
python -m ostler.book missing {{ module }} --app {{ app_root }}
```

Reply with one JSON object and nothing else.

{{ result_schema }}
