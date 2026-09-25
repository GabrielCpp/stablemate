Write the flows of the service `{{ service }}`'s book, under `{{ folder }}`.

Paths in this prompt are relative to the repository root `{{ root }}`. You run from its `docs/`
directory, and you can read and write only under it. Your shell runs `ostler` and the check
command below, and nothing else.

Load the skill and follow it: {{ skill_load_ref("ostler-okf", skill_dir() + "/ostler-okf/SKILL.md") }}

A flow is an ordered journey a user takes through the product. Every entry point of the book
sits on at least one flow, and every flow can be run end to end. Write the flows that put
each entry point on a journey, from the contracts of the files that reach them, each step
linking the node it drives. Scaffold each flow with `ostler scaffold`, and link each one
from a page `{{ folder }}/entries.md` already reaches, such as an entry point's page. Code
writes the entries page, and your edits to it are put back. A page of yours nothing reachable
links to costs you this turn. A new one is deleted at once, and one the book already had is
deleted after your job.

{% if pages %}
The book's flows already written:

{% for other in pages %}
- `{{ other }}`
{% endfor %}

{% endif %}
The contracts:

{% for contract in contracts %}
### `{{ contract.file }}`

{{ contract.purpose }}

{% for claim in contract.promises %}
- promises: {{ claim.text }}{% if claim.symbol %} (`{{ contract.file }}::{{ claim.symbol }}`){% endif %}{% if claim.verify %} verify: `{{ claim.verify }}`{% endif %}

{% endfor %}
{% for claim in contract.refusals %}
- refuses: {{ claim.text }}{% if claim.symbol %} (`{{ contract.file }}::{{ claim.symbol }}`){% endif %}{% if claim.verify %} verify: `{{ claim.verify }}`{% endif %}

{% endfor %}
{% endfor %}
{% if stories %}
The stories that link to these flows. Take the business meaning from them, not the
behaviour, which the contracts own:

{% for story in stories %}
- `{{ story }}`
{% endfor %}

{% endif %}
{% if problems %}
Your last turn on these flows was refused. Each problem below is one place a rule of the bar
below was broken. Fix it, then fix every other place on your pages that breaks the same
rule, because the next judge reads the whole of every page again:

{% for problem in problems %}
- {{ problem }}
{% endfor %}

{% endif %}
Another turn judges your pages once you reply. It refuses them unless every one of these
holds:

{% include "aggregate/prompts/_bar.md" %}

{% include "aggregate/prompts/_format.md" %}

Give each claim a `verify:` from the checks above. Under
each claim of a `command` or an `invocation`, give a `run:` stating one literal call before
its `verify:`. Give each flow a `fixture:`, or `fixture: none, because ...`. A `cli`, a `server`, a
`concept` or a `format` states no check of its own, so put no `verify:` on the node
itself. Check it through the commands, fields and flows under it or linked from it.

Edit only files under `{{ folder }}`, its entries page aside. Anything you change elsewhere is
put back. Yours are the flow pages and the pages you create. On any other page, only add lines, such as a link. Any other
change to it is put back. Run `ostler fmt` on each page you wrote. Then run `{{ check }}` as it is,
from any directory. It checks your pages, edited or not, and every other book page you changed or created. Run it once
before you edit to see what your pages already owe. It prints every problem the check
after your turn will charge you with, and each one costs you this turn. Fix them all and run it again, as often as
you need, until it passes. Your runs share one budget of output. Once it is spent, a run prints how many problems
remain, and after that nothing, so read its exit code: 0 passes. It proves your claims compile.
It does not run them. A later phase runs each claim against the product, so a check that
cannot see its claim fails there. It cannot read the bar above, so the judge can still refuse
a page it passes.
Hold each page to that bar yourself, and once the check passes, reply. Do not run `ostler doctor`: its stale citations are restamped by the
commit, and its unreachable pages are outside your job. Do not commit.

Reply with only this JSON object:

```json
{"summary": "Wrote the add command and its three invocations."}
```
