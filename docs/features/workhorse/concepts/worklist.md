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
- verify: json_path(path="$.id", equals="c")
- returns: the next item or `None`
- verify: json_path(path="$.id", equals="c")
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
- verify: json_path(path="$.by_kind.story", equals=2)
- returns: a `WorkCounts` record
- verify: json_path(path="$.by_status.done", equals=1)
- code: `workhorse/workhorse/worklist.py::WorkList.counts`

### method: snapshot
- sig: `WorkList.snapshot(current: str | None = None, kind: str | None = None) -> WorkSnapshot`
- does: create a snapshot from the backend's current items using the bound scheme and category key
- verify: json_path(path="$.progress", equals="1/4")
- returns: a `WorkSnapshot` record
- verify: json_path(path="$.current", equals="c")
- code: `workhorse/workhorse/worklist.py::WorkList.snapshot`

## Types

### field: WorkItem
- type: Pydantic model with extra fields allowed
- default: `id` defaults to `""`
- verify: json_path(path="$.id", matches="^$")
- default: `status` defaults to `""`
- verify: json_path(path="$.status", equals="")
- default: `kind` defaults to `""`
- verify: json_path(path="$.kind", equals="")
- default: `order` defaults to `None`
- verify: json_path(path="$.order", matches="^None$")
- default: `payload` defaults to `{}`
- verify: json_path(path="$.payload", matches="^\\{\\}$")
- required: false for every declared field
- verify: json_path(path="$.status", absent=true)
- semantics: generic queue item whose workflow-specific extra fields remain top-level on round trip
- verify: keys_unchanged(subject="workflow-specific extra fields on a WorkItem round trip")
- code: `workhorse/workhorse/worklist.py::WorkItem`
- detail: [work item fields](work-item-fields.md)

#### field: id
- type: `str`
- default: `""`
- verify: json_path(path="$.id", equals="")
- required: false
- verify: json_path(path="$.id", absent=true)
- semantics: caller-defined item identifier used by selection, marking, and pruning
- verify: json_path(path="$.id", equals="selected-item")
- code: `workhorse/workhorse/worklist.py::WorkItem`
- detail: [work item fields](work-item-fields.md)

#### field: status
- type: `str`
- default: `""`
- verify: json_path(path="$.status", equals="")
- required: false
- verify: json_path(path="$.status", absent=true)
- semantics: caller-defined status interpreted through `Scheme`
- verify: count(subject="items with statuses in Scheme.active", equals=1)
- code: `workhorse/workhorse/worklist.py::WorkItem`
- detail: [work item fields](work-item-fields.md)

#### field: kind
- type: `str`
- default: `""`
- verify: json_path(path="$.kind", equals="")
- required: false
- verify: json_path(path="$.kind", absent=true)
- semantics: caller-defined list/category discriminator
- verify: json_path(path="$.kind", equals="story")
- code: `workhorse/workhorse/worklist.py::WorkItem`
- detail: [work item fields](work-item-fields.md)

#### field: order
- type: `int | None`
- default: `None`
- verify: json_path(path="$.order", absent=True)
- required: false
- verify: json_path(path="$.order", absent=True)
- semantics: explicit stable ordering value determines selection order when supplied
- verify: json_path(path="$.id", equals="early")
- semantics: when absent, backend sequence order is retained
- verify: unchanged(subject="backend item sequence")
- code: `workhorse/workhorse/worklist.py::WorkItem`
- detail: [work item fields](work-item-fields.md)

#### field: payload
- type: `dict[str, Any]`
- default: `{}`
- verify: json_path(path="$.payload", matches="^\\{\\}$")
- required: false
- verify: json_path(path="$.payload", absent=true)
- semantics: generic nested values used for category counting and other workflow metadata
- verify: json_path(path="$.payload.cat", equals="ui")
- code: `workhorse/workhorse/worklist.py::WorkItem`
- detail: [work item fields](work-item-fields.md)

### field: WorkCounts
- type: frozen record of integer totals and status/category/kind maps
- semantics: count breakdown for one worklist scope
- verify: json_path(path="$.by_status.done", equals=1)
- verify: json_path(path="$.by_status.blocked", equals=1)
- verify: json_path(path="$.by_status.pending", equals=2)
- code: `workhorse/workhorse/worklist.py::WorkCounts`
- detail: [work counts fields](work-counts-fields.md)

#### field: total
- type: `int`
- required: true
- verify: json_path(path="$.total", equals=4)
- semantics: number of items in scope
- verify: count(subject="items in the scoped queue", equals=4)
- code: `workhorse/workhorse/worklist.py::WorkCounts`
- detail: [work counts fields](work-counts-fields.md)

