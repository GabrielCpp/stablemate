# okf_book main nodes

The steps the main book flow calls. Each module owns one job a state hands off.

## Map

- `check_pages.py`: the check a writer runs on its book or on the pages its turn repairs.
- `cited_lines.py`: the lines of a cited file a claim rests on.
- `exercise.py`: the run of a book against the real app.
- `journey.py`: the pages a fix that puts a page on a journey may change.
- `page_sections.py`: the `###` sections of a page and the section each problem sits in.
- `repair_batches.py`: the batches a book too large for one writer is repaired in.
- `repair_ledger.py`: what the repair carries: each round's batches, the ledger kept from round to round, and what it leaves.
- `report.py`: the run's account for the operator.
- `root_entries.py`: the entries page code writes for a book that has none.
- `source_view.py`: the copy of the product source a writer reads.
- `surface.py`: the declaration of one surface of a service.
- `turn_budget.py`: what one writer turn reads, held against its budget.
- `writer_commands.py`: the writer's three commands and the state they share.
- `writer_ostler.py`: the ostler commands a writer may run, counted and clipped.
- `writer_request.py`: what one writer turn is sent.
