# tasks

One module per benchmark round, loaded by `paddock` from `--data-dir`. A module with a leading underscore is shared round machinery. Every other module declares one task and names the fixture under `../apps/` it runs against.

## Map

- `_forensics.py`: reading a staged round's run dirs back: repair loops, churn, node timing, cap-wait and the cost lines of the scorecard.
- `_frozenapp.py`: the frozen-app QA round: materializing a story, seeding a defect from the answer key, and scoring whether QA caught it.
- `_greenfield.py`: the greenfield round every backlog fixture shares: its phases, the frozen grill turn, its backlog trace and its score.
- `_judge.py`: one agent turn that waits out usage caps, and the rubric fill every judged task uses.
- `_leverage.py`: how far a trial's QA plan used what the book documents, read statically from the plan, the book and the run log.
- `_linkshort.py`: the link-shortener acceptance gate: twelve black-box checks over a built product.
- `_mutants.py`: the mutant round: seeding a curated behavior change, running the story's QA, and the pin rate it scores.
- `_operator_gates.py`: the operator-gate ledger, and the watcher that parks a round on a gate nothing answered.
- `_replay.py`: replaying one lane of the coder workflow cold, on a tree that already ran it, and scoring its convergence.
- `_stablemate.py`: the process boundary a task drives stablemate across: the pinned checkout, the pinned config and the leak check.
- `claims_api_qa.py`: the frozen-app QA round on claims-api, an app with no screen.
- `depot_infra_audit.py`: the depot-infra QA round with the auditor on, scored on defect D7 alone.
- `depot_infra_qa.py`: the frozen-app QA round on depot-infra, where nothing runs.
- `expense_split.py`: a replay round on expense-split that asks whether a review loop converges without an answer key.
- `globex_book_disagree.py`: the probe that asks whether an agent can tell if the app or the book is wrong when they disagree.
- `globex_book_line3.py`: the probe that asks what a node is for and which story asked for it, from the book alone.
- `globex_book_operate.py`: the probe that asks whether an agent can bring globex up and drive it from the book and a browser.
- `globex_qa.py`: the frozen-app QA round on globex, the only two-service fixture.
- `link_shortener.py`: the smoke task: a greenfield round with one Go surface and three bullets.
- `link_shortener_dev.py`: a replay of the dev lane on link-shortener, graded by the same gate as a solo-agent baseline.
- `link_shortener_replay.py`: a replay of the docs lane on link-shortener's smallest real story, to measure its cost.
- `policy_desk_qa.py`: the frozen-app QA round on policy-desk: does QA notice a seeded defect and work the product.
- `seat_booking_audit.py`: the seat-booking QA round with the auditor on, scored on defect D9 alone.
- `seat_booking_qa.py`: the frozen-app QA round on seat-booking, the small app.
- `seat_booking_qa_minimax.py`: the seat-booking QA round run on MiniMax through an OpenRouter key.
- `seat_booking_qa_minimax_direct.py`: the seat-booking QA round run on MiniMax through minimax.io's own API.
- `tally_cli_mutants.py`: the mutant round on tally-cli: is the book what kills a defect.
- `tally_cli_qa.py`: the frozen-app QA round on tally-cli: does QA separate obligations that share a file.
