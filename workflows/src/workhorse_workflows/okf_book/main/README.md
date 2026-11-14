# okf_book main

The python book flow, which writes one service book under `services/<name>/`.

A book reached by a screen surface gets a breadth pass before the owner. The pass lists the entry files the book names nowhere and writes one skeleton screen per entry file, eight per turn. A file handed once is never handed again. The notes of each turn sit under `<run_dir>/breadth/`.

Then the flow runs `check`, then `run`, then `missing`, then renders and commits. A `missing` that lists a file on a book with a screen surface goes through the breadth pass again before the owner. On any other book it sends the owner another lap with the list, like a red `run`. Either waits for the operator after three laps.
