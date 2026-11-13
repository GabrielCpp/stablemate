# Cells whose intent no source settles

1. `ostler set-status STORY STATUS`: apart from the empty status, which `decisions/an-empty-status-is-refused.md`
   refuses, the status is free text. `set_status` (`ostler/ostler/crud.py`) writes any other string into the
   frontmatter, quoting it when it holds a colon, and the repository's registry names no list of story statuses.
   The book plays the four statuses `Not started`, `in-progress`, `Blocked: waiting` and `Done`. It does not say
   whether a fixed list of statuses should exist.

2. `ostler conflict STORY --clear` on a story with no conflict recorded: the source answers success with
   `conflict cleared off '<id>'` and changes nothing. Nothing says whether that should be a refusal. The book
   plays it as the success the tool gives.
