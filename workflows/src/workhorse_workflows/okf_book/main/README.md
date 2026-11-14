# okf_book main

The python book flow, which writes one service book under `services/<name>/`.

The flow runs `check`, then `run`, then `missing`, then renders and commits. A `missing` that lists a file sends the owner another lap with the list, like a red `run`, and waits for the operator after three laps.
