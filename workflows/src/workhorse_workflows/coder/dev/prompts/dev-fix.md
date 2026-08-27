# Coder Workflow — Fix Stage

A gate this story must pass reported a failure, and the workflow routed it back to you.
Your only job is to make that gate pass. Nothing else.

- **Gate:** `{{ report.source }}`
- **Where:** `{{ report.cwd }}`{% if report.command %}
- **Command:** `{{ report.command }}`{% endif %}
- **Repair attempt:** {{ report.lap }}

## What the gate reported

{% if report.output %}
```
{{ report.output }}
```
{% endif %}
{% if report.findings %}
{% for finding in report.findings %}
- **{{ finding.target }}** — {{ finding.issue }}
  - Repair: {{ finding.repair }}
{% endfor %}
{% endif %}
{% if changed_files %}
## What this story has already changed

{% for path in changed_files %}- `{{ path }}`
{% endfor %}
{% endif %}

## Steps

1. **Reproduce it.** Run the command above in the directory above, exactly as written. If
   there is no command, work from the findings. Do not substitute a command you believe is
   equivalent — the gate will re-run this one.
2. **Read what it points at.** Open every file and line named in the output. Understand why
   the change made in this story caused it, before editing anything.
3. **Fix the cause, minimally.** Correct the code the gate flagged. Do **not** weaken,
   suppress or delete the gate to make it pass — that removes the check instead of the
   defect. A targeted suppression is defensible only when the rule is wrong for one specific
   line, and then you say why in the notes. Do not refactor or add features beyond passing.
4. **Re-run the command and confirm it is clean.** The workflow re-runs it deterministically
   afterwards, so a still-failing tree simply comes back to you.
5. **Commit what you fixed**, carrying `Epic: {{ epic }}` and `Story: {{ story_slug }}` as
   trailers, spelled exactly so — the run record ties a commit back to its story through
   them. **Do not push or open a PR** — the workflow owns those.

If one finding cannot be fixed without changing intended behaviour, fix everything else and
explain the one you left in `notes`.
{% if report.source == "lint" %}

### For this gate: lint

The findings are the repo's own standard, not advice. Follow the repo's loaded skills for the
correct fix on each one; a suppression is not a fix.
{% elif report.source == "verify" %}

### For this gate: verification

The gate ran the story's own verification. Make the behaviour it checks correct — changing
the check to match the code is the one repair this stage may never make.
{% elif report.source == "regression" %}

### For this gate: regression

Something that used to pass no longer does, and it is very likely the change this story just
made. Prefer repairing the change over amending the older expectation; if the older
expectation is genuinely obsolete, say so explicitly in `notes`.
{% endif %}
{% block repo_fix_rules %}{% endblock %}

## Output

Return the JSON document as the LAST thing in your final response — its keys at the top level, with no wrapper object around them. Any other shape fails to parse and the node is retried.

{{ result_schema }}

Re-run the gate locally before you answer.
