story: none
date: 2026-11-16
elements: Serve, Inventory, Doctor

`saddlebag serve` runs until a signal, and past its checks it needs a reachable Vault. The book plays the checks that
end it: no address, no token on stdin, and keeping a token in the keyring (cmd_serve, custody.py). A valid token with an
address reaches a Vault the sandbox lacks, and the app then dies with a traceback (DISAGREEMENTS 2), so no claim names it.

A person's preference for the daemon is a line in the home config (saddlebag/saddlebag/preference.py). With it set, every
verb is sent to the daemon's socket, and with none listening each says where it looked. The book plays that refusal and
never a served verb.
