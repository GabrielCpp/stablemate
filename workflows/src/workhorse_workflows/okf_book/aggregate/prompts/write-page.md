Write the page `{{ page }}` of the service `{{ service }}`'s book, under `{{ folder }}`.

You have no tools. Everything you need is below, and you reply with the whole text of each
page you write. The workflow writes your pages into the book, canonicalizes their shape and
checks them.

The page describes what the product does, from the contracts of the files that reach it.
Merge them into the page so it reads as the complete, current spec. Keep its frontmatter
`type` and `slug`. Write each child node the contracts call for to the spec depth its node
type asks for. A child node that needs a page of its own goes on a new page under
`{{ folder }}`, with frontmatter `type`, `slug` and `title`, and `{{ page }}` links to it. A new
page nothing reachable links to is deleted and costs you this turn.

You may write `{{ page }}` and new pages. The book's other pages are not yours, and a page of
theirs in your reply is dropped.

{% if bodies %}
The page as it stands:

{% for body in bodies %}
`{{ body.page }}`:

````markdown
{{ body.body }}
````

{% endfor %}
{% endif %}
{% if pages %}
The book's pages of this kind, nearest the root first. Link to them by relative path:

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
````markdown
{{ story }}
````

{% endfor %}
{% endif %}
{% if problems %}
Your last turn on this page was refused. Each problem below is one place a rule was
broken. Fix it, then fix every other place on your pages that breaks the same rule,
because the next check and the next judge read the whole of every page again:

{% for problem in problems %}
- {{ problem }}
{% endfor %}

{% endif %}
{% include "aggregate/prompts/_format.md" %}

Give each claim a `verify:` from the checks above. Under
each claim of a `command`, an `invocation` or a `field`, give a `run:` stating one literal call before
its `verify:`. A `verify:` reads only the call in the `run:` above it: its exit code, its
output streams, which files it creates, removes or leaves unchanged, and what a file it left
holds. A claim about what a call wrote into a file is read by `contents`, or by `json_path`
or `count` with `file=` naming that file. Give each flow a `fixture:`, or `fixture: none, because ...`. A `cli`, a `server`, a
`concept` or a `format` states no check of its own, so put no `verify:` on the node
itself. Check it through the commands, fields and flows under it or linked from it.

Another turn judges your pages once they pass the check. It refuses them unless every one of
these holds:

{% include "aggregate/prompts/_bar.md" %}

Reply with each page you write between two marker lines: `=== page: <repo-relative path> ===`
above it and `=== end ===` below it. Between them goes the page's whole text as it is saved,
frontmatter first. Escape nothing and put no code fence around a page. One line of prose
before the first page may say what you changed:

```text
Wrote the add command and its three invocations.
=== page: {{ page }} ===
---
type: ...
---
...
=== end ===
```
