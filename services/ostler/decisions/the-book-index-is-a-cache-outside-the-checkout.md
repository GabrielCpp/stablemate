story: none
date: 2026-11-23
elements: IndexBook, SearchBook, CheckBook
sources: ostler/ostler/book/index.py, ostler/ostler/book/check.py::refresh_index

`ostler book search` keeps its index of a book in the user cache, not in the book. The index is derived from the book,
so a tracked copy gave every two story branches that changed one book a conflict on `index.tsv` at each landing and at
each review merge. A tool also writes no output into a checkout.

The index of a book folder is `<cache>/book-index/<sha256 of the folder's resolved absolute path, first 16 hex>.tsv`,
where `<cache>` is the shared stablemate cache folder (`$XDG_CACHE_HOME/stablemate`, or `~/.cache/stablemate`). Two book
folders that share a module name hold two files. A file is fresh while it exists and is newer than the newest `.py` or
`.md` under the book folder and than every folder under it, so a deleted or renamed file also makes it stale. The index
holds the decisions with the rest, and a search reads no other file of the book. A search decodes only the rows that
hold one of its words, which keeps it near two seconds on a 140 MB index (measured 2026-11-24). The first search after a change rebuilds it, which takes about four seconds on a 550 KB
index (measured 2026-11-23), and writes it through a sibling temporary file and a rename. A cache folder that cannot be
written does not break search, which then builds in memory on every call.

`ostler book index` stays as a command and prints `<cache path>: changed` or `<cache path>: unchanged`. `ostler book
check` refreshes the same file and reports no finding for it, so its exit code does not depend on the index. A leftover
`index.tsv` in a book folder is read by nothing, `ostler book move` deletes it, and the repository ignores
`services/**/index.tsv`. Nothing is committed and there is nothing to run.
