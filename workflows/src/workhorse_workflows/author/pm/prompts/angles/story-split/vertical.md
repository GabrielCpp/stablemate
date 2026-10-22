Judge whether the stories are vertical slices.

- The dependency-root story is a walking skeleton: a thin end-to-end journey step in the running system, not "set up the backend" or "create the data model".
- Every story answers "after this is green, what can the actor do that they could not before?". A story with no answer is a horizontal slice. Name the journey story it should fold into.
- Flag layer-ordered sequencing (all storage, then all API, then all UI) and dependency edges that exist only because "the layer below comes first".
