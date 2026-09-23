Write the page `{{ page }}` of the service `{{ service }}`'s book, under `{{ folder }}`.

Load the skill and follow it: {{ skill_load_ref("ostler-okf", skill_dir() + "/ostler-okf/SKILL.md") }}

The page describes what the product does, from the contracts of the files that reach it.
Merge them into the page so it reads as the complete, current spec. Keep its frontmatter
`type` and `slug`. Scaffold every child node the contracts call for with `ostler
scaffold`, link each one from this page, and write each to the spec depth its node type
asks for. A new page nothing reachable links to is deleted and costs you this turn.

{% if pages %}
The book's pages of this kind, nearest the root first:

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
The stories that link to this page. Take the business meaning from them, not the
behaviour, which the contracts own:

{% for story in stories %}
- `{{ story }}`
{% endfor %}

{% endif %}
{% if problems %}
Your last turn on this page was refused. Fix each of these:

{% for problem in problems %}
- {{ problem }}
{% endfor %}

{% endif %}
Every claim you write compiles into a check run against the product, and a page with a claim
that does not compile is refused. Give each claim a `verify:` from `ostler checks`. Under
each claim of a `command` or an `invocation`, give a `run:` stating one literal call before
its `verify:`. Give each flow a `fixture:`, or `fixture: none, because ...`. A `cli`, a `server`, a
`concept` or a `format` states no check of its own, so put no `verify:` on the node
itself. Check it through the commands, fields and flows under it or linked from it.

Edit only files under `{{ folder }}`, its entries page aside. Anything you change elsewhere is
put back. Yours are `{{ page }}` and the pages you create. On any other page, only add lines, such as a link. Any other
change to it is put back. Run `ostler fmt` on each page you wrote. Then run `{{ check }}` from the
repo root. It checks every book page you changed or created, and prints every problem the check
after your turn will charge you with, and each one costs you this turn. Fix them all and run it again. Run it
at most {{ check_runs }} times, then reply. Do not commit.

Reply with only this JSON object:

```json
{"summary": "Wrote the add command and its three invocations."}
```
