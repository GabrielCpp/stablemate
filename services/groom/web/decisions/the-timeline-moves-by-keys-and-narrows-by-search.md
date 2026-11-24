story: SM-01M6CQJKKQJQD68Y6FJECEQFJ0
date: 2026-11-23
elements: RunDetail, Runs
sources: groom/groom/assets/dashboard.js, groom/groom/activity.py, groom/groom/app.py

An operator reading a long run wants to walk its rows without the mouse and to find a row by what it says. The Activity timeline answers j, k and e, a search field and a work item selector.

The keys walk the rows the timeline shows, in screen order, so search and the selector narrow what j, k and e reach. The key handler leaves the letter alone when the focus sits in an input, a text area, a select or editable text. This keeps `a-run-with-several-checkouts-chooses-one-inside-the-run`, where j and k skip every form control. The story's technical note said a select was not guarded, and the guard already named it, so nothing changed there.

The row a key moves to takes the focus, so Enter and Space act on what the operator reads. A key to a row out of view pauses a live run's follow, and a key to a row in view keeps it, so a key never fights the follow. This keeps `the-activity-timeline-follows-a-live-run`.

E counts problems by the one definition of `the-attention-tile-counts-problems-by-one-definition`. It wraps from the last problem to the first, and it opens the item, the pass and the fold that hold the problem, as `the-timeline-groups-by-work-item-pass-and-visit` keeps the group of a selected row open. A run with no problems reads 'This run has no problems.' and keeps the selection.

Row text is matched in the browser at each keystroke, as `the-run-list-is-filtered-in-the-browser` does for runs, with the case ignored and the spaces collapsed. Matching reaches rows inside folded headings. The transcript search asks groom for one run a quarter second after the last keystroke, and a reply to an older query is dropped through a sequence number. A transcript match shows 'in transcript:' with the line, and every match is set as text inside a mark.

One unreadable transcript fails the whole transcript search with a 503. The page then keeps the row matches, says the transcripts could not be searched and offers a retry, so a failed read never reads as no match. 'Nothing in this run matches' waits for the transcript search to answer.

The elements are declared and not played, because the book's groom holds only pushed runs, which report no spans, so the timeline has no rows and no bar. The browser tests in `groom/tests/test_activity_keys_dynamic.py` play them against real spans and records.
