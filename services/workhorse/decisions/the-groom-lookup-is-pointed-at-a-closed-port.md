story: workhorse-book
date: 2026-11-12
elements: Run

The runner asks the groom service about the story it works on. The sandbox sets GROOM_URL to http://127.0.0.1:9, a port nothing listens on, so the lookup fails the same way in every world and the machine's own groom does not answer. HOME and STABLEMATE_CONFIG point inside the sandbox for the same reason: the home config is a file the seed writes (`config_version = 2`), so no profile, workspace or backend list comes from the person running the book.
