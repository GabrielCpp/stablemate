# Research Lead — Revive a Wrongly-Stopped Gate

The research lead judged gate `{{ gate_id }}` of the program at `{{ program_dir }}`
to have been stopped for the **wrong reason** (an apparatus artifact or a missing
prerequisite, not a refuted hypothesis). Withdraw the stop and submit the gate back
for another pass. Follow the PROGRESS protocol in `rules-authoring-workflow`: **never
delete a failure entry — supersede it.**

Repository: `{{ repo_dir | default('.') }}`
Program: `{{ program_dir }}`
Progress log: `{{ progress_path }}`
Gate: `{{ gate_id }}`
Gate doc: `{{ gate_doc_path }}`
What stopped it: `{{ escalation | default('', true) or 'a kill' }}`
{% if notes %}
The stopping turn's own account:

> {{ notes }}
{% endif %}

Lead's verdict / required fix:

```json
{{ lead_review | default('{}') }}
```

## First: is this a re-scope, or a missing prerequisite?

A re-scope fixes the gate itself — a broken substrate, a dishonest guard, a control
that was never run. Re-opening the gate is enough, because the next pass through it
can do the corrected thing.

A **missing prerequisite** is different: the gate cannot be designed or built until
some *other* piece of work is done — data that has not been produced, a phase of an
earlier gate still queued, a tool or an asset that does not exist yet. Re-opening the
gate alone does nothing then: the loop selects it straight back, the design or build
blocks on the same missing work, and the program spends another review saying "do
the prerequisite first". The loop only ever runs **ladder gates**, so work that no
not-yet-PASS row owns is work the loop can never reach.

Decide which it is from the stopping turn's account, the lead's `evidence` and
`apparatus_fix`, the README ladder's `Depends on` column and `{{ progress_path }}`.
It is a missing prerequisite when that work is named as required before this gate can
proceed **and** no gate in the ladder whose status is not yet PASS/WEAK_PASS owns it.
A PASS row whose own status or notes record the part as queued, pending or not yet
started does **not** own it — its PASS is for what it measured.

## Do this

1. Write a reassessment finding at
   `{{ program_dir }}/findings/{{ gate_id }}_reassessment.md` stating why the stop
   was not a refutation, the evidence (`evidence` above), and the corrective
   (`apparatus_fix` above). Leave any original negative-result finding in place,
   unchanged.
2. In `{{ progress_path }}`: change the gate's status (`KILLED`, `BLOCKED`, or
   whatever it reads) to `REOPENED` with a one-line reason, set its dependents back to
   `NOT STARTED (pending {{ gate_id }})`, and add a dated "Reopening" note. Keep the
   original entry verbatim as the record of the first attempt.
3. In the gate doc `{{ gate_doc_path }}`: set status to REOPENED, keep the prior
   Result slot as "first attempt", and add a corrective-plan section that bakes in
   the lead's `apparatus_fix` so the next pass cannot repeat the artifact. Where the
   reviews already ruled on a contradiction the stopping turn raised — which document
   governs, how a case is classified — write that ruling into this section, citing the
   review, so the next design reads the answer instead of blocking on the question.
4. **Only for a missing prerequisite**, write that work as its own gate, ahead of this
   one, using the `rules-authoring-workflow` layout contract exactly as a program
   extension does:
   - Add a row to the README gate-ladder table for the prerequisite: a new gate id
     (the gate it completes plus a suffix, e.g. `G1b`, or the next free id), a title
     naming the work, and its own dependencies. Change `{{ gate_id }}`'s `Depends on`
     to name the new gate. **Do not** weaken or delete existing rows.
   - Create its gate doc `{{ program_dir }}/<gate_id>_<short>.md` in the existing
     gate-doc format. Its **success gate** is the prerequisite being verifiably done —
     the concrete, checkable completion condition the stopping turn and the lead named
     (counts, files, a validation that passes) — with an empty Result slot.
   - Add it to `{{ progress_path }}` as `NOT STARTED`. It must be the lowest
     not-yet-PASS gate whose dependencies are satisfied, so `select-next-gate` picks
     it before `{{ gate_id }}`.
   - One prerequisite gate covers the work blocking this gate; if several separate
     pieces are missing, list each as a deliverable of that one gate rather than
     writing several. If a gate already exists that owns it but is mis-ordered or
     mis-marked, fix that row instead of writing a new one.
5. Do **not** implement the experiment, the prerequisite, or re-grade — the researcher
   loop selects the next gate and runs it. Only re-open, re-scope, and record.

## Output (JSON only)

`prerequisite_gate_id` is the gate written (or re-ordered) in step 4, and `""` when
the gate needed only a re-scope.

```json
{"status": "reopened", "gate_id": "{{ gate_id }}", "finding_path": "{{ program_dir }}/findings/{{ gate_id }}_reassessment.md", "progress_updated": true, "gate_doc_rescoped": true, "prerequisite_gate_id": ""}
```
