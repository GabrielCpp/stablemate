## Rules for every angle

- A defect you cannot point at is not a defect. Every finding names the section, criterion, line or element it is against, says what is wrong, and says what would repair it. If you cannot cite where a weakness lives, you have not found it yet. Find it or drop it.
- Review exhaustively in one lap. List every defect you can find now, across all angles. The next lap only verifies the repairs to what you list.
- Every finding carries a `weight`. `blocking` means whoever builds from the subject as written would build the wrong behaviour, would have to take a product or UX decision the subject leaves open, or would meet a contradiction with the book, the epic or the mockup. `note` means anything else worth telling the writer, such as a wording that could be tighter or a detail whose obvious reading is the right one.
- Fail an angle only with at least one blocking finding. Pass an angle that has none, and list its notes if it has any. A finding needs a non-empty `target`, `issue` and `repair`.
- Do not return a blocked verdict. You judge an artifact. If it is too thin to judge, that is a finding against what is missing.
{%- if workhorse_var('prior') %}

## Convergence re-review

A full independent review already found these defects, one per line as `[angle] target: issue. Repair: repair`:

{{ workhorse_var('prior') }}

A line marked `(note)` is a note. Verify every listed finding against the revision. Return a finding only when a listed one remains unresolved, using the same `target`, or when the repair introduced a concrete regression on the same angle. Do not re-raise a finding whose repair landed. Do not open a new stylistic preference or silently expand the contract. A listed note counts as resolved or not like any finding, and it keeps the weight `note`. A defect you could have named in the first lap and did not is one you have forfeited.
{%- endif %}
