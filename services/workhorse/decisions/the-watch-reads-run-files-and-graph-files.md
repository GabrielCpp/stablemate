story: none
date: 2026-11-17
elements: Look, FileRecord

After every step the book reads the files a command may write: the checkpoint, run record, event log and inbox of each run under `.agents/runs` or beside it, and any `.dot` file `dot -o` leaves. A row holds only which of the declared strings a file contains, never its whole text, because the files carry time stamps and run digests that differ in every world. `Look` names the two writers whose effect the strings judge, the rewind that rewrites a checkpoint and logs its backup (workhorse/workhorse/rewind.py) and the reply that stamps an inbox message (workhorse/workhorse/inbox.py).
