# Engineer — A job running past its estimate

A measurement for the program at `{{ program_dir }}` is still running at
**{{ overrun_multiple | default(10) }}×** its estimate. Nothing has failed. You are being
asked one question: **is it still worth waiting for?**

Repository: `{{ repo_dir | default('.') }}`
Gate: `{{ gate_id }}`
Gate doc: `{{ gate_doc_path }}`
Code root: `{{ code_root }}`
Job directory: `{{ job_dir }}`

Estimate: {{ estimate_s | default(0) }}s, derived from this probe:

```json
{{ probe }}
```

Command:

```json
{{ command }}
```

## Time is a bug signal, not a budget

The job is **not** being killed for taking too long. A command that overshoots is
carrying information — about the code, or about the estimate — and killing it destroys
that information along with however many hours of work are already in it.

So the default is **keep going**, and it costs almost nothing: the thresholds double, so
you will be asked again at {{ overrun_multiple | default(10) }}×2, and again after that.
The wakeups get rarer exactly as fast as the job gets less likely to be worth waiting
for. Killing is the decision that cannot be taken back.

## Do this

1. Look at the job directory: `stdout.log` and `stderr.log` are the command's own
   output, `heartbeat` is the supervisor's, `runner.json` appears only when it is over.
   Is it *progressing* — new output, a moving epoch counter, a growing checkpoint — or
   is it silent?
2. Compare what it has done against the probe. If the probe timed 3 of 240 units in 42
   seconds and the log is at unit 200, the estimate was wrong and the run is fine; if
   the log has not moved in an hour, it is not.
3. Look for the shapes that do not end: a wait on something that will never arrive, a
   retry loop with no bound, a quadratic pass over something that grew, thrashing near
   the memory ceiling.

## Decide

`keep_going` — it is progressing, or the estimate was simply too low. Say why in
`diagnosis`; you will be asked again at the next threshold. Prefer this whenever the
evidence is ambiguous.

`kill_and_fix` — it is stuck, looping, or provably will not finish in any useful time.
This kills the job and hands the gate back to an engineer with your `fix_hint`, so make
that hint specific: the file, the loop, the call that hangs.

Set `fault_locus: "tooling"` with a named `component` only if what is stuck is not this
repo's code — the runner, the machine, a dependency you do not control. That routes to a
human, and an unnamed component is treated as a repo fault.

## Output (JSON only)

```json
{"decision": "keep_going", "diagnosis": "<what the logs show>", "fault_locus": "", "component": "", "fix_hint": "<only for kill_and_fix: the specific thing to change>"}
```
