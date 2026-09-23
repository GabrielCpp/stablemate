Write the operations pages of the service `{{ service }}`'s book, under `{{ folder }}`.

Load the skill and follow it: {{ skill_load_ref("ostler-okf", skill_dir() + "/ostler-okf/SKILL.md") }}

The operations pages say how to bring the stack up, where it runs, and what data it starts
with: a `runbook` of ordered `step`s, each `environment` it runs in, and each `fixture` it
seeds. Write them from the contracts of the files that build, configure and seed the stack.
A reader holding only the book must bring the stack up from the runbook alone. A program the
user runs directly, with no server to start, still gets a runbook: how to install it and
run it. Scaffold each page with `ostler scaffold`, and link each one from a page
`{{ folder }}/entries.md` already reaches, such as an entry point's page. Code writes the
entries page, and your edits to it are put back. A new page nothing reachable links to is
deleted and costs you this turn.

{% if pages %}
The book's pages already written:

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
The stories that link to these pages. Take the business meaning from them, not the
behaviour, which the contracts own:

{% for story in stories %}
- `{{ story }}`
{% endfor %}

{% endif %}
{% if problems %}
Your last turn on these pages was refused. Fix each of these:

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
put back. Yours are the operations pages and the pages you create. On any other page, only add lines, such as a link. Any other
change to it is put back. Run `ostler fmt` on each page you wrote. Then run `{{ check }}` as it is,
from any directory. It checks your pages, edited or not, and every other book page you changed or created. Run it once
before you edit to see what your pages already owe. It prints every problem the check
after your turn will charge you with, and each one costs you this turn. Fix them all and run it again, as often as
you need, until it passes. Your runs share one budget of output. Once it is spent, a run prints how many problems
remain, and after that nothing, so read its exit code: 0 passes. Its verdict is the one that counts. `ostler doctor` also reports stale
citations, which the commit restamps, and unreachable pages outside your job, which are not yours.
Neither is charged to you. Then reply. Do not commit.

Reply with only this JSON object:

```json
{"summary": "Wrote the add command and its three invocations."}
```
