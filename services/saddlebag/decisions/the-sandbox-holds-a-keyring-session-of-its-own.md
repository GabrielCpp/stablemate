story: none
date: 2026-11-16
elements: SecretRecord, Create, SetValue, Doctor

saddlebag keeps a secret's value in the OS keyring and its record in a catalogue file under the state directory
(saddlebag/saddlebag/keyring_store.py, catalogue.py). It refuses any keyring that is not the Secret Service or the macOS
Keychain, so a sandbox with no desktop session answers every verb with "no OS keyring on this session"
(keyring_store.py, open_door).

The book therefore starts a message bus and gnome-keyring-daemon for each world, unlocks the login keyring, and
hands the sandbox the bus address. The catalogue sits under the sandbox's home, so a world holds its own records, and
the keyring is thrown away with the world, so no value outlives it. The sandbox runs the real app against a real
keyring and no stand-in for either.

The sandbox's PATH holds the directory of the saddlebag program and the system directories, and no adb. A person's
machine may have one, and `type` would then reach a device the claim never arranged.
