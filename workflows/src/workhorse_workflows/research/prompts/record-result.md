# Researcher — Record Result

The gate resolved. Persist the outcome per the PROGRESS protocol in
`rules-authoring-workflow`. Do not change code or re-grade — only record.

Repository: `{{ repo_dir | default('.') }}`
Program: `{{ program_dir }}`
Gate: `{{ gate_id }}`
Progress log: `{{ progress_path }}`
Forced outcome (if escalated): `{{ forced_outcome | default('') }}`

## Do this

1. Determine the outcome: `PASS` / `WEAK_PASS` / `FAIL` / `KILLED` from the gate
   check (or the forced outcome if the rework cap was hit → `FAIL_MAX_REWORKS`,
   recorded as FAIL).

   A forced outcome on gate `GOAL` is about the **program**, not a gate. Record it at
   the top of `{{ progress_path }}`, dated, under a `## Program verdict` heading:
   - `GOAL_REACHED` — the frozen target was met. Name the result and its number.
   - `GOAL_BANKED` — the North star is unmet, but the strongest result is shippable
     and is being recorded as such. Write it as a standalone claim a reader outside
     this program can act on: what was demonstrated, on what data, under which
     controls, with seeds and deltas. This is the program's product so far — not a
     status line. State plainly that the program stops here pending re-authorization.
   - `GOAL_IMPOSSIBLE` — a recorded negative. Name the findings that close each path.
2. Fill the gate doc's **Result slot** (`{{ gate_doc_path | default(program_dir + '/<gate>.md') }}`)
   — one line per metric, mean±std over seeds, deltas vs each control.
3. Update `{{ progress_path }}`:
   - PASS/WEAK_PASS → status + one-line result + date.
   - FAIL/KILLED → status + one specific failure-mode line + which causes were
     tried/remain. **Never delete a failure entry.**
4. If a new architectural invariant emerged, append a dated entry to the program's
   RULES/notes.
5. If `KILLED` (or forced FAIL), write a negative-result finding under
   `{{ program_dir }}/findings/<gate>_<short>.md`.
6. Delete throwaway artifacts only; keep all learnings.

## Output (JSON only)

```json
{"status": "recorded", "outcome": "PASS", "progress_updated": true, "result_slot_updated": true, "finding_path": ""}
```
