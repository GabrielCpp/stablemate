story: none
date: 2026-11-16
elements: Remove

`secret remove` deletes the record and both stored values with no confirmation, and says no such secret for a name the store
does not hold (saddlebag/saddlebag/verbs.py, verb_remove, and keyring_store.py, remove). A person who wants the name back
creates it again with no value.
