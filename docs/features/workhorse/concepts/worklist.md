---
type: concept
slug: worklist
title: Generic worklist
---
# Generic worklist

The worklist primitive sequences workflow-owned items without knowing the workflow's domain. Items
carry generic `id`, `status`, `kind`, `order`, and `payload` values plus allowed extra fields;
status meanings come from a caller-supplied `Scheme`, and storage comes from a two-method
`Backend`. A `kind` filter lets one store serve several queues without teaching the engine their
names.

- code: `workhorse/workhorse/worklist.py::WorkList`
- tests: `workhorse/tests/test_worklist.py`

## Methods

### method: select_next
- sig: `select_next(items: Iterable[WorkItem], *, skip: Iterable[str] = (), scheme: Scheme = DEFAULT_SCHEME, kind: str | None = None) -> WorkItem | None`
- does: order items by explicit `order` when any item supplies it, otherwise preserve input order
- does: choose an eligible active item before an eligible pending item
- does: skip done, blocked, explicitly skipped, and out-of-scope-kind items
- returns: the next `WorkItem`, or `None` when the scoped queue is drained
- verify: json_path(path="$.id", equals="active-item")
- code: `workhorse/workhorse/worklist.py::select_next`

### method: counts
- sig: `counts(items: Iterable[WorkItem], *, scheme: Scheme = DEFAULT_SCHEME, category_key: str | None = None, kind: str | None = None) -> WorkCounts`
- does: count total, done, active, blocked, pending, and not-done items in scope
- does: count not-done payload categories when `category_key` is supplied
- does: count not-done items by their first-class `kind`
- returns: a `WorkCounts` record
- verify: count(subject="not-done work items in the scoped queue", equals=3)
- code: `workhorse/workhorse/worklist.py::counts`

### method: snapshot
- sig: `snapshot(items: Iterable[WorkItem], *, current: str | None = None, scheme: Scheme = DEFAULT_SCHEME, category_key: str | None = None, kind: str | None = None) -> WorkSnapshot`
- does: package the current item, done/total progress, remaining count, category composition, kind composition, and full counts
- returns: a deterministic in-memory `WorkSnapshot`
- verify: json_path(path="$.progress", equals="1/4")
- code: `workhorse/workhorse/worklist.py::snapshot`

## Methods: WorkList

### method: items
- sig: `WorkList.items(kind: str | None = None) -> list[WorkItem]`
- does: load all backend items or only items of the requested kind
- returns: parsed `WorkItem` values
- code: `workhorse/workhorse/worklist.py::WorkList.items`
- verify: count(subject="items returned for a selected kind", equals=2)

### method: select_next
- sig: `WorkList.select_next(skip: Iterable[str] = (), kind: str | None = None) -> WorkItem | None`
- does: apply the bound scheme, backend, skip set, and kind to the module-level selector
- returns: the next item or `None`
- code: `workhorse/workhorse/worklist.py::WorkList.select_next`

### method: mark
- sig: `WorkList.mark(item_id: str, status: str, kind: str | None = None) -> bool`
- does: update every matching item in the optional kind scope
- does: save only when at least one item matched
- returns: `true` when an item matched, otherwise `false`
- code: `workhorse/workhorse/worklist.py::WorkList.mark`
- verify: persists(subject="marked item status")

### method: prune
- sig: `WorkList.prune(item_id: str, kind: str | None = None) -> bool`
- does: remove matching items in the optional kind scope
- returns: `true` when an item was removed, otherwise `false`
- code: `workhorse/workhorse/worklist.py::WorkList.prune`
- verify: absent(subject="pruned work item")

### method: counts
- sig: `WorkList.counts(kind: str | None = None) -> WorkCounts`
- does: count the backend's current items using the bound scheme and category key
- returns: a `WorkCounts` record
- code: `workhorse/workhorse/worklist.py::WorkList.counts`

### method: snapshot
- sig: `WorkList.snapshot(current: str | None = None, kind: str | None = None) -> WorkSnapshot`
- does: create a snapshot from the backend's current items using the bound scheme and category key
- returns: a `WorkSnapshot` record
- code: `workhorse/workhorse/worklist.py::WorkList.snapshot`

## Types

### field: WorkItem
- type: Pydantic model with extra fields allowed
- default: `id` defaults to `""`
- verify: json_path(path="$.id", equals="")
- default: `status` defaults to `""`
- verify: json_path(path="$.status", equals="")
- default: `kind` defaults to `""`
- verify: json_path(path="$.kind", equals="")
- default: `order` defaults to `None`
- verify: json_path(path="$.order", equals=null)
- default: `payload` defaults to `{}`
- verify: json_path(path="$.payload", equals={})
- required: false for every declared field
- semantics: generic queue item whose workflow-specific extra fields remain top-level on round trip
- code: `workhorse/workhorse/worklist.py::WorkItem`

#### field: id
- type: `str`
- default: `""`
- required: false
- semantics: caller-defined item identifier used by selection, marking, and pruning
- code: `workhorse/workhorse/worklist.py::WorkItem`

