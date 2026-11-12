# Where the source and the app disagree

Found while writing this book from `groom/groom/app.py`, `state.py` and `projection.py`.

1. A push that sends a field of the wrong type is taken, and some of them break the fleet.
   - Step: `POST /push/progress`, `/push/blocked` and `/push/exited` with `name`, `repo_name`, `repo_branch`,
     `current_node` or `container_id` as a number or null, found by the input classes of the run.
   - Source: each handler reads the body with `data.get`, turns `container_id` into text and stores the
     other fields with `setattr` as they came. Nothing checks their type.
   - App did: answered 201. A number stored in `repo_name` or `current_node`, or in `name` of a run that already
     exists, makes `GET /api/state` answer 500 and later pushes to that run answer 500, until the run is pushed
     again with text.
   - Classification: app lenient for the cases that answer 201, and app wrong for the cases that corrupt the row.
     The book keeps the refusal the product intends and declares each class a `Diverges`. The surface pushes the
     run again with text after such a call, so later cells meet a fleet that answers.

2. `POST /api/settings/attend` turns any value of `enabled` into a truth value.
   - Step: `POST /api/settings/attend` with `enabled` as text or null, found by the input classes of the run.
   - Source: `bool(data.get("enabled"))`.
   - App did: answered 201. Text such as "no" turns the attendant on, null turns it off.
   - Classification: app lenient. The book declares both classes a `Diverges`.
