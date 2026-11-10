---
type: concept
slug: cells-share-an-arrangement
title: Cells of a scene share an arrangement
---
# Cells of a scene share an arrangement

A scene of a lifecycle matrix is arranged by the steps that reach it, which cost calls to the service. A run plays the cells of one scene in the order of the matrix's actions. A cell that passes and leaves the model's state as it was hands its arrangement to the next cell of the scene, so the reads of one scene are taken on one arrangement. A cell that changes the model does not hand it on, and the next cell arranges the scene again.

The run reports the cells played, the arrangements they took and, for an exploration, the arrangements shared by cells that change nothing. A cell the matrix marks impossible is not played, and it leaves the arrangement as it was.

- code: ostler/ostler/book/cells.py::play@002f27654e76
- code: ostler/ostler/book/cells.py::one@655a8b6469b4
- code: ostler/ostler/book/state.py::Impossible@3277124f4c07
- code: ostler/ostler/book/exploration.py::play@379c76657054
- rule: cells of one scene share an arrangement while the cell before changed nothing
- rule: a cell that changes the model, fails or carries a known defect ends the arrangement, and the next cell arranges its scene again
- rule: a cell the matrix marks impossible needs a reason and is never played
- rule: an action that builds to nothing where the pair is not impossible fails its cell, so the matrix says `Impossible` with a reason and never leaves a blank
- tests: ostler/tests/test_book_cells.py::test_two_read_cells_of_one_scene_share_an_arrangement
- tests: ostler/tests/test_book_cells.py::test_a_cell_that_changes_the_model_does_not_hand_it_on
- tests: ostler/tests/test_book_cells.py::test_a_read_after_a_read_keeps_the_arrangement_a_write_after_it_ends
