---
type: concept
slug: lists-read-as-containing
title: A list is read as containing
---
# A list is read as containing

The service is never wiped between cells. Every cell, every journey and every other person who reaches the same environment share its standing accounts, so the service holds records the book never made. A list the book reads is read as containing what the book made and nothing more.

The runtime compares a listing only on the entries the book made. A `Listed` step removes the rows that stood in the watch when the journey began, then expects the rows left to equal the records the author names. A count of everything a list holds is never asserted.

- code: ostler/ostler/book/runner.py::listed@694880f28733
- code: ostler/ostler/book/runner.py::without@2013c1c60174
- code: ostler/ostler/book/journey.py::Listed@388214ed5158
- code: ostler/ostler/book/http.py::List@ee0ed28b9ebd
- rule: a list is read as containing the entries the book made, never as equal to what the service holds
- rule: the book never assumes a list is empty and never asserts a count of everything listed
- rule: an order the service does not fix is declared `unordered` with the tie it leaves open, so the run does not fail on an order the product never promised
- rule: a value the caller types and the book never issued is declared as a stranger id with its reason, so the run reads it back as written and not as an unknown id
- tests: ostler/tests/test_book_todo.py::test_run_plays_the_journeys_the_cells_and_the_input_classes
