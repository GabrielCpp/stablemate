---
type: concept
slug: outside-events-and-the-watch
title: Outside events and the watch
---
# Outside events and the watch

A service that reacts to another one keeps states none of its own calls reaches, such as a timer that starts when a ticket service announces a ticket. The book makes that change itself and reads until it has landed.

An outside event is one `Arrange` class per thing a person does elsewhere. Its `carries` names the action of this book's model that says what this service does when it hears. The surface performs the event by sending the other service's own call, and that call must succeed, so the surface raises a book error on a refusal.

The watch is the list of reads the surface makes after each step to compare rows, declared on the service as `watch`. After an outside event the runtime reads the watch again until it shows what the model says. It reads at most a thousand times and judges the last reading. It never sleeps and never reads a clock, because each read is a round trip. A reading that is off its shape on the way, such as a record half written, is the event half landed, and the run reads again. A reading off its shape on the last read is raised.

The run remembers how long events took. After one event fails to land, the run is red already, so the bound drops to three times the longest landing seen, and to no fewer than fifty reads. The cells behind a broken consumer then fail in seconds each.

- code: ostler/ostler/book/runner.py::landed@1227c56ede47
- code: ostler/ostler/book/runner.py::Landings@95de9e9c866e
- code: ostler/ostler/book/arrange.py::Arrange@aaa21cfcef67
- code: ostler/ostler/book/httpsurface.py::HttpSurface.follow@87c90c8cd7f5
- rule: after an outside event the watch is read again until it shows what the model says, at most a thousand reads
- rule: the wait uses no sleep, no retry and no deadline, and reads no clock
- rule: after one event fails to land, the bound drops to three times the longest landing seen and never below fifty reads
- rule: a reading off its shape on the way to the model's rows is tolerated, and one on the last read is raised
- rule: an event whose change no watch read compares is not waited for, so the surface adds a read of each record the cell made to the watch
- rule: a cell asks only about what it made, within a scope only it has, and a column that cannot be scoped in a scene is impossible with its reason
- rule: the model names the record an event makes, and the surface learns the service's id for it from the answer of the call that made it
- rule: the book reads only the records a cell made after an outside event, because a seeded record has aged since the seed and its time fields drift
- tests: ostler/tests/test_book_runner.py::test_after_an_arrange_the_watch_is_read_again_until_it_shows_the_model
- tests: ostler/tests/test_book_runner.py::test_a_reading_off_its_shape_on_the_way_is_tolerated
- tests: ostler/tests/test_book_runner.py::test_a_reading_off_its_shape_on_the_last_read_is_raised
- tests: ostler/tests/test_book_runner.py::test_an_event_that_never_lands_is_judged_on_the_last_reading
- tests: ostler/tests/test_book_runner.py::test_after_one_miss_the_bound_drops
