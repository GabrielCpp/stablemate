# What a list on a screen holds

Status: proposed, not built. Written with the decompose order. I had read the book runtime
before writing it, so every part and concept below was checked against the test "would I
have named this without having seen the code".

## 1. Problem

A person hunting bugs on a web or mobile screen looks at its lists: a dropdown, an
autocomplete, a group of radio buttons, a second table, the fields of a generated form. They
ask whether the list holds what it should. Today the book names such a list and says nothing
a run can check about its content. A dropdown that offers the sender as a recipient, leaves
out the project made a minute ago, shows another customer's record, sorts wrongly or repeats
an entry passes every run. Where a book says anything about it, it is prose in a decision
file.

Three facts of the domain shape the answer:

- **An environment is shared and never wiped.** A list holds records other people and other
  runs made. Nobody can state its whole content ahead of the run, and nothing guarantees an
  account that holds test data only.
- **A list is filled in one of four ways.** Its entries are fixed in the app's code. They
  come from an answer the page received. They come from data the page's own server fetched
  before sending the page. Or the page computes them from data it got one of those ways.
- **A run knows two things for sure.** It knows the records it made itself, with the ids the
  app gave them. It can know the data the page was given in this run, when it can see it.

Done, as that person sees it:

- For each list a screen shows from data, the book says what it holds, in a form `search`
  and `explain` show.
- A run reads the list when a user would see it and reports a difference, on an environment
  full of other people's data.
- A run's report names every list a screen declares and no run checked. A green run cannot
  hide them.
- On the client's web book, the seven list claims written today as prose are each a check,
  and putting the sender back among the recipients turns the run red.

Out of scope:

- Whether the backend's answer is right for records the run did not make. The backend's own
  book proves the same read on the records it made.
- A long list that renders only the entries scrolled into view (A4).
- What a list looks like, and how long its data takes to arrive.

## 1b. Claims that reached this note

1. "The rows a page shows are compared with the model's rows, and they must be equal." The
   web runtime does this today for the one main list of a book.
2. "A list is read as containing: it is compared only on the entries whose ids the book
   learned." The book skill says this for the answers of an HTTP or gRPC service.
3. "A dropdown with a fixed list gives its choices in `options=`." The screen format.
4. "A dropdown states its entries as a read on the model, compared exactly when the run made
   every record in scope." My own earlier proposal.

## 2. Parts and concepts

### Level 1: parts

| Part | Owns | Never knows | Hands over |
|---|---|---|---|
| The statement | what the book claims a list holds | the environment's data, how the page gets its data | the claims, to the judgement |
| The evidence | what a run can know for sure at the moment a list is seen | whether the list is right | the run's own records, the data the page was given, the entries shown |
| The judgement | whether the entries shown agree with each claim | how any evidence was obtained | a verdict per list |
| The account | which lists were stated, read and judged, by name | how a claim is judged | the lines of the run's report and of `check` |

Flow. The author writes the statement once per list. When a run reaches the moment a user
would see the list, the evidence is gathered: what the run made, what the page was given, what
the screen shows. The judgement compares. The account says, per list, which claims held, and
which lists nobody stated or no run reached.

### Level 2: concepts

**The statement**

| Concept | Owns | Never knows |
|---|---|---|
| List | that one component of a screen repeats one entry per record, and what an entry shows of its record | where the records come from |
| Belonging | which records belong in the list for the person looking, as a read on the model | records the model does not hold |
| Derivation | how the entries follow from the data the page was given | the model |
| Entry rule | a property of the entries shown whatever they are: their order, no repeat, which one is picked first | where an entry came from |

**The evidence**

| Concept | Owns | Never knows |
|---|---|---|
| Own records | the records this run made, with the id the app gave each | records anyone else made |
| Feed | the data the page was given for one list, in this run | what the list should hold |
| Reading | the entries a list shows now, in order, with what identifies each | what they should be |

**The judgement**

| Concept | Owns | Never knows |
|---|---|---|
| Containing check | each own record is shown when it belongs and absent when it does not | entries the run did not make |
| Derivation check | the reading equals the derivation applied to the feed | the model |
| Rule check | each entry rule holds over the reading | the model and the feed |

**The account**

| Concept | Owns | Never knows |
|---|---|---|
| Coverage | per list: stated or named only, read or never reached, which claims were judged | how a claim is judged |

Belonging, derivation and entry rules are three claims a list may state in any combination.
Each is judged alone. None needs the whole list to be known ahead of the run.

## 3. Invariants

