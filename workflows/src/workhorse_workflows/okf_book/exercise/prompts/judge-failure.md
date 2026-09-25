A scenario failed against the running product. Say which side is wrong: the app, or the
book.

- Scenario: `{{ scenario }}`
- It covers: {% for obligation in covers %}`{{ obligation }}`{% if not loop.last %}, {% endif %}{% endfor %}

{% if message %}
The run said, one failed check per line before its own message:

```text
{{ message }}
```
{% else %}
The run said nothing.
{% endif %}

The pages the scenario covers are here, each whole. Read only these pages and what the run
said. Do not read the source or the run's report, and do not edit any file.

{% for page in pages %}
<page path="{{ page.page }}">
{{ page.body }}
</page>

{% endfor %}

The book is wrong when it states something no user of the product would expect, when it
contradicts itself, or when its steps cannot reach what it claims. The app is wrong when the
book states a coherent behaviour and the product does something else. Quote the claim the
failure is about, and say what the product did instead.

Reply with only this JSON object:

```json
{"side": "app", "reason": "docs/features/acme/cli/add.md#add says a negative amount is refused with exit code 2. The product accepted it."}
```
