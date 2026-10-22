# pm

The PM: the one reviewer every authoring stage hands its output to, and the one that answers the writers' gaps.

## Map

- `angles.py`: the review angles of each stage, read from `prompts/angles/<stage>/`.
- `answer.py`: the gap answer turn and its `MAX_ANSWERS` budget.
- `flow.py`: the `PMReview` flow: one verdict per angle, then a pass or a list of findings.
- `ledger.py`: the human-editable `grills/pm.md` ledger of settled answers.
- `nodes/`: the steps that write the receipt and the ledger.
- `prompts/`: the inline and delegated review prompts, the stage briefs, one file per angle and the answer prompt.
- `receipt.py`: the `pm-receipt.json` a passing review leaves beside the work it judged.
- `schemas.py`: the verdicts, findings and gap answers.
