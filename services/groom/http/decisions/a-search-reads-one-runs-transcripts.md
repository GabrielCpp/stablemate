story: SM-01M6CQJKKQJQD68Y6FJECEQFJ0
date: 2026-11-23
elements: SearchRun
sources: groom/groom/activity.py::search, groom/groom/app.py::run_search

A search of a run's transcripts reads the turns of the one run in the path and that run's live turns, and never another run. The query is spaces-collapsed, cut to 200 characters and lowercased, and each matching line is cut to 160 characters around the match, so neither the request nor the answer grows with a transcript.

One transcript that cannot be read fails the whole search with 503. A partial match list would read as 'nothing else matches', so the search never answers one. The page keeps its row matches and offers a retry.

The book's groom has an empty store, so its search answers no match, as `an-empty-store-answers-empty` says. The browser tests of `groom/tests/test_activity_keys_dynamic.py` and the unit tests of `groom/tests/test_activity.py` play the matches.
