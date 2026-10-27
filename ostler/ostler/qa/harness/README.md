# QA scenario harness

The modules a generated `qa_plan.py` imports at run time. They load inside a
scenario's own process, so they import only the standard library, each other
and Playwright.
