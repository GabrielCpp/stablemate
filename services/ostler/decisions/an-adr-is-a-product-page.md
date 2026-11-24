---
story: none
date: 2026-11-24
elements: Doctor, BacklogList
sources: ostler/ostler/doctor.py, ostler/ostler/model.py::doc_roots
---

An architecture decision is a page of the product book, or a decision of a service book. Ostler keeps no separate store for it.

The doctor no longer checks an `adr.md` shelf, and the graph names no `adrs` document root. A record filed before the decision field went still loads, because the loader ignores the key.
