story: none
date: 2026-11-16
elements: Exec

The README says a `NAME.totp` binding gives the current six-digit code. The app hands the stored seed
(saddlebag/saddlebag/verbs.py, verb_env, reads the value as stored; only `_typable` computes the code, for fill and
type). The code changes every thirty seconds, so no book claim can name it, and the book never binds a stored seed
under exec. It plays a totp binding only where the secret holds no seed. See DISAGREEMENTS 1.
