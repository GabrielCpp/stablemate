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

{% for claim in contract.claims %}
{{ claim.id }}. {{ claim.text }}{% if claim.symbol %} (`{{ contract.file }}::{{ claim.symbol }}`){% endif %}

{% endfor %}
{% endfor %}

A page passes when every one of these holds:

{% include "aggregate/prompts/_bar.md" %}

Go through the numbered claims in order, and account for every one. For each claim, find the
node that states it and read that node's `verify:`. Reply with one finding per claim:

- `claim` is the claim's number.
- `node` is the page and anchor of the node that states it. Leave it empty when no page states
  the claim.
- `problem` is what is wrong with how that node states or checks the claim, as the fix it needs.
  Leave it empty when the claim is stated and its check holds.

Then read every page again, and name each problem no claim covers in `problems`, with the page
and the node it is on. The pages pass when every claim has a node and no problem is named.

Reply with only this JSON object:

```json
{"claims": [{"claim": 1, "node": "docs/features/tally/cli/add.md#add", "problem": ""}, {"claim": 2, "node": "", "problem": ""}], "problems": ["docs/features/tally/cli/add.md#add: the example shows an exit code the page never states."]}
```
