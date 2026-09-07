# Research Lead — Apply a Program Review

The program review for `{{ program_dir }}` returned a verdict that changes the program
rather than a gate. Apply it **in this same program folder**, under the layout contract
in `rules-authoring-workflow`: `program.yml` stays valid, nothing is deleted, superseded
material is labelled and kept.

Repository: `{{ repo_dir | default('.') }}`
Program: `{{ program_dir }}`
Progress log: `{{ progress_path }}`
Gate template: `{{ gate_template }}`
Today: `{{ today }}`

The review:

```json
{{ review }}
```

{% if resolvability_failure %}
## Your previous target was refused

The target you wrote last time was checked in code against the seed noise of its own
eval and **did not clear the floor**:

> {{ resolvability_failure }}

Write a target that does. The arithmetic is binomial: with `n` task-instances at
baseline rate `p`, one standard error of the resolve rate is `sqrt(p(1-p)/n)`, and the
threshold must sit at least **two** of those above the baseline. Either the eval gets
bigger (`n` up), or the margin does, or the metric changes to one whose noise is smaller.
Keeping the old eval with the old margin is the one thing that cannot pass.
{% endif %}

## The dossier the review was judged on

{{ dossier }}

## Do this, for whichever fields the review filled

**If `recharter` is filled** (a new frozen target):

1. Rewrite the `### Frozen target` table in `{{ program_dir }}/README.md` with the new
   Metric, Dataset / split, Threshold (as `>= <count>/<n>`), Seeds and Deadline rows,
   and add a `Baseline` row (`<count>/<n>`). Move the old table under a
   `### Superseded target (re-chartered {{ today }})` heading directly below it — kept,
   labelled, not deleted.
2. Under the table add a one-paragraph **Resolvability** note giving the SE arithmetic
   from `why_resolvable`.
3. Append a dated entry to `{{ progress_path }}`:
   `## {{ today }} — Program re-chartered` — the old target, the new one, and the
   review's `reason` verbatim. If the ladder's gates measured the old target, say in the
   entry which gates now measure the new one and adjust their rows' `Depends on` /
   `Result` cells only where the old target is named.

**If `probe` is filled** (a probe gate ordered ahead of the ladder):

4. Write `{{ program_dir }}/<gate_id>_<slug>.md` from the gate template: the probe's
   `question` as the hypothesis, `kill_if` as the exact kill criterion, `expected_cost_s`
   as a declared budget in the design section, controls from the README, an empty
   Result slot. Say in the design that it re-uses existing artifacts and code wherever
   the review's `evidence` names them.
5. Insert a row for it at the **top** of the active status table in `{{ progress_path }}`
   with status `NOT STARTED` and `Depends on` = `-`, and a row in the README's gate
   ladder with the exact advance condition. `select-next-gate` picks a `NOT STARTED`
   probe ahead of every ladder gate.

**If `cache_gate_id` is filled** (score an existing gate from its cache):

6. Append to that gate's doc a section:
   ```
   ## Loop directive ({{ today }})
   Score from `<cache_dir>` only. Do not re-run the experiment. <reason>
   ```
7. Set the gate's row in `{{ progress_path }}` to `REOPENED (score from cache)` with a
   one-line reason, keeping any prior KILLED entry verbatim.

Always:

8. Append `## {{ today }} — Program review: <verdict>` to `{{ progress_path }}` with
   the review's `reason` and `triggers_confirmed`, if step 3 did not already write it.
9. Leave `program.yml` as it is unless the new target moves where code lives.
10. Do **not** implement or run anything. Write the documents and return.

Return `status: "blocked"` with the reason if the review's fields contradict each
other or the README cannot be edited as asked.

## Output (JSON only)

```json
{"status": "written", "new_target": {"metric": "<as written to the README, or empty>", "dataset": "", "threshold": "", "threshold_count": 0, "n": 0, "seeds": [0, 1, 2], "baseline": "", "baseline_count": 0, "deadline": "", "why_resolvable": ""}, "probe_doc_path": "<path or empty>", "cache_doc_path": "<path or empty>", "readme_path": "{{ program_dir }}/README.md", "progress_updated": true, "reason": "<one line: what was written>"}
```
