story: none
date: 2026-11-17
elements: CheckBook, IndexBook
sources: ostler/ostler/book/tree.py, ostler/ostler/book/check.py::itself_faults, a34829091

A book declares a tree, such as a formula of formulas, as one named object whose fields hold `Itself("Name")`, and
the object replaces the placeholder when it is built. `ostler book check` reads every shape an endpoint declares,
in its path, query, headers, body and answers, and reports each `Itself` that names no enclosing object with the
path of the field that holds it. A shape that holds itself is loaded by `check` and `index` alike, so both run the
same code that resolves it. The sandbox's demo book declares no tree, so its check reports no finding.
