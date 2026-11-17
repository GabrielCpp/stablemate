story: none
date: 2026-11-17
elements: AnswerGate, LeaveMessage, ReadInbox, ReadFiles, ReadFile, ReadDiff, ReadOutbox
sources: groom/groom/app.py::_answer, groom/groom/gates.py::answer_gate, groom/groom/app.py::inbox_post, groom/groom/app.py::file_content

A push tells groom a run exists and where it is. It gives groom no run directory, no workspace volume and no
sidecar. So answering a gate of a pushed run is refused with "unknown workspace volume for this container", leaving it
a message is refused with "no run directory yet", its inbox is empty and its files, one file and its change all read
as failed with an empty body. A run groom never heard of is refused first, as "no such run". These are answers with
status 200 or 201 and {ok: false}, so the book writes them as answers and not as rules.

The language of a file read is the grammar the name implies, and it is told even when the read failed, so the model
computes it from the path.
