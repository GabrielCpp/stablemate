story: none
date: 2026-11-23
elements: Runs
sources: groom/groom/app.py::_refresh_figures, groom/groom/figures.py::run_figures, groom/groom/store.py::run_row_profile

Each committed span batch refreshes the figures of the runs it touched. One pass per run runs at a time, and batches that land during it fold into one rerun. The pass reads only the columns and attributes the row shows. groom adds no settle delay, so the figures stay as fresh as the run list. The figures are not folded incrementally, because active time is a sweep over every span and a resume can reorder it.
