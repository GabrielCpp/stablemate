story: SM-01M6CN5KZ826G63H89XZGBREEW
date: 2026-11-22
elements: AnswerTheGate, RunDetail
sources: services/groom/web/surface.py::GroomDashboard.answer, groom/groom/assets/dashboard.js

A story's book pass starts on a green base. When the base play of the page book is red because of a defect in the book's
surface that is older than the story, the story's QA seat repairs the surface in a commit of its own, before its own
work, and plays the base again before it goes on. A red base caused by the app goes back to the operator, and the seat
repairs nothing in the app.

The first case is the answer to a blocked run's gate. The page shows two toasts for such a run: "worker blocked" when
the run is pushed, and "answer not taken" with groom's reason after the answer is refused. The first one is already on
the page when the answer is sent, so `RunDetail.rejected` names the toast that carries the title "answer not taken", and
the surface waits for that one.
