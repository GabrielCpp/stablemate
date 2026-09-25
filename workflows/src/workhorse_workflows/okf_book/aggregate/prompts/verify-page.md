Judge these {{ kind }} pages of the book. Another turn wrote them. You did not.

Load the skill and follow it: {{ skill_load_ref("ostler-okf", skill_dir() + "/ostler-okf/SKILL.md") }}

Each page's whole text is here. Judge them from what is here, and read nothing else. Do not
edit any file.

Every page here passes `ostler doctor`. So each bullet's value has a form the grammar admits,
each `verify:` parses against its check's signature, and each `working-directory:` names a
directory the step can run in. `scenario:` with its colon is such a value: it names the
scenario's own directory. Never name a problem on how a value is spelled. Name one on what a
bullet claims, on a key used for a job the grammar gives another key, or on a check that does
not read its claim.

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
{% if cleared %}
An earlier round judged these nodes sound, and their text has not changed since. Do not name a
problem on any of them. When a node that changed now disagrees with one of them, name the problem
on the node that changed. A claim one of them states counts as stated.

{% for node in cleared %}
- `{{ node }}`
{% endfor %}

{% endif %}
{% if context %}
These contracts say what the rest of the product does. Other pages state their claims, so these
pages owe none of them. Read them to judge what these pages say about the product:

{% for contract in context %}
### `{{ contract.file }}`

{{ contract.purpose }}

{% for claim in contract.promises %}
- {{ claim.text }}
{% endfor %}
{% for claim in contract.refusals %}
- {{ claim.text }}
{% endfor %}
{% endfor %}

{% endif %}
{% if contracts %}
They were written from these contracts, and they owe each numbered claim:

{% for contract in contracts %}
### `{{ contract.file }}`

{{ contract.purpose }}

{% for claim in contract.claims %}
{{ claim.id }}. {{ claim.text }}{% if claim.symbol %} (`{{ contract.file }}::{{ claim.symbol }}`){% endif %}

{% endfor %}
{% endfor %}

{% endif %}
The checks a `verify:` may call, each with its arguments and the defect it excludes:

{{ checks }}

A page passes when every one of these holds:

{% include "aggregate/prompts/_bar.md" %}

{% if contracts %}
Go through the numbered claims in order, and account for every one. For each claim, find the
node that states it and read that node's `verify:`. Reply with one finding per claim:

- `claim` is the claim's number.
- `node` is the page and anchor of the node that states it. Leave it empty when no page states
  the claim.
- `problem` is what is wrong with how that node states or checks the claim, as the fix it needs.
  Leave it empty when the claim is stated and its check holds.
- `expected` is the `verify:` that reads the claim, written as `name(arg=value)` with no
  `verify:` before it. Give it when `problem` is about the claim's check, and leave it empty
  otherwise. When no check above reads the claim, write the check you would need in the same
  form anyway.

Then read every page again, and name each problem no claim covers in `problems`:
{% else %}
These pages owe no numbered claim. Leave `claims` empty. Read every page, and name each problem
on it in `problems`:
{% endif %}

- `node` is the page and anchor of the node the problem is on, or the page alone when the problem
  is on the page as a whole.
- `problem` is what is wrong there, as the fix it needs.
- `expected` is the `verify:` the node needs, written as `name(arg=value)` with no `verify:`
  before it, when the problem is about a check. Leave it empty otherwise.

The pages pass when every claim has a node and no problem is named.

Reply with only this JSON object:

```json
{"claims": [{"claim": 1, "node": "docs/features/acme/cli/add.md#add", "problem": "", "expected": ""}, {"claim": 2, "node": "docs/features/acme/cli/add.md#add", "problem": "the check reads stdout, and the claim is about the file the command writes.", "expected": "json_path(path=\"items[0].name\", equals=\"milk\", file=\"list.json\")"}, {"claim": 3, "node": "", "problem": "", "expected": ""}], "problems": [{"node": "docs/features/acme/cli/add.md#add", "problem": "the example shows an exit code the page never states.", "expected": ""}]}
```
