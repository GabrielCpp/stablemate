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

- Every promise and refusal above is stated on some page, as a claim the product can be
  asked to demonstrate. None is missing, and the pages claim nothing the contracts do not.
- Each node is written to the spec depth its node type asks for. A one-line stub fails.
- Every interactive control has a role, an accessible name and a keyboard contract. Every
  structural component has a placement.
- A reader holding only the book understands what the product does here and why, and can
  drive it without the source.

Name each problem as the fix it needs, with the page and the node it is on.

Reply with only this JSON object:

```json
{"passed": false, "problems": ["docs/features/tally/cli/add.md#add: the refusal of a non-numeric amount is missing."]}
```
