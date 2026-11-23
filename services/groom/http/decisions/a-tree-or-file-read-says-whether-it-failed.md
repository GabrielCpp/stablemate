story: SM-01M6CP89MHPC9GSEGDMHD2C690
date: 2026-11-23
elements: ReadFiles, ReadFile
sources: groom/groom/sidecar.py, groom/groom/docker_io.py, groom/groom/localfs.py, groom/groom/app.py

A caller that lists a run's checkout or reads one of its files must tell an empty result from a read that did not happen, so each reply says which it was. A tree walk that cannot enter a folder fails the whole read, because a partial listing would claim a checkout without files it has. A checkout that is missing fails it too. A file that is missing or unreadable fails its read, and an empty file does not.

The sidecar's `getTree` and `getFile` keep `paths` and `content` and add `failed` beside them, so a consumer that reads only those, such as the terminal client, keeps working. The Docker volume reader and the local disk reader report `failed` the same way. The `/files/` and `/file/` replies add `reported`, which is false when the sidecar sent no `failed`, and `served`, which names the reader that answered, `sidecar` or `volume`. An empty answer with `reported` false comes from a sidecar too old to report failure, so it cannot confirm the checkout has no files or the file is empty.

A sidecar asked for an empty `repo` reads the first checkout the diff read finds, so Files and Diff show the same checkout.

This extends `a-pushed-run-has-no-workspace`, which has a read with no volume and no sidecar answer as a failed read. It sits beside `a-diff-read-says-whether-it-failed`.
