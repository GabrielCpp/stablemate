story: track50
date: 2026-11-11
elements: Install

install prints "Updated .agents .gitignore rules" when it changes the ignore file (farrier/farrier/outputs.py:696-697),
"Wired `make farrier-run-hook` into ..." when it wires the hook (the hook manager lines at outputs.py:703-705) and
"Added agent launcher include to root Makefile" when it appends to an existing Makefile (outputs.py:706-707).
Each is printed once and not again, so the line depends on whether the repository already held the result of an
earlier run. The model keeps the files, not those histories, so the answer leaves the three lines out of the
comparison. The files they describe are still watched.
