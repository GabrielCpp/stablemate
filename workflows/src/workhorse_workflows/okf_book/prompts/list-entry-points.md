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

{% if pages %}
The book already has these pages. When an entry point is one of them, reuse its slug:

{% for page in pages %}
- `{{ page }}`
{% endfor %}
{% if pages_left_out %}

{{ pages_left_out }} more pages are past this turn's budget.
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