| Invariant | Owner |
|---|---|
| No check compares a list's whole content with the book's own records. | Containing check |
| An entry the run did not make never fails belonging. | Containing check |
| The derivation check uses the data of this run and keeps none between runs. | Feed |
| A list is read at an event (the pick, the screen showing), never after a wait of fixed length. | Reading |
| A list with no claim, or one no run reached, is named in the report as unchecked. | Coverage |
| A book that states nothing about its lists behaves as it does today. | Coverage |

## 4. Forces and patterns

Forces:

- F1. The environment's data is unknown and shared.
- F2. How a list is filled varies per list: fixed, received by the page, fetched by the
  page's server, computed in the page.
- F3. What a run can see varies per surface. A browser sees the answers a page receives. A
  phone run sees the screen only.
- F4. How a list is drawn varies: a native select, a popup of options, radio buttons, table
  rows, form fields.
- F5. Which claims an author can make varies per list.
- F6. Two records can show the same label.
- F7. The model moves before the page does in a step, and the list a user picks from is the
  one from before the step.

Between parts: one value handed along. The statement is data on the screen declaration. The
evidence is gathered at the moment of reading. The judgement is a plain comparison.

Inside parts:

- F1 gives the containing check its shape: compare on own records only. No mode says "this
  environment is clean". One behaviour holds everywhere, a clean stack included.
- F2 and F3 make the feed a role with two variants. One takes the answer the page received,
  named by the request it answers. The other asks the backend the same read as the same
  person, through the backend's book, for a page whose server fetched the data or for a
  phone. The list's statement chooses the variant.
- F4 makes the reading a role with one variant per way a list is drawn. The component's kind
  chooses it.
- F5 keeps the three claims independent and optional. A plain value with three optional
  parts is enough.
- F6 identifies an entry by the id the app gave its record when the list exposes it, and by
  its label otherwise. A label two own records share is reported, since the claim cannot be
  read for them.
- F7 means what should belong is taken from the model before the step moves it.

Claims from 1b:

1. Equality of the main list with the model: not re-derived. F1 rejects it for a shared
   environment. It stays for the books that reset their app, and this design does not touch
   it (5b).
2. A list is read as containing: re-derived from F1. It is the containing check.
3. `options=` for a fixed list: kept. A fixed list is the first way of F2 and needs no claim.
4. Exact comparison with the book's records: rejected by F1.

SOLID check. Each concept owns one thing. A new way to draw a list adds one reading variant
and one line where the kind is matched. A new place to get the feed adds one feed variant.
The judgement names neither variant.

Open lookups:

- L1. How many of the client's web lists are native selects, and how many are popups.
- L2. Whether the lists at work are filled by a request the browser makes, or rendered by the
  page's server (A1).

## 5. Mapping onto the existing system

Revision log:

- Section 6, slice order. L1 found that the client's web app draws its dropdowns as popups
  in 9 files and as native selects in 2. The popup slice moved from fourth to second.

Lookups resolved. L1: see the log. L2, for the client's web app: no page loads its data on
the server, so every list there is fed by a request the browser makes. L2 for the apps at
work stays open as A1.

| Item | Verdict | Where |
|---|---|---|
| List | Reshape | A component has `options` and `per_row` (`ostler/ostler/book/screen.py`). It has no place for a claim. The statement becomes one keyword on a component, by name, beside `options=`. |
| Belonging, derivation, entry rule | New | A small value in `screen.py`, with each claim a named function whose first docstring line is what `describe`, `search` and `explain` print. |
| Own records | Exists | The model, and the ids a surface learns from the app's answers. The HTTP runtime already drops list entries whose id it never learned (`http.py`, `canonical`). |
| Feed, from the page's answer | Reshape | The browser records requests (`taken`) and can wait for one answer (`answered`). It does not keep the last answer to a request named ahead of time. |
| Feed, by asking the backend | New | A web book can already import a backend book's calls, as it does for an outside event. |
| Reading | Reshape | `offered` reads a native select only, and by option value. The client's surface clicks popup options by hand. A phone run has no reader for a list. |
| Containing, derivation and rule checks | New | Beside the row comparison in `runner.py`. |
| Coverage | New | In the run's report and in `check`, as findings that do not block. |

When a list is read. The browser's `fill` already reads what a select offers before it
picks, to refuse a value the select does not offer. That is the moment a user sees the list.
So a pick in a stated list is judged at the pick, and the surface's author writes nothing
more. A list no journey picks from gets an explicit read the surface can call. A list no
run reads is named in the report.

The author's lines, for a list computed in the page from data it received:

```python
def collections(products):
    """the distinct collections of the products received, by name"""
    return sorted({p["collection"] for p in products})

collection = Select(None, T(en="Collection", fr="Collection"), "filters the products",
                    lists=Lists(given=request("GET", "/products"), derived=collections))
```

And for a list of the caller's own records:

