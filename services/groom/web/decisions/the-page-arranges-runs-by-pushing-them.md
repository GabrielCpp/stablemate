story: none
date: 2026-11-17
elements: ReportProgress, ReportGate, ReportExit
sources: groom/groom/app.py::push_progress, groom/groom/app.py::push_blocked, groom/groom/app.py::push_exited

A run reaches groom by a workflow pushing it, not by anything the dashboard does, so the page book arranges a run by
the same three pushes the HTTP book uses and then reads the list. The check suggests asking the HTTP book for the run
with Needs. The page book keeps its own pushes because the push is the event the page is judged against: it must
show the run the moment groom takes the push, over its own socket, and a Needs would arrange the run before the page
opened.
