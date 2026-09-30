# QA scenario harness

The modules a generated `qa_plan.py` imports at run time. They load inside a
scenario's own process, so they import only the standard library, each other
and Playwright.

## Map

- `ostler_qa.py`: the harness a `qa_plan.py` imports, and the runner that drives it.
- `ostler_qa_browser.py`: the Playwright lifecycle of a browser scenario.
- `ostler_qa_checkout.py`: the copy of the checkout a scenario's commands run in.
- `ostler_qa_documents.py`: the verifiers that read documents and bodies: a JSON path, a count of what it selects, and what a body must not carry.
- `ostler_qa_elements.py`: the verifiers that read page elements: shown, actionable, focusable, and how many were emitted.
- `ostler_qa_files.py`: the verifiers that read files and trees: what a working directory holds, and what changed in it.
- `ostler_qa_hierarchy.py`: the view-hierarchy scan a device screen is vetted from.
- `ostler_qa_lap.py`: the lap record, what each precondition built once in a lap leaves for the later scenarios.
- `ostler_qa_paths.py`: the document-path grammar, the steps a path parses into and how it walks a document.
- `ostler_qa_responses.py`: the verifiers that read what a request or a command answered: status, headers, exit code and output.
- `ostler_qa_scan.py`: the DOM scan `ostler vet` is built on.
- `ostler_qa_verdicts.py`: the verdict a check returns, the arguments it reads, and the values its assert record carries.
- `ostler_qa_verifiers.py`: the claim verifiers, every `verify:` kind by the reading it takes and the judge it applies.
