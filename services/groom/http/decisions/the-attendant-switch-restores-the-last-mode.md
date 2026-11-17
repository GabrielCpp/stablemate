story: none
date: 2026-11-17
elements: ReadAttend, SetAttend
sources: groom/groom/app.py::attend_settings_post, groom/groom/settings.py

The attendant has three modes, off, session and headless, and the settings pane offers one switch. Turning it on
restores the last mode that was on, headless when none was, and turning it off keeps that last mode for the next
time. The book's groom has a home config that names no mode, so on is headless. Any value of the switch but true
turns the attendant off, as DISAGREEMENTS 2 records. Where the cli, the deny list and the sources of each setting come
from is the environment's config, so the book compares none of them.
