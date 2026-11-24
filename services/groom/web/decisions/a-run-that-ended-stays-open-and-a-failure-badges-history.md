story: SM-01M6CRJYT67JXWVN6BAEXYC7DF
date: 2026-11-24
elements: RunDetail, Runs, History, Settings
sources: groom/groom/assets/dashboard.js, groom/groom/projection.py, groom/groom/app.py, groom/groom/history.py

An operator who watches a run, or works in another pane, needs to learn that a run ended. A run the operator has open stays open with a strip that says it ended, how long ago and how, and links to the run in History. The History button of the rail carries a badge that counts the runs that failed since the operator last looked.

The server says a run ended through one `ended` member on the run's row and on its detail. The ending comes from the History mapping and nowhere else, so the strip, the row, the History table and the failure banner never disagree. A run that is running, or that continues through a reload, has no ending and shows no strip.

A run counts as failed when it failed, gave up or crashed. An interrupted run counts only when its root span recorded `error.kind` as `fatal`, because `interrupt` is the operator's own stop.

The strip derives from the open run's detail and not from its row. It stays when the row is evicted from the list, and it goes only when the operator selects another run. The row and the head change to ended in the same update, and Files and Diff leave the tabs, because a finished run has no live diff.

The strip's link opens the run in History, clears a kept filter that would hide it, and selects it there once the list has loaded. When a run's summary is written, the server sends every tab a `summary` frame. An open Overview then loads the failure banner, and an open History reloads and shows the run at the top with the totals following.

The last time the operator opened History lives in the browser's local storage, with the ids of the runs that failed since. The server holds nothing and is told nothing. A first load with no recorded time shows no badge and records now. Opening History clears the badge and records now, and leaving History records now again, so a run that ended while the operator was on History never counts. A run that ended before the page loaded counts when it failed after the recorded time. Each run counts once, so a reload does not raise the count.

Each badge is hidden from assistive technology, and the rail button's name states the count in words, so a count is never colour alone. The Runs badge counts blocked runs while any other pane is open, History included. The History badge never shows on History. This extends `the-gate-strip-sits-above-the-tabs`.

The elements are declared and not played, because the book's groom never receives telemetry and so never hears a run end. This keeps `the-book-arranges-an-archive-with-grooms-own-code`. The browser tests in `groom/tests/test_run_ended_dynamic.py` play them against runs that end through OTLP spans.
