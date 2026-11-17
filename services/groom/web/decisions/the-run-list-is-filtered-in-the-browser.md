story: none
date: 2026-11-17
elements: FilterTheList
sources: groom/groom/assets/dashboard.js, groom/groom/projection.py::matches

The run list is filtered in the browser, on the fleet the socket already pushed, and not by asking groom: a list
filtered by the server would be replaced by the next push. The page trims what is typed, ignores its case, and keeps a
run when the text is part of its name, repo, node, the gate path it waits on or its id. The HTTP read of the fleet
filters too, in projection.matches, and the two books state their own filter.
