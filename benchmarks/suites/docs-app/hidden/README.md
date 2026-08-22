# Held out, on purpose

**A design-completeness score is judged against expectations the workflow under test was
never shown.**

That is the whole instrument. The measurement is the gap between what a brief *implies*
and what author *wrote*; the moment the expectation list — or a paraphrase of it — reaches
the backlog, a prompt, an installed skill the run resolves, or anything else a phase
reads, the benchmark stops measuring design and starts measuring transcription. And it
does so silently: the scores keep printing, they simply stop meaning what the column
header says, and every number the suite ever produced becomes retroactively suspect
because nobody can say which side of the leak it came from.

So:

- Nothing in this directory is ever copied into `target`. `bench.py backlog` seeds exactly
  one file — `docs/backlog.md` — and `tests/test_bench.py` asserts that a seeded target
  contains no text from this directory.
- Nothing in here is named to a workflow. The judge reads it, and the judge runs after
  author has finished and writes nothing.
- `../docs/backlog.md` is **deliberately underspecified**. That is its job, not a defect
  to fix. A pull request that "completes" the brief by adding a sign-out bullet has
  deleted the experiment, not improved it.

The same discipline `bench.py` already applies one level down: planning documents are
claims, not evidence. Here the input backlog itself is the claim about scope, and these
files are the evidence standard.

## What is in here

| File | What it is |
|---|---|
| `expectations.yaml` | the held-out expectation pack — invariant + rendering per entry, seeded from the observed `acme` miss list |
| `journeys.yaml` | the scripted persona journeys the dead-ends metric walks |

Both are read only by `bench.py design-score`.