```python
def open_projects(model, by):
    """the projects the caller may send, the archived ones left out"""
    return [p for p in model.projects if p.owner == by.handle and not p.archived]

project = Select(None, T(en="Project", fr="Projet"), "which project to send",
                 lists=Lists(of=Project, belongs=open_projects, order="name", first=FIRST))
```

What the existing system has that the design lacks: the exact comparison of the main list
with the model. It is not waste. It is the stronger check where a book resets its app, and
this design leaves it in place.

Mismatch found: the web runtime's main list is compared for equality while the skill tells
every book that the app is never wiped. A web book holds on a shared environment only when
its surface returns the rows it tracks itself. The design does not fix that. It is recorded
as A7.

A derivation may also read who is looking, as its second argument, for a list such as "every
user received except the caller".

## 5b. What must not move

| Receiver | Gets today | Enforced by | Before | Holds when |
|---|---|---|---|---|
| A book that states nothing | `check` exits 0 and its index is unchanged | the index comparison in `check` | 0 findings on the fixture books and the five client books | still 0 blocking findings, index byte-identical |
| A surface that picks in a native select | a `CannotReach` when the value is not offered | `test_book_web.py` | passes | passes unchanged |
| The main list comparison | equality of the page's rows with the model's | `test_book_web.py` | passes | passes unchanged |
| A person waiting on a run | the web fixture's run time | nothing | not measured, taken in slice 1 | within 10 percent |

## 6. Slices

1. **A derived list is judged at the pick.** The fixture web app gains a dropdown computed
   from data the page fetched. Its book states the derivation. The run reads the list when a
   journey picks in it and compares. A copy of the app that sorts wrongly turns the run red.
   The report names each list as stated and read, or named only. Touches: list, derivation,
   feed from the page's answer, reading of a native select, derivation check, coverage.
   Done when the red and green runs show it and every row of 5b holds.
2. **A popup of options.** `fill` and the reading work on a list drawn as a popup. The
   client's web book states the derivation of the lists its prose claims describe. Done when
   the sender put back among the recipients turns that book's run red.
3. **A record the run made is offered, and gone when it should be.** Belonging, own records,
   the containing check, with what belongs taken before the model moves. Done when the
   fixture shows a made record offered, a removed one gone, and another person's never
   offered, with rows the run did not make present in the list.
4. **Rules over every entry, and the lists nobody stated.** Order, no repeat, first pick.
   `check` names each list a screen declares with no claim. Done when each rule has a red
   and a green run and `check` prints the names without failing.
5. **Data the browser never saw, and the phone.** The feed asked of the backend through its
   book. A reader for a list on a phone. Done on a server-rendered page of the client's app
   and on one list of the mobile book.
6. **The fields of a generated form.** An entry is a field with its label and its kind. Done
   on the client's staged form.
7. **The writers.** The skill and the book workflow's breadth pass state a list's claims
   from the app's source. Done when a workflow run on the client's web book writes them.

## 7. Assumptions

- A1. **Assumption:** most lists are filled by a request the browser makes. **Decided:**
  the feed read from the page's answer comes first, and asking the backend waits for slice 5.
  **Basis:** none for the apps at work. **If wrong:** slice 5 moves ahead of slice 2.
- A2. **Assumption:** a run can tell its own records apart in a list, by the id the list
  exposes or by a label only the run uses. **Decided:** F6. **Basis:** the web surfaces
  already find a row by the id the app gave. **If wrong:** belonging is unreadable for lists
  that expose no id, and only derivation and rules apply there.
- A3. **Assumption:** reading a list when a journey picks in it reaches most lists.
  **Decided:** no separate walk over every list of every screen. **Basis:** none. **If
  wrong:** coverage names many lists as never read, and a walk becomes its own slice.
- A4. **Assumption:** an opened list renders all its entries. **Decided:** long lists that
  render on scroll are out of scope. **Basis:** none. **If wrong:** the reading must search
  or scroll, in slices 2 and 5.
- A5. **Assumption:** stating a page's computation again in the book is acceptable, since it
  is what the user should see. **Decided:** the derivation is a function in the book.
  **Basis:** the model already restates the backend's rules the same way.
- A6. **Assumption:** data asked of the backend a moment after the page got it is the same
  data. **Decided:** asking suits lists that change slowly. **Basis:** none. **If wrong:**
  a busy shared list gives false failures, and that list keeps only belonging and rules.
- A7. **Assumption:** the equality check of a web book's main list can stay as it is for
  now. **Decided:** untouched here. **Basis:** the fixture resets its app, and the
  client's surface builds its rows from what it tracked.
  **If wrong:** the main list moves to the containing check, which is a migration of every
  web and mobile book.
