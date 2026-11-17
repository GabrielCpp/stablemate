story: none
date: 2026-11-17
elements: Runs, History, Attendant, Dispatch, Settings, OpenRuns, OpenHistory, OpenAttendant, OpenDispatch, OpenSettings
sources: groom/groom/templates/dashboard.html, groom/groom/assets/dashboard.js

The page is one document with five panes, chosen by the button of the left bar that is pressed: runs, history, the
attendant, dispatch and settings. Each pane reads its own HTTP route when it opens. The book's groom holds no ended
run, no attendance and no dispatch queue, so History, Attendant and Dispatch each show their empty line, and the
pane's button of the left bar is the interaction that reaches it. The page opens on the run list.
