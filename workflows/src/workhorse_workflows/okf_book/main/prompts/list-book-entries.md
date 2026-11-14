List the entry files of the `{{ service }}` app that its book does not describe yet.

The app's source is `{{ source_root }}/`. The book is the package `{{ package }}/` under
`{{ book_root }}`. Write nothing.

An entry file holds something a user opens at an address of its own: a page or a screen. A file
that only helps one, such as a shared part, a style, a hook or a helper, is not an entry file.

No element of the book names these files of the app:

{% for file in unnamed -%}
- {{ file }}
{% endfor %}

Find where the app declares its pages: its route table, its navigation graph or its pages
folder. Read it whole. Each page it declares has an entry file. Keep every one that is in the
list above, a page that only redirects included.

Reply with one JSON object and nothing else. `entries` holds each entry file exactly as the list
above spells it. `how` names the file that declares the pages:

{{ result_schema }}