#### field: done
- type: `int`
- required: true
- verify: json_path(path="$.done", equals=1)
- semantics: number of items whose status is in `Scheme.done`
- verify: count(subject="items whose status is in Scheme.done", equals=1)
- code: `workhorse/workhorse/worklist.py::WorkCounts`
- detail: [work counts fields](work-counts-fields.md)

#### field: active
- type: `int`
- required: true
- verify: json_path(path="$.active", equals=1)
- semantics: number of items whose status is in `Scheme.active`
- verify: count(subject="items with statuses in Scheme.active", equals=1)
- code: `workhorse/workhorse/worklist.py::WorkCounts`
- detail: [work counts fields](work-counts-fields.md)

#### field: blocked
- type: `int`
- required: true
- verify: json_path(path="$.blocked", equals=1)
- semantics: number of items whose status is in `Scheme.blocked`
- verify: count(subject="items with statuses in Scheme.blocked", equals=1)
- code: `workhorse/workhorse/worklist.py::WorkCounts`
- detail: [work counts fields](work-counts-fields.md)

#### field: pending
- type: `int`
- required: true
- verify: json_path(path="$.pending", equals=2)
- semantics: total minus done, active, and blocked counts
- verify: count(subject="pending items in the scoped queue", equals=2)
- code: `workhorse/workhorse/worklist.py::WorkCounts`
- detail: [work counts fields](work-counts-fields.md)

#### field: remaining
- type: `int`
- required: true
- verify: json_path(path="$.remaining", equals=3)
- semantics: total minus done count
- verify: json_path(path="$.remaining", equals=3)
- code: `workhorse/workhorse/worklist.py::WorkCounts`
- detail: [work counts fields](work-counts-fields.md)

#### field: by_status
- type: `dict[str, int]`
- required: true
- verify: json_path(path="$.by_status.done", equals=1)
- semantics: count for every status present in scope
- verify: json_path(path="$.by_status.done", equals=1)
- verify: json_path(path="$.by_status.blocked", equals=1)
- verify: json_path(path="$.by_status.pending", equals=2)
- code: `workhorse/workhorse/worklist.py::WorkCounts`
- detail: [work counts fields](work-counts-fields.md)

#### field: by_category
- type: `dict[str, int]`
- required: true
- verify: json_path(path="$.by_category.ui", equals=1)
- semantics: not-done item counts keyed by the requested payload category
- verify: count(subject="by_category", equals=2)
- verify: json_path(path="$.by_category.ui", equals=1)
- verify: json_path(path="$.by_category.api", equals=2)
- code: `workhorse/workhorse/worklist.py::WorkCounts`
- detail: [work counts fields](work-counts-fields.md)

#### field: by_kind
- type: `dict[str, int]`
- required: true
- verify: json_path(path="$.by_kind.epic", equals=1)
- semantics: not-done item counts keyed by item kind
- verify: json_path(path="$.by_kind.epic", equals=1)
- verify: json_path(path="$.by_kind.story", equals=2)
- verify: json_path(path="$.by_kind.fix", equals=1)
- code: `workhorse/workhorse/worklist.py::WorkCounts`
- detail: [work counts fields](work-counts-fields.md)

### field: WorkSnapshot
- type: frozen record containing current, progress, remaining, composition, kinds, and counts
- semantics: dashboard/activity-ready summary held in memory
- verify: json_path(path="$.progress", equals="1/2")
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
- verify: persists(subject="items saved through the backend")
- code: `workhorse/workhorse/worklist.py::Backend`

### field: JsonBackend
- type: dataclass with `path: Path` and `items_key: str = ""`
- semantics: atomically reads and writes a bare JSON array or an item list nested under `items_key`, preserving sibling metadata
- verify: unchanged(subject="sibling object metadata", except_fields=["items"])
- code: `workhorse/workhorse/worklist.py::JsonBackend`

## Methods: Backend

### method: load
- sig: `Backend.load() -> list[WorkItem]`
- does: return the current stored items as validated `WorkItem` values
- verify: count(subject="items returned by Backend.load", equals=2)
- returns: a list of work items
- verify: json_path(path="$[0].id", equals="first-item")
- code: `workhorse/workhorse/worklist.py::Backend.load`

### method: save
- sig: `Backend.save(items: Sequence[WorkItem]) -> None`
- does: persist the supplied item sequence as the backend's current contents
- verify: persists(subject="supplied item sequence in backend storage")
- returns: `None`
- verify: json_path(path="return", absent=true)
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
- verify: persists(subject="JSON worklist contents after save")
- does: preserve sibling object metadata when `items_key` is configured
- verify: unchanged(subject="sibling object metadata", except_fields=["items"])
- does: replace through a temporary file so readers never observe a partial JSON document
- returns: `None`
- verify: json_path(path="return", absent=true)
- returns: the scenario records `return` only when the result is not `None`
- verify: json_path(path="return", absent=true)
- code: `workhorse/workhorse/worklist.py::JsonBackend.save`