#### field: status
- type: `str`
- default: `""`
- required: false
- semantics: caller-defined status interpreted through `Scheme`
- code: `workhorse/workhorse/worklist.py::WorkItem`

#### field: kind
- type: `str`
- default: `""`
- required: false
- semantics: caller-defined list/category discriminator
- code: `workhorse/workhorse/worklist.py::WorkItem`

#### field: order
- type: `int | None`
- default: `None`
- required: false
- semantics: explicit stable ordering value determines selection order when supplied
- verify: json_path(path="$.id", equals="early")
- semantics: when absent, backend sequence order is retained
- verify: unchanged(subject="backend item sequence")
- code: `workhorse/workhorse/worklist.py::WorkItem`

#### field: payload
- type: `dict[str, Any]`
- default: `{}`
- required: false
- semantics: generic nested values used for category counting and other workflow metadata
- code: `workhorse/workhorse/worklist.py::WorkItem`

### field: WorkCounts
- type: frozen record of integer totals and status/category/kind maps
- semantics: count breakdown for one worklist scope
- code: `workhorse/workhorse/worklist.py::WorkCounts`

#### field: total
- type: `int`
- required: true
- semantics: number of items in scope
- code: `workhorse/workhorse/worklist.py::WorkCounts`

#### field: done
- type: `int`
- required: true
- semantics: number of items whose status is in `Scheme.done`
- code: `workhorse/workhorse/worklist.py::WorkCounts`

#### field: active
- type: `int`
- required: true
- semantics: number of items whose status is in `Scheme.active`
- code: `workhorse/workhorse/worklist.py::WorkCounts`

#### field: blocked
- type: `int`
- required: true
- semantics: number of items whose status is in `Scheme.blocked`
- code: `workhorse/workhorse/worklist.py::WorkCounts`

#### field: pending
- type: `int`
- required: true
- semantics: total minus done, active, and blocked counts
- code: `workhorse/workhorse/worklist.py::WorkCounts`

#### field: remaining
- type: `int`
- required: true
- semantics: total minus done count
- code: `workhorse/workhorse/worklist.py::WorkCounts`

#### field: by_status
- type: `dict[str, int]`
- required: true
- semantics: count for every status present in scope
- code: `workhorse/workhorse/worklist.py::WorkCounts`

#### field: by_category
- type: `dict[str, int]`
- required: true
- semantics: not-done item counts keyed by the requested payload category
- code: `workhorse/workhorse/worklist.py::WorkCounts`

#### field: by_kind
- type: `dict[str, int]`
- required: true
- semantics: not-done item counts keyed by item kind
- code: `workhorse/workhorse/worklist.py::WorkCounts`

### field: WorkSnapshot
- type: frozen record containing current, progress, remaining, composition, kinds, and counts
- semantics: dashboard/activity-ready summary held in memory
- code: `workhorse/workhorse/worklist.py::WorkSnapshot`

### field: Scheme
- type: frozen record of `done`, `active`, and `blocked` status sets
- default: `done={"done"}`, `active={"active"}`, `blocked={"blocked"}`
- semantics: maps a workflow's status vocabulary onto selection and counting behavior
- verify: json_path(path="$.pending", equals=1)
- semantics: all other statuses are pending
- verify: json_path(path="$.id", equals="todo")
- code: `workhorse/workhorse/worklist.py::Scheme`

### field: Backend
- type: protocol with `load() -> list[WorkItem]` and `save(items: Sequence[WorkItem]) -> None`
- semantics: storage port owned by the workflow or by the built-in JSON adapter
- code: `workhorse/workhorse/worklist.py::Backend`

### field: JsonBackend
- type: dataclass with `path: Path` and `items_key: str = ""`
- semantics: atomically reads and writes a bare JSON array or an item list nested under `items_key`, preserving sibling metadata
- code: `workhorse/workhorse/worklist.py::JsonBackend`

## Methods: Backend

### method: load
- sig: `Backend.load() -> list[WorkItem]`
- does: return the current stored items as validated `WorkItem` values
- returns: a list of work items
- code: `workhorse/workhorse/worklist.py::Backend.load`

### method: save
- sig: `Backend.save(items: Sequence[WorkItem]) -> None`
- does: persist the supplied item sequence as the backend's current contents
- returns: `None`
- code: `workhorse/workhorse/worklist.py::Backend.save`

## Methods: JsonBackend

### method: load
- sig: `JsonBackend.load() -> list[WorkItem]`
- does: return an empty list for a missing file
- does: read a bare array or the configured object member and validate each row
- returns: parsed `WorkItem` values
- code: `workhorse/workhorse/worklist.py::JsonBackend.load`
- verify: count(subject="items loaded from the JSON backend", equals=4)

### method: save
- sig: `JsonBackend.save(items: Sequence[WorkItem]) -> None`
- does: write only fields set on each item, preserving workflow-owned extra fields
- does: preserve sibling object metadata when `items_key` is configured
- does: replace through a temporary file so readers never observe a partial JSON document
- returns: `None`
- code: `workhorse/workhorse/worklist.py::JsonBackend.save`
- verify: persists(subject="JSON worklist after an atomic save")
