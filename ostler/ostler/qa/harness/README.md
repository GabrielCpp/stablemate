# QA scenario harness

The modules a generated `qa_plan.py` imports at run time. They load inside a
scenario's own process, so they import only the standard library, each other
and Playwright.

## Map

- `ostler_qa.py`: the harness a `qa_plan.py` imports, and the runner that drives it.
- `ostler_qa_browser.py`: the Playwright lifecycle of a browser scenario.
- `ostler_qa_hierarchy.py`: the view-hierarchy scan a device screen is vetted from.
- `ostler_qa_scan.py`: the DOM scan `ostler vet` is built on.
- `ostler_qa_verifiers.py`: the claim verifiers, what each `verify:` kind observes, and the document reads they share.
