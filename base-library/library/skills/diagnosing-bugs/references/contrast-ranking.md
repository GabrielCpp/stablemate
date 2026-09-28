# Ranking hypotheses by contrast

Phase 3 of [the skill](../SKILL.md) branches here when the loop prints a failing set and a
passing set, each with more than a couple of examples. An example is anything the loop gives a
verdict: a test case, an input of a batch, a seed, a config, a commit.

The question is **which single change, had it been made, would have altered the verdict on
exactly the failing examples**. Answer it from what the runs recorded, then confirm it with a
real run. The record proposes. The real run grades.

The method needs three things. Say which one is missing when any is absent.

- **Two sets.** The failing set `F` and the passing set `P`, from one run of the loop over
  every example. With `P` empty, every hypothesis looks equally good. Phase 2's passing
  neighbours are the cheapest way to fill it.
- **A record per example.** Logs, traces, intermediate values, or the output of each stage:
  enough to say, per example, what each candidate site saw and produced.
- **Hypotheses that name a site.** Each one says where the fault sits and what that site should
  have done instead.

## The steps

1. **Write down both sets.** Done when `F` and `P` are listed and neither is empty.
2. **Write each hypothesis's affected set.** The affected set `A` is the examples whose verdict
   would change if the site behaved the way the hypothesis says it should. Work from the record,
   one example at a time, without re-running. Did this example reach the site? Given what the
   site saw there, would the corrected behaviour have produced something different? Judge the
   difference at the nearest point where it steers control flow or the output. A changed operand
   that leaves a comparison's result unchanged affects nothing. An example whose record cannot
   settle the question counts as affected, and you mark it as a guess, because guesses inflate
   `A`.
3. **Score the overlap.** `|A ∩ F| / sqrt(|A| · |F|)`, the Ochiai coefficient. It is 1 when the
   hypothesis affects every failing example and no passing one. Break ties by preferring the
   site fewer examples merely pass through.
4. **Run both controls.** Report their scores beside the method's.
   - **Coverage.** Rank the sites by how many failing examples pass through them. This is the
     classic spectrum ranking. When your top hypothesis wins only because the failures run
     through it, you have found where the system is busy.
   - **Shuffled failing set.** Draw a random set `R` of `|F|` examples and score the top
     hypothesis's `A` against `R` instead of `F`. A cause scores far lower on `R`. A story that
     scores as well on `R` does not depend on which examples failed.
5. **Check for real.** Fix the budget `k` before the first check and label it hardcoded. The
   study used 3. Apply the top `k` hypotheses one at a time, as a probe or as the fix, and rerun
   the loop over every example. One is confirmed when every verdict matches its expected
   verdict.
6. **Peel.** When none of the `k` confirms, keep the checked change that shrank `F` the most,
   make it the new baseline, and go back to step 1. One peel is the tested depth.

Every passing example inside a top hypothesis's `A` is a prediction that it should fail too.
Explain why it passes before trusting the rank. A compensating path elsewhere is a common
answer, and it is also a second site to rank.

## Example

A validator rejects 4 of 12 inputs that it should accept. Three hypotheses:

| Hypothesis | Affected set | Score |
| --- | --- | --- |
| H1: the tokenizer mishandles escapes | all 12, since every input passes through it | 4 / sqrt(12 · 4) = 0.58 |
| H2: the length limit is off by one | the 4 rejected, plus 1 accepted | 4 / sqrt(5 · 4) = 0.89 |
| H3: the date parser drops a timezone | 2 of the rejected | 2 / sqrt(2 · 4) = 0.71 |

H1 is the coverage answer. H2 ranks first. Against a random 4 of the 12, H2's affected set of 5
overlaps by about 1.7 on average, for a score near 0.37, so its 0.89 depends on which inputs
failed. The one accepted input inside H2's set is the next thing to explain. If it sits exactly
at the limit, H2 is sharper than the table says.

## Where it goes blind

- **Omission.** A missing check or branch leaves no record at any site, so the true cause has
  an empty `A`. When every hypothesis scores low, look for what the failing examples needed and
  nothing provided.
- **Coordinated changes.** A fix that needs two edits together is not a single-site
  hypothesis. Peeling finds the second fault far less often than the first.
- **No record.** Without per-example records, each `A` costs one real run per hypothesis. That
  is the blind search this method exists to beat, so fix `k` small.
- **Slow checks.** When a check takes a minute rather than a millisecond, the budget `k` is the
  whole cost.

## Report

Three parts, plus the numbers behind them:

- **Result.** Each example's verdict before and after.
- **Locus.** The site of the confirmed change.
- **Reason.** The kind of change, such as a swapped operator, a dropped item or an off-by-one
  limit.
- **Numbers.** `|F|`, `|P|`, the top scores, both control scores, `k`, and every guess counted
  as affected.

## Provenance

The method comes from a study on generated grammars and small programs, each with one injected
single-site fault and 104 cases per seed. With a budget of 3 checks, it repaired 55 to 66 cases
per seed. Coverage ranking repaired 12 to 21, and a shuffled failing set repaired 7 to 12. Real
repair work has not been measured. In a census of 134 real agent repair episodes, 5 were
one-token faults. Treat the ranking as a way to order checks, not as a verdict.
