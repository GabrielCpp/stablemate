# Cells whose intent no source settles

1. `ostler set-status STORY STATUS`: the status is free text. `set_status` (`ostler/ostler/crud.py:453-468`)
   writes any string into the frontmatter, quoting it when it holds a colon, and the repository's registry names no
   list of story statuses. An empty status is accepted too. The book plays the three statuses `Not started`,
   `In progress` and `Blocked: waiting` and refuses nothing else. It does not say whether `Done` or an empty
   status is meant to be allowed.

2. `ostler conflict STORY --clear` on a story with no conflict recorded: the source answers success with
   `conflict cleared off '<id>'` and changes nothing. Nothing says whether that should be a refusal. The book
   plays it as the success the tool gives.
