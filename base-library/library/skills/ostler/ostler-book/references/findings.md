# Findings, and what the book cannot see

Reached from step 7 of adding a route in [../SKILL.md](../SKILL.md), and whenever a command
reports something.

## What each command reports

| Finding | Command | Means | Fix |
| --- | --- | --- | --- |
| `<Record>: no source pointer` | check | a record or element names no source | add `source`; a finding present before your pass is the baseline, leave it |
| endpoint, journey or rule not registered | check | a class exists that nothing lists | add it to `ALL` or `__all__` |
| endpoint no matrix places | check | it will be played in every state | add a column to the matrix of the record it touches |
| module nothing imports | check | dead file | import it where it belongs, or delete it |
| `the book contradicts itself` | explore --seed-only | a scene or fixture arranges a record the model refuses | fix the scene's steps or the fixture, never the rule |
| `FAIL state ...` with `path:` and `rows differ` | explore --only | the model and the app disagree on one cell | compare the two lists; decide book wrong or app wrong |
| `rules never refused: N` | explore, run | a rule no reachable cell breaks | add the scene or input that breaks it, or the rule is dead |
| `declared scenes never reached` | explore, run | a scene no walk reaches | fix its `reached_by`, or the scene is wrong |
| `FAIL <Journey>` | run | a journey step disagreed | same as a cell FAIL |
| `KNOWN <Journey>` | run | a declared `Defect` answered as declared | nothing |
| `inputs: ... diverge as declared` | run | a declared `Diverges` held | nothing |
| `FAIL  input <Endpoint> <class>` | run | the app answered an input class other than the book predicts | book wrong: fix the shape or the refusal; app lenient: declare `Diverges` |
| `Declared divergences never met` | run | a `Diverges` whose class the app now refuses | the app was fixed or the class name changed: remove or rename it |
| a gap under "what the run witnessed" | run | an answer or field no step showed | reach it with a step, or declare it `Unseen` |

## Book wrong or app wrong

A FAIL is one of two things. Read the source the endpoint's `source` names and decide:

- **The book is wrong** when the source does what the app did. Fix the model, the shape or
  the fixture. When the fix is a behaviour a reader would not guess, it gets a `why`.
- **The app is wrong** when the source, the openapi or the product's rule says otherwise. Keep
  the intended behaviour in the model and write a `DISAGREEMENTS.md` entry. Then declare it
  by where it showed. A whole input class the app accepts and the book refuses, such as any
  malformed id, is a `Diverges` on the endpoint. A call in a cell or a journey that the app
  answers wrongly is a `Defect` on the action.

Never make a FAIL pass by loosening a shape, widening an existing fixture, or adding a step
that hides the difference.

## DISAGREEMENTS.md

One numbered entry per disagreement, after the last one:

```markdown
## 29. <what happens, as a sentence>

- Step: <the call, and whether a probe, a replay or a run found it>.
- Source and openapi: <what they say>, when it differs from what the app did.
- App did: <the answer>.
- Classification: app wrong, app lenient, app inconsistent, or book wrong (fixed). <What the book does about it.>
```

## What the book declares it cannot see

- `Unseen(Endpoint, "401", Because.SHARED_GATE, "<why>")` or
  `Unseen(Endpoint, "200: path.to.field", Because.<reason>, "<why>")` in
  `Service(unseen=...)`: an answer or field no run reaches. `Because` is a closed list of what
  lies out of the book's reach: `SHARED_GATE`, `NEVER_FILLED`, `OUTSIDE`, `NO_ACCOUNT`,
  `TEST_HOOK`, and `RUNTIME` for what the runtime cannot yet send or read. A gap the book
  can close by arranging a state, a caller or an input has no reason on the list: arrange it.
  A list whose only entries other cells made gets an entry the book makes, through a standing
  fact the backstage arranges once and the model seeds.
- `Diverges(Endpoint, "<input class as the run prints it>", why="<why>")` in
  `Service(diverges=...)`: the app accepts an input class the book refuses.
- A route the app answers with 501 or leaves unimplemented gets an endpoint whose answer says
  so, and an entry when the openapi promises more.

Every why says something a reader could check. "Not covered yet" is not a why.
