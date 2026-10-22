---
type: flow
slug: carve-a-server-into-endpoint-pages
title: Carve a server into endpoint pages
---
# Carve a server into endpoint pages

- start: a server page holds two endpoints and an invocation
- steps:
  - [ostler edit carve endpoints](../editing.md#ostler-edit-carve-endpoints)
- end: the caller reads how many endpoint pages were made and finds each endpoint on its own page
- verify: exit_status(code=0)
- verify: stdout(matches="(?m)^carve docs/services/demo/http/server\\.md: 2 endpoint page\\(s\\), 1 invocation\\(s\\) moved with them$")
- verify: contents(subject="edit-scratch/docs/services/demo/http/get-widget.md", matches="(?m)^type: endpoint$")
- fixture: [edit scratch repo](../fixtures/edit-scratch-repo.md) with an edit scratch repo whose book and story have not been edited yet
