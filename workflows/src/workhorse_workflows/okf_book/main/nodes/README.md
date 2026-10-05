# okf_book main nodes

The steps the main book flow calls. Each module owns one job a state hands off.

## Map

- `check_lead.py`: the page check's problems grouped by rule, the side the owner named for each, and the problems it held back.
- `check_pages.py`: the check the owner runs on its book, or on the pages it names.
- `claim_snapshot.py`: each claim's expected outcome when a gate opened, and the changes an answer made to them.
- `exercise.py`: the run of a book, or of the pages and fixture pages the owner names, against the real app.
- `gate.py`: what the run settles itself when a gate is answered: each blocker's rerun, its verdict, and the failures left to the owners.
- `lead_findings.py`: what the owner named for each group of a lap's failed checks, kept across laps, and the lap as it attributed it.
- `operator_answer.py`: the operator's latest answer, which every owner turn reads until the next gate.
- `owner_gate.py`: what the owner's turn is shown of the gates it last failed, and what its reply names of them.
- `page_sections.py`: the `###` sections of a page and the section each problem sits in.
- `progress_ledger.py`: each lap's failed checks by cause, and the rule that says a lap did not help.
- `report.py`: the run's account for the operator.
- `source_view.py`: the copy of the product source the owner reads.
- `stale_citations.py`: the citations whose file changed since their stamp, grouped by file, and what one reading of the change settles for them.
- `surface.py`: the declaration of one surface of a service.
- `surface_pass.py`: the services one pass of the run routes.
- `turn_budget.py`: the steps an owner turn takes, and what a folder costs to read.
- `writer_commands.py`: the owner's three commands and the state they share.
- `writer_jobs.py`: a check or scenario run kept apart from the call that starts it, whose result the same command reads on a later call.
- `writer_stack.py`: the stack a turn's checks share, brought up by the first and released when the turn ends.
- `writer_ostler.py`: the ostler commands the owner may run, counted and clipped.
- `writer_request.py`: what one owner turn is sent.
