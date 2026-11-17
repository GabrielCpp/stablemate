story: none
date: 2026-11-17
elements: AnswerTheGate, RunDetail, OpenRun
sources: groom/groom/assets/dashboard.js, groom/groom/app.py::_handle_command, groom/groom/gates.py::answer_gate

The detail pane of a blocked run holds the gate it waits on and a box for the answer. The answer travels over the
dashboard socket, and groom writes it into the gate file of the run's workspace. A pushed run has no workspace, so
groom refuses and the page shows a notice, "answer not taken", with the reason groom gave. The page's refusal is the
same sentence the HTTP book's AnswerGate gives for the same run, so the page book states it as one rule and the notice
carries its last line.
