story: none
date: 2026-11-16
elements: Tags, TagSecret, UntagSecret, Meta, Unmeta

A tag is a key and a value, and a secret carries a set of them, so tagging twice with one pair keeps one and untagging a pair
the secret lacks does nothing (saddlebag/saddlebag/verbs.py, verb_tag and verb_untag). `list` and `tags` print them
sorted. Metadata is a map of printable values: `meta` overwrites a key and refuses one given twice in the same call, and
`unmeta` refuses a key the secret lacks, checking each key in turn (verb_meta, verb_unmeta). A tag or a metadata pair
that is not key=value is refused by the command line with exit 2, before any request is made (cmd_tag, cmd_meta).
