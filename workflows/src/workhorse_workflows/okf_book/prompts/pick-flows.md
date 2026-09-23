Pick the scenarios to run against the product. Each one exercises obligations the book
states.

{% for scenario in scenarios %}
- `{{ scenario.id }}` covers: {% for obligation in scenario.covers %}`{{ obligation }}`{% if not loop.last %}, {% endif %}{% endfor %}

{% endfor %}

{% if written %}
This run wrote these pages and jobs:

{% for subject in written %}
- `{{ subject }}`
{% endfor %}

{% endif %}
Pick every scenario that exercises something this run wrote, and every scenario that puts
an entry point on a journey. When you cannot tell, pick it. An empty list runs them all.

Reply with only this JSON object:

```json
{"ids": ["add-then-list"]}
```
