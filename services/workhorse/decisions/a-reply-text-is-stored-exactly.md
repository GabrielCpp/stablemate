story: workhorse-book
date: 2026-11-12
elements: InboxReply, FileRecord

`inbox reply` stores the text as typed: no trimming, no case change (workhorse/workhorse/inbox.py::reply). The watch declares the strings `go ahead` for either message and `yes` for the second, so a reply of any other text leaves the message holding none of the declared strings. The model keeps exactly that, and does not guess a message's later `inbox read` after an undeclared text.
