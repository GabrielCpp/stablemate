# okf_book main nodes

The steps the main book flow calls. Each module owns one job a state hands off.

## Map

- `check_pages.py`: the check a writer runs on its book, on the pages its turn repairs, or on the pages it names.
- `cited_lines.py`: the lines of a cited file a claim rests on.
- `claim_snapshot.py`: each claim's expected outcome when a gate opened, and the changes an answer made to them.
- `exercise.py`: the run of a book, or of the pages and fixture pages the writer names, against the real app.
- `gate.py`: what the run settles itself when a gate is answered: each blocker's rerun, its verdict, and the failures left to the writers.
- `journey.py`: the pages a fix that puts a page on a journey may change.
- `operator_answer.py`: the operator's latest answer, which every repair turn reads until the next gate.
- `page_sections.py`: the `###` sections of a page and the section each problem sits in.
- `progress_ledger.py`: each lap's failed checks by cause, and the rule that says a lap did not help.
- `repair_batch_models.py`: the pages one repair turn is sent, the batches they go in, and the parts too large for any turn.
- `repair_batches.py`: the batches a book too large for one writer is repaired in.
- `repair_cost.py`: what one writer reads to repair a page or one of its sections, in tokens.
- `repair_ledger.py`: what the repair carries: each round's batches, the ledger kept from round to round, and what it leaves.
- `repair_put_back.py`: which pages a repair turn changed that its batch may keep, and the stamp on those it keeps.
- `report.py`: the run's account for the operator.
- `root_entries.py`: the entries page code writes for a book that has none.
- `source_view.py`: the copy of the product source a writer reads.
- `surface.py`: the declaration of one surface of a service.
- `surface_pass.py`: the services one pass of the run routes.
- `turn_budget.py`: what one writer turn reads, held against its budget.
- `writer_commands.py`: the writer's three commands and the state they share.
- `writer_jobs.py`: a check or scenario run kept apart from the call that starts it, whose result the same command reads on a later call.
- `writer_stack.py`: the stack a turn's checks share, brought up by the first and released when the turn ends.
- `writer_ostler.py`: the ostler commands a writer may run, counted and clipped.
- `writer_request.py`: what one writer turn is sent.
