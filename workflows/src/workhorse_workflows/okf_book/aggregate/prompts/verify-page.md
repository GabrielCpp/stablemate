Judge these {{ kind }} pages of the book. Another turn wrote them. You did not.

Load the skill and follow it: {{ skill_load_ref("ostler-okf", skill_dir() + "/ostler-okf/SKILL.md") }}

Each page's whole text is here. Judge them from what is here, and read nothing else. Do not
edit any file.

{% for page in pages %}
<page path="{{ page.page }}">
{{ page.body }}
</page>

{% endfor %}

{% if other_pages %}
The book has these other pages too. A link or a `fixture:` that names one of them is not
missing:

{% for other in other_pages %}
- `{{ other }}`
{% endfor %}
{% if other_pages_left_out %}

{{ other_pages_left_out }} more pages are past this turn's budget.
{% endif %}

{% endif %}
They were written from these contracts:

{% for contract in contracts %}
### `{{ contract.file }}`

{{ contract.purpose }}

{% for claim in contract.promises + contract.refusals %}
- {{ claim.text }}{% if claim.symbol %} (`{{ contract.file }}::{{ claim.symbol }}`){% endif %}

{% endfor %}
{% endfor %}

A page passes when every one of these holds:

{% include "aggregate/prompts/_bar.md" %}

Name each problem as the fix it needs, with the page and the node it is on.

Reply with only this JSON object:

```json
{"passed": false, "problems": ["docs/features/tally/cli/add.md#add: the refusal of a non-numeric amount is missing."]}
```
