---
type: concept
slug: web-book-surface
title: The web surface of a book
---
# The web surface of a book

A web book plays a web app the way a person drives it. The book declares screens and interactions where an HTTP book declares endpoints, and the run drives a headless Chromium through Playwright. Each interaction runs on the model and in the page, and the rows the page then shows are compared with the model's rows.

A screen lists its components. A component is found by role and accessible name, as a user finds it, and carries a test id only where the app offers no name to find it by. A screen also names the requests the page may send. After each step the run fails the step when the page sent a request under the screen's API prefix that no screen declares.

The runtime supplies the browser and the verbs a web book repeats: opening a page, finding a component in a row, typing, picking, pressing, reading a text, and waiting on an answer or on a component. The book's surface supplies what is the app's own: how each interaction is performed, how the app is put back to its first state, and how the rows are read. A new web book's surface is a few dozen lines past the interactions.

- code: ostler/ostler/book/browser.py::Browser@0@67aacea61e02
- code: ostler/ostler/book/pagesurface.py::PageSurface@0@03bf2a58e922
- code: ostler/ostler/book/screen.py::Screen@0@36149e8afa72
- rule: a web run records one video for each journey and each cell arrangement under `<out>/videos`, keeps it when a step failed or met a known defect or when `--keep-videos` is given, and the run lists each such step with the video and its offset in the m:ss.t form of the QA harness
- rule: a web surface waits on an event, a request leaving, an answer arriving, a component appearing or the rows an answer carries showing, and a book declares no sleep, timer or timeout
- rule: a web book runs headless and needs the `qa` extra of ostler and an installed Chromium, and a run without Playwright stops with an error that names the extra
- rule: a component is found by role and accessible name, and a test id is the exception for an element the app gives no name
- rule: the runtime holds the browser verbs every web book repeats and the book holds only the app's own steps, so a web book never imports Playwright
- rule: a page request under a screen's API prefix that no screen declares fails the step that caused it
- rule: a screen's components carry no shape, so input classes and twin pairs are not played on a web book
- tests: ostler/tests/test_book_web.py::test_the_journeys_and_the_cells_play_green_headless
- tests: ostler/tests/test_book_web.py::test_a_planted_bug_in_the_page_turns_the_run_red
- tests: ostler/tests/test_book_web.py::test_the_browser_names_the_extra_when_playwright_is_missing
