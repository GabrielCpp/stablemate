# Research Lead — Extend the Program (append the next gate)

The research lead judged the program at `{{ program_dir }}` **not yet at its North
star**, with a concrete next gate that moves materially closer. Record that gate by
**extending** the existing ladder — additively. Do **not** supersede or reset the
program (that is `define-new-direction`'s job, reserved for a justified kill); the
prior gates stay PASS and the North star is unchanged.

> **North star (unchanged):** the `## North star` of `{{ program_dir }}/README.md`
{% if goal %}> Manifest goal: {{ goal }}{% endif %}

The `scientific-method-controls`, `never-constraints`, and
`rules-authoring-workflow` skills define the discipline.

Repository: `{{ repo_dir | default('.') }}`
Program: `{{ program_dir }}`
Progress log: `{{ progress_path }}`
Code root: `{{ code_root }}`
Lead's goal review:

```json
{{ goal_review | default('{}') }}
```

## Do this

1. Read the README ladder, `{{ progress_path }}`, the latest gate Result slots, and the
   relevant `{{ program_dir }}/findings/`. The new gate must build on what passed and
   must not repeat anything the findings rule out.
2. Append the next gate to the ladder, keeping the folder a valid program so the loop
   reloads it (`rules-authoring-workflow` layout contract: valid `program.yml` +
   `README.md` ladder):
   - Add a row to the README gate-ladder table: new gate id (the next in sequence),
     title, its dependency on the last passed gate, and — if the program kill criteria
     need it — an updated criterion. **Do not** weaken or delete existing rows.
   - Create the gate doc `{{ program_dir }}/<gate_id>_<short>.md` mirroring the existing
     gate-doc format: **hypothesis** (one falsifiable sentence, from the lead's
     `next_gate_question`), design/deliverables, an **exact numeric success gate**, the
     **controls** it must run (from `next_gate_controls`, plus the program's standing
     controls — enumeration/random/cold floor as applicable), failure modes, imports to
     reuse, and an empty Result slot.
   - If experiment code for the new gate lives somewhere new, update `program.yml`'s
     `code_root`; otherwise leave it.
3. Add the new gate to `{{ progress_path }}` as `NOT STARTED`, **preserving** every prior
   gate's status and result. The new gate must be the lowest not-yet-PASS gate so
   `select-next-gate` picks it next.
4. Reuse the existing machinery (the measurement harness, control factory, multi-seed
   discipline, the leak/zero-weights guards). Do not rebuild what works; do not weaken
   any NEVER constraint. The new gate's success must be judged on **held-out** data.
5. Do **not** implement the experiment here — only define and record the gate. The loop
   selects it next.

## Output (JSON only)

```json
{"extend_result": {"status": "extended", "new_gate_id": "<id>", "new_gate_title": "<title>", "depends_on": "<last passed gate>", "gate_doc_path": "{{ program_dir }}/<gate_id>_<short>.md", "readme_updated": true, "progress_updated": true, "moves_closer": "<one line: how this gate advances the North star>"}}
```
