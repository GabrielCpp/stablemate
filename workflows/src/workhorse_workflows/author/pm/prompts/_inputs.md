## Inputs

- Stage under review: `{{ workhorse_var('stage') }}`
- Subject: `{{ workhorse_var('subject') }}`
{%- if workhorse_var('epic') %}
- Epic: `{{ workhorse_var('epic') }}`
{%- endif %}
{%- if workhorse_var('milestone_dir') %}
- Milestone folder: `{{ workhorse_var('milestone_dir') }}`. Its `milestone.md` is the contract, its `grills/` folder holds the grill records, and its `mockups/` folder holds one mockup per journey.
{%- endif %}
{%- if workhorse_var('services_dir') %}
- OKF book root: `{{ workhorse_var('services_dir') }}`. It is the existing documentation of each service. Read it and never write to it.
{%- endif %}
{%- if workhorse_var('ledger') %}
- PM ledger: `{{ workhorse_var('ledger') }}`. It records the product questions already answered for this milestone. Read it before you judge. Its answers bind you: a design the ledger settles is not a finding, and a design that contradicts it is.
{%- endif %}

You review an artifact. Do not edit any file.
