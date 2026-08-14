# Independently review a completed implementation plan

Act as the final senior reviewer. The implementation agents' claims and green command output are
evidence, not proof. Review the exact candidate against the complete immutable plan and identify
every actionable issue that must be fixed before this workflow may claim completion.

## Authority

- Plan digest: `{{ workhorse_var('plan_digest') }}`
- Original base commit: `{{ workhorse_var('base_commit') }}`
- Candidate commit: `{{ workhorse_var('candidate_commit') }}`
- Review cycle: {{ workhorse_var('review_cycle') }}

## Complete source plan

{{ workhorse_var('plan_text') }}

## Validated implementation packets and aggregate commands

```json
{{ workhorse_var('prepared_plan') | tojson(indent=2) }}
```

## Review procedure

Inspect the repository and `git diff {{ workhorse_var('base_commit') }}..{{ workhorse_var('candidate_commit') }}`. Check, at minimum:

1. every plan requirement and acceptance criterion is actually implemented;
2. behavior is integrated across the real call paths, not only unit-tested in isolation;
3. lifecycle, resume, error, and boundary behavior is coherent;
4. every packet acceptance criterion has a covering test that would fail if the behavior
   regressed, and tests also exercise the important failure and recovery paths — the
   tests-first red gate fails open after bounded rework, so this audit is the binding
   check; an uncovered criterion is an actionable issue;
5. no test was weakened, deleted, skipped, or loosened during implementation without a
   declared justification that the test itself was wrong — an unjustified test edit is
   an actionable issue;
6. public-package, portability, typing, security, and repository conventions still hold;
7. documentation and metadata match the shipped behavior;
8. no placeholder, bypass, omitted phase, or unsupported completion claim remains.

Do not edit, commit, push, or change Git configuration. Do not list speculative improvements or
preferences. Every issue must be concrete, evidenced, within the source plan's scope, independently
fixable, and severe enough to block completion.

For every issue, return one commit-sized packet with:

- a lowercase kebab-case `id`, at most 48 characters, unique in this review;
- `title`, `objective`, and a concrete `finding` explaining the observed defect and evidence;
- observable `acceptance` statements;
- explicit repository-relative `paths` it may change;
- dependency ids when issue ordering is required;
- argv-based `verification` commands (never shell source or Git commands);
- a valid Conventional Commit `commit_type` and optional tracked top-level `commit_scope`.

Return `approved` only when there are no actionable issues. An approval with issues, or an `issues`
verdict with an empty list, is invalid and stops the workflow.

End with exactly one JSON object:

```json
{
  "status": "approved|issues|blocked",
  "summary": "what was reviewed and why this verdict follows",
  "issues": [
    {
      "id": "concrete-defect",
      "title": "Concrete defect",
      "objective": "Correct the observed defect.",
      "finding": "Exact evidence and why it violates the plan.",
      "acceptance": ["Observable corrected behavior."],
      "depends_on": [],
      "paths": ["path/to/owned-area"],
      "verification": [
        {"argv": ["python", "-m", "pytest", "path/to/test.py", "-q"], "cwd": ".", "timeout_s": 1800}
      ],
      "commit_type": "fix",
      "commit_scope": ""
    }
  ]
}
```