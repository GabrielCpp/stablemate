## Rules for every angle

- A defect you cannot point at is not a defect. Every finding names the section, criterion, line or element it is against, says what is wrong, and says what would repair it. If you cannot cite where a weakness lives, you have not found it yet. Find it or drop it.
- Review exhaustively in one lap. List every defect you can find now, across all angles. The next lap only verifies the repairs to what you list.
- Fail an angle only with at least one finding, and pass an angle with none. A finding needs a non-empty `target`, `issue` and `repair`.
- Do not return a blocked verdict. You judge an artifact. If it is too thin to judge, that is a finding against what is missing.
{%- if workhorse_var('prior') %}

## Convergence re-review

A full independent review already found these defects, one per line as `[angle] target: issue. Repair: repair`:

{{ workhorse_var('prior') }}

Verify every listed finding against the revision. Return a finding only when a listed one remains unresolved, using the same `target`, or when the repair introduced a concrete regression on the same angle. Do not re-raise a finding whose repair landed. Do not open a new stylistic preference or silently expand the contract. A defect you could have named in the first lap and did not is one you have forfeited.
{%- endif %}
