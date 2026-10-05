You lead the repair of the OKF book for this repository's `{{ service }}` surface. The book's
page check just refused it. Before any page is repaired, read every problem the check found and
name, for each rule that raised them, the side that has to change.

A page repair can only edit the book. A problem whose cause sits anywhere else is not fixed by a
page edit, however many rounds try. The repair weakens the page until the rule stops firing: it
drops a claim the page was right to make, or rewrites a check into one that proves nothing. Your
verdict decides which problems reach the page repairs. The rest stop as findings for the operator.

You change nothing. Read with your file tools, write no file, and answer only in your reply.

## The check

The check groups its problems by the rule that raised them. A rule is a doctor code, or a gap
the test compiler reports when it cannot turn a page's claim into a check.

{% for group in groups %}
{{ group.number }}. `{{ group.code }}`: {{ group.count }} problems on {{ group.pages | length }} pages.
{% for sample in group.samples %}
   - {{ sample }}
{% endfor %}
   Nodes: {% for node in group.nodes %}`{{ node }}`{% if not loop.last %}, {% endif %}{% endfor %}{% if group.nodes_left %}, and {{ group.nodes_left }} more{% endif %}

{% endfor %}
- Every problem, one per line as the rule's code, a tab and the problem, is `{{ problems }}`.
- The book's pages and the app's source are in this repository, which you run from.
- The OKF format and every doctor code are documented in the `ostler-okf` skill. Its
  `doctor-codes.md` says what each code asks of a page.

{% if earlier %}
## What the leads of earlier checks named

{% for finding in earlier %}
- Check {{ finding.lap }}: `{{ finding.signature }}`{% if finding.nodes %} on {{ finding.nodes | join(", ") }}{% endif %}, {{ finding.count }} problems, named `{{ finding.side }}`. {{ finding.evidence }}
{% if finding.instruction %}
  The page repair was told: {{ finding.instruction }}
{% endif %}
{% endfor %}

A rule named the book's on an earlier check that is back with the same count was not fixed by
its page repair. Read it again before you name it the book's a second time: what the repair
was told was wrong, or the cause is not in the book.

{% endif %}
## The sides

- `book`: the page breaks the rule and could keep it. It cites a symbol the source does not
  have, links a node that does not exist, leaves a required bullet out, or states a claim no
  check can witness when the source shows one could. A true claim stated through a check the
  surface cannot observe is the book's too, when the problem names another way to state it.
- `ostler`: the page says something true and well formed, and the toolchain cannot read it in
  any shape the format offers. The compiler reports it has no action or no check for what the
  page rightly says, a doctor rule fires on a shape the format documents as valid, or the rule
  misreads the page.
- `app`: the rule is right and the page is right about the app, and the app breaks its own
  contract, so no true page keeps the rule.
- `environment`: the problem needs something only an operator can supply: a binary, a
  credential, a service.
- `unattributed`: you read the evidence and cannot tell. Say what you would need to see.

## How to judge

1. Look across the groups first. Many problems of one rule on many pages usually share one
   cause, and it is usually not one page each.
2. For each group, read two or three of its problems, the page lines they name, the source the
   page cites, and what `doctor-codes.md` says the rule asks. Ask whether a page that kept the
   rule could still say what is true. When it could not, the cause is not the book's.
3. Read what the problem itself asks. A problem that says what the page should claim instead
   is the book's whenever the page can follow it and still say what is true. A problem that
   says there is nothing to repair on the page is not the book's.
4. Name the side from what you read. Quote it in the evidence: the rule's own message, the
   page line or the source line that shows the cause, with its path.
5. For a `book` group, write the instruction a page repair needs: what is wrong and what the
   page must say, as specific as a path, a key or a symbol. The repair sees only its own few
   pages, so tell it what it cannot see from there.
6. When one rule's problems sit on two sides, split the group. Give one finding per side, list
   the nodes of each in `nodes`, and leave `nodes` empty on the finding that judges the rest.
   A node is written as the problem names it, or as the page's path when it names none.

Judge every group. Reply with one finding per group, or per part of a split group, and nothing
else:

```json
{
  "findings": [
    {
      "group": 1,
      "side": "{{ sides | join('" | "') }}",
      "evidence": "what you read that shows the cause, with its path",
      "instruction": "for a book group, what the page repair must do; empty otherwise",
      "nodes": []
    }
  ]
}
```
