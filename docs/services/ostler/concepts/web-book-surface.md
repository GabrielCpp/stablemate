---
type: concept
slug: web-book-surface
title: The web surface of a book
---
# The web surface of a book

A web book plays a web app the way a person drives it. The book declares screens and interactions where an HTTP book declares endpoints, and the run drives a headless Chromium through Playwright. Each interaction runs on the model and in the page, and the rows the page then shows are compared with the model's rows.

A screen lists its components. A component is found by role and accessible name, as a user finds it, and carries a test id only where the app offers no name to find it by. A screen also names the requests the page may send. After each step the run fails the step when the page sent a request under the screen's API prefix that no screen declares.

The runtime supplies the browser and the verbs a web book repeats: opening a page, finding a component in a row, typing, picking, pressing, reading a text, and waiting on an answer or on a component. The book's surface supplies what is the app's own: how each interaction is performed, how the app is put back to its first state, and how the rows are read. A new web book's surface is a few dozen lines past the interactions.

- code: ostler/ostler/book/browser.py::Browser@0@0de9aee5f34a
- code: ostler/ostler/book/pagesurface.py::PageSurface@0@f8fd370f4948
- code: ostler/ostler/book/screen.py::Screen@0@2ca061585fdf
- rule: a web run records one video for each journey and each cell arrangement under `<out>/videos`, keeps it when a step failed or met a known defect or when `--keep-videos` is given, and the run lists each such step with the video and its offset in the m:ss.t form of the QA harness
- rule: a web surface waits on an event, a request leaving, an answer arriving, a component appearing or the rows an answer carries showing, and a book declares no sleep, timer or timeout
- rule: a web book runs headless and needs the `qa` extra of ostler and an installed Chromium, and a run without Playwright stops with an error that names the extra
- rule: a component is found by role and accessible name, and a test id is the exception for an element the app gives no name
- rule: the runtime holds the browser verbs every web book repeats and the book holds only the app's own steps, so a web book never imports Playwright
- rule: a page request under a screen's API prefix that no screen declares fails the step that caused it
- rule: a component declares the shape of the fixture field it takes with `takes` and `holds`, and the interaction on its screen then plays input classes and twin pairs on that field as an endpoint does on its fields
- rule: a date typed into a screen also gets a twin pair of the clock's day and the day after, and a page that reads the date in another time zone is reported underspecified when the model reads both days alike
- rule: a browser that rejects a typed value makes the input class unreachable and not a failure, and the surface leaves the screen as it found it
- tests: ostler/tests/test_book_web.py::test_the_journeys_and_the_cells_play_green_headless
- tests: ostler/tests/test_book_web.py::test_a_planted_bug_in_the_page_turns_the_run_red
- tests: ostler/tests/test_book_web.py::test_the_browser_names_the_extra_when_playwright_is_missing
- tests: ostler/tests/test_book_web.py::test_a_screen_input_with_a_shape_gets_input_classes
- tests: ostler/tests/test_book_web.py::test_a_screen_input_with_a_shape_gets_twins_on_either_side_of_midnight
- tests: ostler/tests/test_book_web.py::test_a_screen_input_that_ignores_a_dimension_skips_its_twins
- tests: ostler/tests/test_book_web.py::test_a_page_that_sends_the_date_from_a_local_midnight_is_underspecified
