story: workhorse-book
date: 2026-11-12
elements: Control, InboxRead

A rewind prints `  backup:  <path>` and the path carries a time stamp, so the line is opaque and the model does not say it. Every `inbox read` header (`[m1] <time> (outstanding)`) is opaque for the same reason: a reply stamps its message with the time of the reply, and the header shows it. The body lines and the `  -> reply` lines are compared. The `replied` marker of a header is therefore not judged; whether a message is answered is judged by the reply line and by the inbox file the watch reads.
