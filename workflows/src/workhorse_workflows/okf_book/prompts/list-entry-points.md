List the entry points of the `{{ kind }}` surface of the service `{{ service }}`.

The surface starts at `{{ entry }}`. Read that file and the files it imports, and nothing
else:

{% for file in files %}
- `{{ file }}`
{% endfor %}
{% if files_left_out %}

{{ files_left_out }} more imported files are past this turn's budget. Do not read them.
{% endif %}

An entry point is a place a user starts:

- **cli**: every command the program accepts, one per subcommand.
- **http**: every endpoint the server routes, one per method and path.
- **web** and **mobile**: the home screen only, the one the app shows first. Every other
  screen is reached from it and is documented later.

{% if slugs %}
The book already documents these entry points of this surface. When an entry point is one
of them, reuse its slug. Never give an entry point the slug of anything else the book has:

{% for slug in slugs %}
- `{{ slug }}`
{% endfor %}
{% if slugs_left_out %}

{{ slugs_left_out }} more entry points are past this turn's budget.
{% endif %}
{% endif %}

Give each entry point a slug of lowercase words joined by hyphens, and a short title a
user would recognise. An endpoint's slug names its method and path, like `get-widgets`.

Reply with only this JSON object:

```json
{
  "entry_points": [
    {"slug": "init", "title": "Create a ledger"}
  ]
}
```
