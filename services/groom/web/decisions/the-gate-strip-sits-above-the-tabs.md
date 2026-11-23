story: SM-01M6CN62PAJJX6AD7Z3PXQ0T2M
date: 2026-11-23
elements: RunDetail, Settings, OpenRun, AnswerTheGate
sources: groom/groom/assets/dashboard.js, groom/groom/assets/dashboard.css, groom/groom/templates/dashboard.html, groom/groom/projection.py

An operator who reads a run's tab needs the gate's question where they already are, and answering must never cost them their place. The strip of open gates therefore sits between the run's header and its tabs, outside the tab's panel, so no tab's scroll moves it.

The strip lists every open gate of the run, keyed by its gate file. Telemetry reports one gate per run, so several gates come only from the run's own gate list. The strip takes at most half of the pane's height and scrolls inside that, so the tab below it always has room.

On the Overview the text the operator reads keeps its screen position while the strip opens, folds or clears. It shares the hold of `the-overview-refreshes-on-a-committed-span-batch`. Diff and Files keep their scroll offset instead, as story SM-01M6CP8M6RMAF18Y66ZZGQSTK9 settled, so a gate never moves the file the operator reads. When the strip is taller than the Overview's scroll offset the place cannot be held, because scrolling stops at the top.

Folding hides the blocks and keeps them, so a typed answer survives. The fold lasts while the same run stays selected, across tabs and live pushes. It resets on another run and after the run's detail is closed. A gate that opens while the strip is folded is counted on the folded line.

The Runs button of the left bar carries a badge with the number of blocked runs while another pane is open. It counts runs from the fleet's state counts, not open gates, so a run with two gates counts once. It stays hidden on the run list, because the list already shows each blocked run. The number is text and the button's name carries it, so the badge never relies on color alone. It extends `the-page-has-five-panes`.

A refused answer keeps the typed text and the notice says why, as `the-page-cannot-answer-a-pushed-runs-gate` describes. The book's groom holds only pushed runs, so the strip answers with that refusal.
