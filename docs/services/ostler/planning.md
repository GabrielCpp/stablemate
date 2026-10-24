---
type: cli
slug: planning
title: ostler planning commands
---
# ostler planning commands

The commands that plan work in a repo: epics, stories, features, milestones, the debt register, the epic
queue, frozen stories, templates and the documents a template declares. Every claim here runs
against a small plan repo seeded under the checkout, with `-C plan-scratch`, and each command acts
on an entity of its own, so the order the claims run in does not change an outcome.

- binary: ostler
- code: ostler/ostler/cli.py::main@d36715768389

## Commands

### ostler-create-epic
- usage: ostler create epic NAME --title TITLE [--prefix PREFIX] [--json]: allocates an id, numbers
  the epic after the last one and writes its epic page and index entry
- flags:
  - --title (the epic's heading)
  - --prefix (the id prefix to record, when the repo has none yet)
  - --json (print `{ok, id, name, message}`)
- args: name: the bare slug, which the command prefixes with the next four-digit number
- exits: 0 when the epic is created and its directory name is printed
- run: invoke(argv=["-C", "plan-scratch", "create", "epic", "fourth", "--title", "Fourth epic", "--json"])
- verify: exit_status(code=0)
- verify: json_path(path="ok", equals=true)
- verify: json_path(path="name", matches="-fourth$")
- fixture: [plan scratch repo](fixtures/plan-scratch-repo.md) with four epics, so the new one is
  numbered after the last
- code: ostler/ostler/_vendor/stablemate_core/base_cache.py::cache_root@79e1cc13c672
- code: ostler/ostler/_vendor/stablemate_core/config.py::config_path@45b4d92edb39
- code: ostler/ostler/crud.py::create_epic@b34e5b5a7cfb
- code: ostler/ostler/dynamic_registry.py::load_kinds@09b3f9268893
- code: ostler/ostler/index.py::active@cfb08df1cba1
- code: ostler/ostler/markdown.py::extract_refs@115245786c4b
- code: ostler/ostler/model.py::doc_roots@7651c0781a8f
- code: ostler/ostler/pages.py::files_in_book@e9f96e7b3156
- code: ostler/ostler/registry.py::base_type@cd37e79abc8c
- detail: [Planning identities](concepts/planning-identities.md)

### ostler-create-story
- usage: ostler create story EPIC SLUG --title TITLE [--covers ...] [--depends ...] [--json]: adds a
  story to an epic and writes its story page
- args: epic, slug: the epic's directory name and the new story's slug
- exits: 0 when the epic exists and the story is created
- run: invoke(argv=["-C", "plan-scratch", "create", "story", "0002-second", "newbie", "--title", "Newbie", "--json"])
- verify: exit_status(code=0)
- verify: json_path(path="ok", equals=true)
- verify: json_path(path="message", matches="in epic '0002-second'$")
- fixture: [plan scratch repo](fixtures/plan-scratch-repo.md) with an epic that holds one story
- code: ostler/ostler/_vendor/stablemate_core/base_cache.py::cache_root@79e1cc13c672
- code: ostler/ostler/_vendor/stablemate_core/config.py::config_path@45b4d92edb39
- code: ostler/ostler/crud.py::create_story@b34e5b5a7cfb
- code: ostler/ostler/dynamic_registry.py::load_kinds@09b3f9268893
- code: ostler/ostler/index.py::active@cfb08df1cba1
- code: ostler/ostler/markdown.py::extract_refs@115245786c4b
- code: ostler/ostler/model.py::doc_roots@7651c0781a8f
- code: ostler/ostler/pages.py::files_in_book@e9f96e7b3156
- code: ostler/ostler/registry.py::base_type@cd37e79abc8c

### ostler-create-feature
- usage: ostler create feature SLUG --title TITLE [--json]: writes a feature page with an allocated
  id
- exits: 0 when the feature is created
- run: invoke(argv=["-C", "plan-scratch", "create", "feature", "gamma", "--title", "Gamma", "--json"])
- verify: exit_status(code=0)
- verify: json_path(path="ok", equals=true)
- verify: json_path(path="message", matches="^created feature 'gamma'")
- fixture: [plan scratch repo](fixtures/plan-scratch-repo.md) with two features
- code: ostler/ostler/_vendor/stablemate_core/base_cache.py::cache_root@79e1cc13c672
- code: ostler/ostler/_vendor/stablemate_core/config.py::config_path@45b4d92edb39
- code: ostler/ostler/crud.py::create_feature@b34e5b5a7cfb
- code: ostler/ostler/dynamic_registry.py::load_kinds@09b3f9268893
- code: ostler/ostler/index.py::active@cfb08df1cba1
- code: ostler/ostler/markdown.py::extract_refs@115245786c4b
- code: ostler/ostler/model.py::doc_roots@7651c0781a8f
- code: ostler/ostler/pages.py::files_in_book@e9f96e7b3156
- code: ostler/ostler/registry.py::base_type@cd37e79abc8c

### ostler-create-milestone
- usage: ostler create milestone NAME --title TITLE [--json]: writes a milestone folder holding a `milestone.md`
  stub with an allocated id
- exits: 0 when the milestone is created
- run: invoke(argv=["-C", "plan-scratch", "create", "milestone", "m2", "--title", "M two", "--json"])
- verify: exit_status(code=0)
- verify: json_path(path="ok", equals=true)
- verify: json_path(path="name", equals="m2")
- fixture: [plan scratch repo](fixtures/plan-scratch-repo.md) with one milestone
- code: ostler/ostler/_vendor/stablemate_core/base_cache.py::cache_root@79e1cc13c672
- code: ostler/ostler/_vendor/stablemate_core/config.py::config_path@45b4d92edb39
- code: ostler/ostler/crud.py::create_milestone@b34e5b5a7cfb
- code: ostler/ostler/dynamic_registry.py::load_kinds@09b3f9268893
- code: ostler/ostler/index.py::active@cfb08df1cba1
- code: ostler/ostler/markdown.py::extract_refs@115245786c4b
- code: ostler/ostler/model.py::doc_roots@7651c0781a8f
- code: ostler/ostler/pages.py::files_in_book@e9f96e7b3156
- code: ostler/ostler/registry.py::base_type@cd37e79abc8c

### ostler-next-epic
- usage: ostler next-epic [--json]: names the first epic in the queue that still has unfinished work
- exits: 0 when an epic has unfinished work
- run: invoke(argv=["-C", "plan-scratch", "next-epic", "--json"])
- verify: exit_status(code=0)
- verify: json_path(path="name", equals="0001-first")
- verify: json_path(path="stories", equals=9)
- fixture: [plan scratch repo](fixtures/plan-scratch-repo.md) with four epics, the first holding
  nine unfinished stories
- code: ostler/ostler/_vendor/stablemate_core/base_cache.py::cache_root@79e1cc13c672
- code: ostler/ostler/_vendor/stablemate_core/config.py::config_path@45b4d92edb39
- code: ostler/ostler/dynamic_registry.py::load_kinds@09b3f9268893
- code: ostler/ostler/index.py::active@cfb08df1cba1
- code: ostler/ostler/markdown.py::extract_refs@115245786c4b
- code: ostler/ostler/model.py::doc_roots@7651c0781a8f
- code: ostler/ostler/pages.py::files_in_book@e9f96e7b3156
- code: ostler/ostler/registry.py::base_type@cd37e79abc8c
- code: ostler/ostler/select.py::epic_by_name@95d1a37a3be0

### ostler-next-story
- usage: ostler next-story EPIC [--json]: names the first story of an epic that no dependency or
  give-up stamp holds back
- args: epic: the epic's directory name
- exits: 0 when the epic has a runnable story
- run: invoke(argv=["-C", "plan-scratch", "next-story", "0001-first", "--json"])
- verify: exit_status(code=0)
- verify: json_path(path="slug", equals="alpha")
- verify: json_path(path="status", equals="Not started")
- fixture: [plan scratch repo](fixtures/plan-scratch-repo.md) with nine stories in order, the first
  with no dependency
- code: ostler/ostler/_vendor/stablemate_core/base_cache.py::cache_root@79e1cc13c672
- code: ostler/ostler/_vendor/stablemate_core/config.py::config_path@45b4d92edb39
- code: ostler/ostler/dynamic_registry.py::load_kinds@09b3f9268893
- code: ostler/ostler/index.py::active@cfb08df1cba1
- code: ostler/ostler/markdown.py::extract_refs@115245786c4b
- code: ostler/ostler/model.py::doc_roots@7651c0781a8f
- code: ostler/ostler/pages.py::files_in_book@e9f96e7b3156
- code: ostler/ostler/registry.py::base_type@cd37e79abc8c
- code: ostler/ostler/select.py::epic_by_name@95d1a37a3be0

### ostler-set-status
- usage: ostler set-status STORY STATUS: rewrites a story's status in its page front matter and its
  Implementation Status section
- args: story, status: the story's slug and the new status text
- exits: 0 when the story exists
- run: invoke(argv=["-C", "plan-scratch", "set-status", "bravo", "in-progress"])
- verify: exit_status(code=0)
- verify: stdout(matches="^status of 'bravo'")
- fixture: [plan scratch repo](fixtures/plan-scratch-repo.md) with a story whose status is Not
  started
- code: ostler/ostler/_vendor/stablemate_core/base_cache.py::cache_root@79e1cc13c672
- code: ostler/ostler/_vendor/stablemate_core/config.py::config_path@45b4d92edb39
- code: ostler/ostler/crud.py::dump_frontmatter@b34e5b5a7cfb
- code: ostler/ostler/dynamic_registry.py::load_kinds@09b3f9268893
- code: ostler/ostler/index.py::active@cfb08df1cba1
- code: ostler/ostler/markdown.py::extract_refs@115245786c4b
- code: ostler/ostler/model.py::doc_roots@7651c0781a8f
- code: ostler/ostler/pages.py::files_in_book@e9f96e7b3156
- code: ostler/ostler/registry.py::base_type@cd37e79abc8c

### ostler-conflict
- usage: ostler conflict STORY TEXT: records a conflict note on a story that a human must settle
- exits: 0 when the story exists
- run: invoke(argv=["-C", "plan-scratch", "conflict", "golf", "the criteria disagree"])
- verify: exit_status(code=0)
- verify: stdout(matches="^conflict recorded on 'golf'$")
- fixture: [plan scratch repo](fixtures/plan-scratch-repo.md) with a story with no conflict
- code: ostler/ostler/_vendor/stablemate_core/base_cache.py::cache_root@79e1cc13c672
- code: ostler/ostler/_vendor/stablemate_core/config.py::config_path@45b4d92edb39
- code: ostler/ostler/crud.py::dump_frontmatter@b34e5b5a7cfb
- code: ostler/ostler/dynamic_registry.py::load_kinds@09b3f9268893
- code: ostler/ostler/index.py::active@cfb08df1cba1
- code: ostler/ostler/markdown.py::extract_refs@115245786c4b
- code: ostler/ostler/model.py::doc_roots@7651c0781a8f
- code: ostler/ostler/pages.py::files_in_book@e9f96e7b3156
- code: ostler/ostler/registry.py::base_type@cd37e79abc8c

### ostler-conflict-clear
- usage: ostler conflict STORY --clear: removes the conflict note from a story
- flags:
  - --clear (remove the note instead of recording one)
- exits: 0 when the story exists
- run: invoke(argv=["-C", "plan-scratch", "conflict", "charlie", "--clear"])
- verify: exit_status(code=0)
- verify: stdout(matches="^conflict cleared off 'charlie'$")
- fixture: [plan scratch repo](fixtures/plan-scratch-repo.md) with a story that carries a conflict
- code: ostler/ostler/_vendor/stablemate_core/base_cache.py::cache_root@79e1cc13c672
- code: ostler/ostler/_vendor/stablemate_core/config.py::config_path@45b4d92edb39
- code: ostler/ostler/crud.py::dump_frontmatter@b34e5b5a7cfb
- code: ostler/ostler/dynamic_registry.py::load_kinds@09b3f9268893
- code: ostler/ostler/index.py::active@cfb08df1cba1
- code: ostler/ostler/markdown.py::extract_refs@115245786c4b
- code: ostler/ostler/model.py::doc_roots@7651c0781a8f
- code: ostler/ostler/pages.py::files_in_book@e9f96e7b3156
- code: ostler/ostler/registry.py::base_type@cd37e79abc8c

### ostler-unblock
- usage: ostler unblock [--story STORY | --epic EPIC] [--json]: clears the give-up stamp off a
  blocked story and returns it to Not started
- exits: 0 whether or not the story was blocked
- run: invoke(argv=["-C", "plan-scratch", "unblock", "delta", "--json"])
- verify: exit_status(code=0)
- verify: json_path(path="ok", equals=true)
- verify: json_path(path="message", matches="^unblocked 1")
- fixture: [plan scratch repo](fixtures/plan-scratch-repo.md) with a story whose status starts with
  Blocked
- code: ostler/ostler/_vendor/stablemate_core/base_cache.py::cache_root@79e1cc13c672
- code: ostler/ostler/_vendor/stablemate_core/config.py::config_path@45b4d92edb39
- code: ostler/ostler/crud.py::dump_frontmatter@b34e5b5a7cfb
- code: ostler/ostler/dynamic_registry.py::load_kinds@09b3f9268893
- code: ostler/ostler/index.py::active@cfb08df1cba1
- code: ostler/ostler/markdown.py::extract_refs@115245786c4b
- code: ostler/ostler/model.py::doc_roots@7651c0781a8f
- code: ostler/ostler/pages.py::files_in_book@e9f96e7b3156
- code: ostler/ostler/registry.py::base_type@cd37e79abc8c
- code: ostler/ostler/select.py::is_blocked@95d1a37a3be0

### ostler-freeze
- usage: ostler freeze STORY --by NAME [--note TEXT]: records the story's content fingerprint, with
  who approved it, in `.agents/ids.json`
- flags:
  - --by (who approves the story)
  - --note (a free-text note kept with the record)
- exits: 0 when the story exists
- run: invoke(argv=["-C", "plan-scratch", "freeze", "hotel", "--by", "me", "--note", "ok"])
- verify: exit_status(code=0)
- verify: stdout(matches="freeze story 'hotel'")
- verify: stdout(matches="recorded in .*ids\\.json")
- fixture: [plan scratch repo](fixtures/plan-scratch-repo.md) with an unfrozen story
- code: ostler/ostler/_vendor/stablemate_core/base_cache.py::cache_root@79e1cc13c672
- code: ostler/ostler/_vendor/stablemate_core/config.py::config_path@45b4d92edb39
- code: ostler/ostler/dynamic_registry.py::load_kinds@09b3f9268893
- code: ostler/ostler/freeze.py::fingerprint@fc5b0823b5d9
- code: ostler/ostler/index.py::active@cfb08df1cba1
- code: ostler/ostler/markdown.py::extract_refs@115245786c4b
- code: ostler/ostler/model.py::doc_roots@7651c0781a8f
- code: ostler/ostler/pages.py::files_in_book@e9f96e7b3156
- code: ostler/ostler/registry.py::base_type@cd37e79abc8c

### ostler-unfreeze
- usage: ostler unfreeze STORY: removes the story's frozen record from `.agents/ids.json`
- exits: 0 when the story is frozen
- run: invoke(argv=["-C", "plan-scratch", "unfreeze", "echo"])
- verify: exit_status(code=0)
- verify: stdout(matches="^unfreeze 'echo'$")
- fixture: [plan scratch repo](fixtures/plan-scratch-repo.md) with a story that is frozen
- code: ostler/ostler/_vendor/stablemate_core/base_cache.py::cache_root@79e1cc13c672
- code: ostler/ostler/_vendor/stablemate_core/config.py::config_path@45b4d92edb39
- code: ostler/ostler/dynamic_registry.py::load_kinds@09b3f9268893
- code: ostler/ostler/freeze.py::unfreeze@fc5b0823b5d9
- code: ostler/ostler/index.py::active@cfb08df1cba1
- code: ostler/ostler/markdown.py::extract_refs@115245786c4b
- code: ostler/ostler/model.py::doc_roots@7651c0781a8f
- code: ostler/ostler/pages.py::files_in_book@e9f96e7b3156
- code: ostler/ostler/registry.py::base_type@cd37e79abc8c

### ostler-path-epic
- usage: ostler path epic EPIC: prints the epic directory, relative to the repo root
- exits: 0 when the epic exists
- run: invoke(argv=["-C", "plan-scratch", "path", "epic", "0001-first"])
- verify: exit_status(code=0)
- verify: stdout(matches="^docs/epics/0001-first$")
- fixture: [plan scratch repo](fixtures/plan-scratch-repo.md) with an epic named 0001-first
- code: ostler/ostler/_vendor/stablemate_core/base_cache.py::cache_root@79e1cc13c672
- code: ostler/ostler/_vendor/stablemate_core/config.py::config_path@45b4d92edb39
- code: ostler/ostler/dynamic_registry.py::load_kinds@09b3f9268893
- code: ostler/ostler/index.py::active@cfb08df1cba1
- code: ostler/ostler/markdown.py::extract_refs@115245786c4b
- code: ostler/ostler/model.py::doc_roots@7651c0781a8f
- code: ostler/ostler/pages.py::files_in_book@e9f96e7b3156
- code: ostler/ostler/registry.py::base_type@cd37e79abc8c

### ostler-path-story
- usage: ostler path story EPIC STORY: prints the path of a story's page
- exits: 0 when the story exists
- run: invoke(argv=["-C", "plan-scratch", "path", "story", "0001-first", "alpha"])
- verify: exit_status(code=0)
- verify: stdout(matches="^docs/epics/0001-first/stories/alpha/story\\.md$")
- fixture: [plan scratch repo](fixtures/plan-scratch-repo.md) with a story named alpha
- code: ostler/ostler/_vendor/stablemate_core/base_cache.py::cache_root@79e1cc13c672
- code: ostler/ostler/_vendor/stablemate_core/config.py::config_path@45b4d92edb39
- code: ostler/ostler/dynamic_registry.py::load_kinds@09b3f9268893
- code: ostler/ostler/index.py::active@cfb08df1cba1
- code: ostler/ostler/markdown.py::extract_refs@115245786c4b
- code: ostler/ostler/model.py::doc_roots@7651c0781a8f
- code: ostler/ostler/pages.py::files_in_book@e9f96e7b3156
- code: ostler/ostler/registry.py::base_type@cd37e79abc8c

### ostler-path-branch
- usage: ostler path branch STORY: prints the git branch name a story's work goes on
- exits: 0 when the story exists
- run: invoke(argv=["-C", "plan-scratch", "path", "branch", "alpha"])
- verify: exit_status(code=0)
- verify: stdout(matches="^alpha$")
- fixture: [plan scratch repo](fixtures/plan-scratch-repo.md) with a story named alpha
- code: ostler/ostler/_vendor/stablemate_core/base_cache.py::cache_root@79e1cc13c672
- code: ostler/ostler/_vendor/stablemate_core/config.py::config_path@45b4d92edb39
- code: ostler/ostler/dynamic_registry.py::load_kinds@09b3f9268893
- code: ostler/ostler/index.py::active@cfb08df1cba1
- code: ostler/ostler/markdown.py::extract_refs@115245786c4b
- code: ostler/ostler/model.py::doc_roots@7651c0781a8f
- code: ostler/ostler/pages.py::files_in_book@e9f96e7b3156
- code: ostler/ostler/registry.py::base_type@cd37e79abc8c

### ostler-todo-add
- usage: ostler todo add EPIC: appends an epic to the ordered work queue in `docs/epics/index.md`
- exits: 0 when the epic exists and is not queued yet
- run: invoke(argv=["-C", "plan-scratch", "todo", "add", "0003-third"])
- verify: exit_status(code=0)
- verify: stdout(matches="^queued epic '0003-third'$")
- fixture: [plan scratch repo](fixtures/plan-scratch-repo.md) with a queue that holds two epics
- code: ostler/ostler/_vendor/stablemate_core/base_cache.py::cache_root@79e1cc13c672
- code: ostler/ostler/_vendor/stablemate_core/config.py::config_path@45b4d92edb39
- code: ostler/ostler/dynamic_registry.py::load_kinds@09b3f9268893
- code: ostler/ostler/index.py::active@cfb08df1cba1
- code: ostler/ostler/markdown.py::extract_refs@115245786c4b
- code: ostler/ostler/model.py::doc_roots@7651c0781a8f
- code: ostler/ostler/pages.py::files_in_book@e9f96e7b3156
- code: ostler/ostler/registry.py::base_type@cd37e79abc8c
- code: ostler/ostler/todo.py::add@eb0ea0bc4039

### ostler-todo-list
- usage: ostler todo list: prints the queued epics, one per line, in order
- exits: 0 always
- run: invoke(argv=["-C", "plan-scratch", "todo", "list"])
- verify: exit_status(code=0)
- verify: stdout(matches="(?m)^0001-first$")
- fixture: [plan scratch repo](fixtures/plan-scratch-repo.md) with a queue that holds two epics
- code: ostler/ostler/_vendor/stablemate_core/base_cache.py::cache_root@79e1cc13c672
- code: ostler/ostler/_vendor/stablemate_core/config.py::config_path@45b4d92edb39
- code: ostler/ostler/dynamic_registry.py::load_kinds@09b3f9268893
- code: ostler/ostler/index.py::active@cfb08df1cba1
- code: ostler/ostler/markdown.py::extract_refs@115245786c4b
- code: ostler/ostler/model.py::doc_roots@7651c0781a8f
- code: ostler/ostler/pages.py::files_in_book@e9f96e7b3156
- code: ostler/ostler/registry.py::base_type@cd37e79abc8c
- code: ostler/ostler/todo.py::list_epics@eb0ea0bc4039

### ostler-todo-prune
- usage: ostler todo prune EPIC: removes an epic from the work queue without deleting it
- exits: 0 when the epic is queued
- run: invoke(argv=["-C", "plan-scratch", "todo", "prune", "0002-second"])
- verify: exit_status(code=0)
- verify: stdout(matches="^pruned epic '0002-second' from the queue$")
- fixture: [plan scratch repo](fixtures/plan-scratch-repo.md) with a queue that holds two epics
- code: ostler/ostler/_vendor/stablemate_core/base_cache.py::cache_root@79e1cc13c672
- code: ostler/ostler/_vendor/stablemate_core/config.py::config_path@45b4d92edb39
- code: ostler/ostler/dynamic_registry.py::load_kinds@09b3f9268893
- code: ostler/ostler/index.py::active@cfb08df1cba1
- code: ostler/ostler/markdown.py::extract_refs@115245786c4b
- code: ostler/ostler/model.py::doc_roots@7651c0781a8f
- code: ostler/ostler/pages.py::files_in_book@e9f96e7b3156
- code: ostler/ostler/registry.py::base_type@cd37e79abc8c
- code: ostler/ostler/todo.py::list_epics@eb0ea0bc4039

### ostler-todo-reorder
- usage: ostler todo reorder EPIC [EPIC ...]: rewrites the queue in the order given
- exits: 0 when every named epic is queued
- run: invoke(argv=["-C", "plan-scratch", "todo", "reorder", "0001-first"])
- verify: exit_status(code=0)
- verify: stdout(matches="^reordered epics queue$")
- fixture: [plan scratch repo](fixtures/plan-scratch-repo.md) with a queue that holds 0001-first
- code: ostler/ostler/_vendor/stablemate_core/base_cache.py::cache_root@79e1cc13c672
- code: ostler/ostler/_vendor/stablemate_core/config.py::config_path@45b4d92edb39
- code: ostler/ostler/dynamic_registry.py::load_kinds@09b3f9268893
- code: ostler/ostler/index.py::active@cfb08df1cba1
- code: ostler/ostler/markdown.py::extract_refs@115245786c4b
- code: ostler/ostler/model.py::doc_roots@7651c0781a8f
- code: ostler/ostler/pages.py::files_in_book@e9f96e7b3156
- code: ostler/ostler/registry.py::base_type@cd37e79abc8c
- code: ostler/ostler/todo.py::list_epics@eb0ea0bc4039

### ostler-backlog-add
- usage: ostler backlog add SUMMARY --repo REPO --area AREA [--pattern PATTERN] [--symbol SYMBOL ...] [--id ID] [--body TEXT] [--prefix PREFIX] [--json]: files a record a person wrote on the [debt register](concepts/the-debt-register.md) and commits it in the artifacts repo as `chore(REPO): file ID`; `ostler create backlog-item` is the same command under another name
- flags:
  - --repo (the workspace repository the record is about, one lowercase kebab segment)
  - --area (the area folder the record is shelved under, one lowercase kebab segment)
  - --pattern (the kind of fix the record calls for; `untriaged` when omitted)
  - --symbol (a code symbol or path the record names; repeatable)
  - --id (file under this id instead of a minted one)
  - --body (the record's text below the frontmatter)
  - --prefix (the id prefix to pin when the repo has none yet)
  - --json (print `{ok, id, name, message}` instead of the message line)
- args: summary (the record's one-line listing text)
- exits: 0 when the record is filed; 1 with the reason when it is refused (an id the workspace already holds, a repo or area that is not one lowercase kebab segment, an empty or multi-line summary, or a failed artifacts commit)
- run: invoke(argv=["-C", "plan-scratch", "backlog", "add", "third item", "--repo", "api-service", "--area", "billing", "--id", "X-3"], env={"STABLEMATE_ARTIFACTS_DIR": "plan-scratch/art"})
- verify: exit_status(code=0)
- verify: stdout(matches="^filed record 'X-3'$")
- fixture: [plan scratch repo](fixtures/plan-scratch-repo.md) with records X-1 and X-2 on its register
- code: ostler/ostler/_vendor/stablemate_core/base_cache.py::cache_root@79e1cc13c672
- code: ostler/ostler/_vendor/stablemate_core/config.py::config_path@45b4d92edb39
- code: ostler/ostler/dynamic_registry.py::load_kinds@09b3f9268893
- code: ostler/ostler/index.py::active@cfb08df1cba1
- code: ostler/ostler/markdown.py::extract_refs@115245786c4b
- code: ostler/ostler/model.py::doc_roots@7651c0781a8f
- code: ostler/ostler/pages.py::files_in_book@e9f96e7b3156
- code: ostler/ostler/registry.py::base_type@cd37e79abc8c

### ostler-backlog-list
- usage: ostler backlog list [--repo REPO] [--status STATUS] [--json]: prints every record on the register, closed ones included, as one tab-separated line of id, repo, area, status, pattern and summary, sorted by repo, area and id; a `record.md` that does not parse is left out of the listing and named by `ostler doctor` instead
- flags:
  - --repo (only the records of this workspace repository; every repository when omitted)
  - --status (only the records at this status, one of open, done, dropped or promoted; every status when omitted)
  - --json (print the matching records as one indented JSON array of their full fields, body included)
- exits: 0 always (an empty match prints `(none)`)
- run: invoke(argv=["-C", "plan-scratch", "backlog", "list", "--repo", "api-service"], env={"STABLEMATE_ARTIFACTS_DIR": "plan-scratch/art"})
- verify: exit_status(code=0)
- verify: stdout(matches="(?m)^X-1\\tapi-service\\tbilling\\topen\\tuntriaged\\tfirst item$")
- fixture: [plan scratch repo](fixtures/plan-scratch-repo.md) with records X-1 and X-2 on its register
- code: ostler/ostler/_vendor/stablemate_core/base_cache.py::cache_root@79e1cc13c672
- code: ostler/ostler/_vendor/stablemate_core/config.py::config_path@45b4d92edb39
- code: ostler/ostler/dynamic_registry.py::load_kinds@09b3f9268893
- code: ostler/ostler/index.py::active@cfb08df1cba1
- code: ostler/ostler/markdown.py::extract_refs@115245786c4b
- code: ostler/ostler/model.py::doc_roots@7651c0781a8f
- code: ostler/ostler/pages.py::files_in_book@e9f96e7b3156
- code: ostler/ostler/registry.py::base_type@cd37e79abc8c

### ostler-backlog-adopt
- usage: ostler backlog adopt --repo REPO FILE [--prefix PREFIX] [--json]: turns every top-level bullet of an old backlog list into a record of REPO by the import rules of [the debt register](concepts/the-debt-register.md#importing-an-old-list), commits them together in the artifacts repo as `chore(REPO): import the backlog list`, then deletes FILE; it prints one listing line per record, then `imported N records, kept K ids`
- flags:
  - --repo (the workspace repository every imported record belongs to; required)
  - --prefix (the id prefix to pin when the repo has none yet)
  - --json (print the imported records as one indented JSON array of their full fields instead of the listing)
- args: file (the markdown list to import)
- exits: 0 when the list is imported; 1 with the reason, leaving FILE and the shelf as they were, when FILE is missing, holds no bullets, uses one id twice, keeps an id the workspace already holds, or holds a bullet that makes an invalid record, or when the artifacts commit fails
- run: invoke(argv=["-C", "plan-scratch", "backlog", "adopt", "--repo", "api-service", "plan-scratch/old-list.md", "--prefix", "BL"], env={"STABLEMATE_ARTIFACTS_DIR": "plan-scratch/art"})
- verify: exit_status(code=0)
- verify: stdout(matches="(?m)^imported 2 records, kept 0 ids$")
- fixture: [plan scratch repo](fixtures/plan-scratch-repo.md) with an old two-bullet list beside it
- code: ostler/ostler/_vendor/stablemate_core/base_cache.py::cache_root@79e1cc13c672
- code: ostler/ostler/_vendor/stablemate_core/config.py::config_path@45b4d92edb39
- code: ostler/ostler/dynamic_registry.py::load_kinds@09b3f9268893
- code: ostler/ostler/index.py::active@cfb08df1cba1
- code: ostler/ostler/markdown.py::extract_refs@115245786c4b
- code: ostler/ostler/model.py::doc_roots@7651c0781a8f
- code: ostler/ostler/pages.py::files_in_book@e9f96e7b3156
- code: ostler/ostler/registry.py::base_type@cd37e79abc8c

### ostler-backlog-prune
- usage: ostler backlog prune ID [--as done|dropped|promoted] [--reason TEXT] [--json]: closes a record on the [debt register](concepts/the-debt-register.md#closing-a-record) and commits the close in the artifacts repo as `chore(REPO): close ID as STATUS`
- flags:
  - --as (the status the record ends at: `done` by default, or `dropped` or `promoted`)
  - --reason (why the record ended, written to its `reason`; required with `dropped` and `promoted`)
  - --json (print `{ok, id, name, message}` instead of the message line)
- args: id (the record's full id or short handle)
- exits: 0 when the record is closed, or was already closed at that status; 1 with the reason when the id is unknown, the record is closed at another status, or --as dropped or promoted comes without --reason
- run: invoke(argv=["-C", "plan-scratch", "backlog", "prune", "X-2"], env={"STABLEMATE_ARTIFACTS_DIR": "plan-scratch/art"})
- verify: exit_status(code=0)
- verify: stdout(matches="^closed record 'X-2' as done$")
- fixture: [plan scratch repo](fixtures/plan-scratch-repo.md) with a record X-2 filed on its register
- code: ostler/ostler/_vendor/stablemate_core/base_cache.py::cache_root@79e1cc13c672
- code: ostler/ostler/_vendor/stablemate_core/config.py::config_path@45b4d92edb39
- code: ostler/ostler/dynamic_registry.py::load_kinds@09b3f9268893
- code: ostler/ostler/index.py::active@cfb08df1cba1
- code: ostler/ostler/markdown.py::extract_refs@115245786c4b
- code: ostler/ostler/model.py::doc_roots@7651c0781a8f
- code: ostler/ostler/pages.py::files_in_book@e9f96e7b3156
- code: ostler/ostler/registry.py::base_type@cd37e79abc8c

### ostler-milestone-set-source-items
- usage: ostler milestone set-source-items MILESTONE ITEM [ITEM ...]: records which [debt register](concepts/the-debt-register.md)
  records a milestone delivers, replacing its `sourceItems` list; a short handle is expanded to its full id first
- exits: 0 when the milestone exists
- run: invoke(argv=["-C", "plan-scratch", "milestone", "set-source-items", "m1", "X-1"], env={"STABLEMATE_ARTIFACTS_DIR": "plan-scratch/art"})
- verify: exit_status(code=0)
- verify: stdout(matches="^set 1 source item\\(s\\) on milestone 'm1'$")
- fixture: [plan scratch repo](fixtures/plan-scratch-repo.md) with a milestone and a record X-1 on its register
- code: ostler/ostler/_vendor/stablemate_core/base_cache.py::cache_root@79e1cc13c672
- code: ostler/ostler/_vendor/stablemate_core/config.py::config_path@45b4d92edb39
- code: ostler/ostler/crud.py::dump_frontmatter@b34e5b5a7cfb
- code: ostler/ostler/dynamic_registry.py::load_kinds@09b3f9268893
- code: ostler/ostler/index.py::active@cfb08df1cba1
- code: ostler/ostler/markdown.py::extract_refs@115245786c4b
- code: ostler/ostler/model.py::doc_roots@7651c0781a8f
- code: ostler/ostler/pages.py::files_in_book@e9f96e7b3156
- code: ostler/ostler/registry.py::base_type@cd37e79abc8c

### ostler-seed-add
- usage: ostler seed add EPIC ID [--summary TEXT] [--status STATUS] [--layer LAYER] [--service
  SERVICE]: adds a seed section to an epic page
- flags:
  - --status (one of backlog, researched, covered, resolved, dropped, deferred)
  - --layer (repeatable; one of frontend, backend, infra)
  - --service (repeatable; the service the seed lands in)
- exits: 0 when the epic exists and the seed id is new
- run: invoke(argv=["-C", "plan-scratch", "seed", "add", "0002-second", "SD-9", "--summary", "nine", "--status", "backlog", "--layer", "backend"])
- verify: exit_status(code=0)
- verify: stdout(matches="^added seed 'SD-9' in epic '0002-second'$")
- fixture: [plan scratch repo](fixtures/plan-scratch-repo.md) with an epic with no seed
- code: ostler/ostler/_vendor/stablemate_core/base_cache.py::cache_root@79e1cc13c672
- code: ostler/ostler/_vendor/stablemate_core/config.py::config_path@45b4d92edb39
- code: ostler/ostler/crud.py::add_seed@b34e5b5a7cfb
- code: ostler/ostler/dynamic_registry.py::load_kinds@09b3f9268893
- code: ostler/ostler/index.py::active@cfb08df1cba1
- code: ostler/ostler/markdown.py::extract_refs@115245786c4b
- code: ostler/ostler/model.py::doc_roots@7651c0781a8f
- code: ostler/ostler/pages.py::files_in_book@e9f96e7b3156
- code: ostler/ostler/registry.py::base_type@cd37e79abc8c

### ostler-seed-remove
- usage: ostler seed remove EPIC ID: removes a seed section from an epic page
- exits: 0 when the seed exists
- run: invoke(argv=["-C", "plan-scratch", "seed", "remove", "0001-first", "SD-2"])
- verify: exit_status(code=0)
- verify: stdout(matches="^removed seed 'SD-2' from epic '0001-first'$")
- fixture: [plan scratch repo](fixtures/plan-scratch-repo.md) with an epic that holds seed SD-2
- code: ostler/ostler/_vendor/stablemate_core/base_cache.py::cache_root@79e1cc13c672
- code: ostler/ostler/_vendor/stablemate_core/config.py::config_path@45b4d92edb39
- code: ostler/ostler/crud.py::remove_seed@b34e5b5a7cfb
- code: ostler/ostler/dynamic_registry.py::load_kinds@09b3f9268893
- code: ostler/ostler/index.py::active@cfb08df1cba1
- code: ostler/ostler/markdown.py::extract_refs@115245786c4b
- code: ostler/ostler/model.py::doc_roots@7651c0781a8f
- code: ostler/ostler/pages.py::files_in_book@e9f96e7b3156
- code: ostler/ostler/registry.py::base_type@cd37e79abc8c

### ostler-update-story
- usage: ostler update story SLUG --title TITLE --covers COVERS --depends DEPENDS: replaces a
  story's title, coverage list and blocker list
- flags:
  - --covers (the seed ids the story covers, or `(none)`)
  - --depends (the complete blocker list, or `(none)` to clear it)
- exits: 0 when the story exists
- run: invoke(argv=["-C", "plan-scratch", "update", "story", "india", "--title", "Story india b", "--covers", "(none)", "--depends", "(none)"])
- verify: exit_status(code=0)
- verify: stdout(matches="^updated story 'india' in epic '0001-first'$")
- fixture: [plan scratch repo](fixtures/plan-scratch-repo.md) with a story named india
- code: ostler/ostler/_vendor/stablemate_core/base_cache.py::cache_root@79e1cc13c672
- code: ostler/ostler/_vendor/stablemate_core/config.py::config_path@45b4d92edb39
- code: ostler/ostler/crud.py::update_story@b34e5b5a7cfb
- code: ostler/ostler/dynamic_registry.py::load_kinds@09b3f9268893
- code: ostler/ostler/index.py::active@cfb08df1cba1
- code: ostler/ostler/markdown.py::extract_refs@115245786c4b
- code: ostler/ostler/model.py::doc_roots@7651c0781a8f
- code: ostler/ostler/pages.py::files_in_book@e9f96e7b3156
- code: ostler/ostler/registry.py::base_type@cd37e79abc8c

### ostler-delete-epic
- usage: ostler delete epic EPIC: removes an epic directory and its entry in the epics index
- exits: 0 when the epic exists
- run: invoke(argv=["-C", "plan-scratch", "delete", "epic", "0004-junk"])
- verify: exit_status(code=0)
- verify: stdout(matches="^deleted epic '0004-junk'")
- fixture: [plan scratch repo](fixtures/plan-scratch-repo.md) with an epic named 0004-junk with no
  story
- code: ostler/ostler/_vendor/stablemate_core/base_cache.py::cache_root@79e1cc13c672
- code: ostler/ostler/_vendor/stablemate_core/config.py::config_path@45b4d92edb39
- code: ostler/ostler/crud.py::delete_epic@b34e5b5a7cfb
- code: ostler/ostler/dynamic_registry.py::load_kinds@09b3f9268893
- code: ostler/ostler/index.py::active@cfb08df1cba1
- code: ostler/ostler/markdown.py::extract_refs@115245786c4b
- code: ostler/ostler/model.py::doc_roots@7651c0781a8f
- code: ostler/ostler/pages.py::files_in_book@e9f96e7b3156
- code: ostler/ostler/registry.py::base_type@cd37e79abc8c
- code: ostler/ostler/todo.py::list_epics@eb0ea0bc4039

### ostler-delete-story
- usage: ostler delete story SLUG: removes a story from its epic
- exits: 0 when the story exists
- run: invoke(argv=["-C", "plan-scratch", "delete", "story", "sx"])
- verify: exit_status(code=0)
- verify: stdout(matches="^deleted story 'sx' from epic '0002-second'$")
- fixture: [plan scratch repo](fixtures/plan-scratch-repo.md) with an epic holding one story
- code: ostler/ostler/_vendor/stablemate_core/base_cache.py::cache_root@79e1cc13c672
- code: ostler/ostler/_vendor/stablemate_core/config.py::config_path@45b4d92edb39
- code: ostler/ostler/crud.py::delete_story@b34e5b5a7cfb
- code: ostler/ostler/dynamic_registry.py::load_kinds@09b3f9268893
- code: ostler/ostler/index.py::active@cfb08df1cba1
- code: ostler/ostler/markdown.py::extract_refs@115245786c4b
- code: ostler/ostler/model.py::doc_roots@7651c0781a8f
- code: ostler/ostler/pages.py::files_in_book@e9f96e7b3156
- code: ostler/ostler/registry.py::base_type@cd37e79abc8c

### ostler-delete-feature
- usage: ostler delete feature SLUG: removes a feature page
- exits: 0 when the feature exists
- run: invoke(argv=["-C", "plan-scratch", "delete", "feature", "beta"])
- verify: exit_status(code=0)
- verify: stdout(matches="^deleted feature 'beta'$")
- fixture: [plan scratch repo](fixtures/plan-scratch-repo.md) with two features
- code: ostler/ostler/_vendor/stablemate_core/base_cache.py::cache_root@79e1cc13c672
- code: ostler/ostler/_vendor/stablemate_core/config.py::config_path@45b4d92edb39
- code: ostler/ostler/crud.py::delete_feature@b34e5b5a7cfb
- code: ostler/ostler/dynamic_registry.py::load_kinds@09b3f9268893
- code: ostler/ostler/index.py::active@cfb08df1cba1
- code: ostler/ostler/markdown.py::extract_refs@115245786c4b
- code: ostler/ostler/model.py::doc_roots@7651c0781a8f
- code: ostler/ostler/pages.py::files_in_book@e9f96e7b3156
- code: ostler/ostler/registry.py::base_type@cd37e79abc8c

### ostler-template-new
- usage: ostler template new NAME [KIND ...]: declares a template in `.agents/templates.yml`, with a
  stub for each kind named
- exits: 0 when the template name is free
- run: invoke(argv=["-C", "plan-scratch", "template", "new", "tpl3", "widget"])
- verify: exit_status(code=0)
- verify: stdout(matches="^created template 'tpl3' \\(1 kind\\(s\\)\\)$")
- fixture: [plan scratch repo](fixtures/plan-scratch-repo.md) with two declared templates
- code: ostler/ostler/_vendor/stablemate_core/base_cache.py::cache_root@79e1cc13c672
- code: ostler/ostler/_vendor/stablemate_core/config.py::config_path@45b4d92edb39
- code: ostler/ostler/dynamic_registry.py::load_kinds@09b3f9268893
- code: ostler/ostler/index.py::active@cfb08df1cba1
- code: ostler/ostler/markdown.py::extract_refs@115245786c4b
- code: ostler/ostler/model.py::doc_roots@7651c0781a8f
- code: ostler/ostler/pages.py::files_in_book@e9f96e7b3156
- code: ostler/ostler/registry.py::base_type@cd37e79abc8c
- code: ostler/ostler/templates.py::new@401b5b3edc08

### ostler-template-edit
- usage: ostler template edit NAME --set KIND.FIELD=VALUE: patches a field of one kind of a template
- flags:
  - --set (repeatable; a dotted kind.field path and its new value)
- exits: 0 when the template and the field exist
- run: invoke(argv=["-C", "plan-scratch", "template", "edit", "tpl2", "--set", "memo.doc_root=docs/memos"])
- verify: exit_status(code=0)
- verify: stdout(matches="^updated template 'tpl2'$")
- fixture: [plan scratch repo](fixtures/plan-scratch-repo.md) with a template tpl2 with a memo kind
- code: ostler/ostler/_vendor/stablemate_core/base_cache.py::cache_root@79e1cc13c672
- code: ostler/ostler/_vendor/stablemate_core/config.py::config_path@45b4d92edb39
- code: ostler/ostler/dynamic_registry.py::load_kinds@09b3f9268893
- code: ostler/ostler/index.py::active@cfb08df1cba1
- code: ostler/ostler/markdown.py::extract_refs@115245786c4b
- code: ostler/ostler/model.py::doc_roots@7651c0781a8f
- code: ostler/ostler/pages.py::files_in_book@e9f96e7b3156
- code: ostler/ostler/registry.py::base_type@cd37e79abc8c
- code: ostler/ostler/templates.py::edit@401b5b3edc08

### ostler-template-find
- usage: ostler template find [--json]: lists the declared templates and how many kinds each holds
- exits: 0 always
- run: invoke(argv=["-C", "plan-scratch", "template", "find", "--json"])
- verify: exit_status(code=0)
- verify: json_path(path="[0].name", equals="tpl")
- verify: json_path(path="[0].kinds", equals=1)
- fixture: [plan scratch repo](fixtures/plan-scratch-repo.md) with two declared templates
- code: ostler/ostler/_vendor/stablemate_core/base_cache.py::cache_root@79e1cc13c672
- code: ostler/ostler/_vendor/stablemate_core/config.py::config_path@45b4d92edb39
- code: ostler/ostler/dynamic_registry.py::load_kinds@09b3f9268893
- code: ostler/ostler/index.py::active@cfb08df1cba1
- code: ostler/ostler/markdown.py::extract_refs@115245786c4b
- code: ostler/ostler/model.py::doc_roots@7651c0781a8f
- code: ostler/ostler/pages.py::files_in_book@e9f96e7b3156
- code: ostler/ostler/registry.py::base_type@cd37e79abc8c
- code: ostler/ostler/templates.py::find@401b5b3edc08

### ostler-template-find-one
- usage: ostler template find NAME [--json]: prints one template with each of its kinds in full
- exits: 0 when the template exists
- run: invoke(argv=["-C", "plan-scratch", "template", "find", "tpl", "--json"])
- verify: exit_status(code=0)
- verify: json_path(path="[0].name", equals="tpl")
- verify: json_path(path="[0].kinds[0].name", equals="note")
- verify: json_path(path="[0].kinds[0].default_path", equals="docs/note")
- fixture: [plan scratch repo](fixtures/plan-scratch-repo.md) with a template tpl with a note kind
- code: ostler/ostler/_vendor/stablemate_core/base_cache.py::cache_root@79e1cc13c672
- code: ostler/ostler/_vendor/stablemate_core/config.py::config_path@45b4d92edb39
- code: ostler/ostler/dynamic_registry.py::load_kinds@09b3f9268893
- code: ostler/ostler/index.py::active@cfb08df1cba1
- code: ostler/ostler/markdown.py::extract_refs@115245786c4b
- code: ostler/ostler/model.py::doc_roots@7651c0781a8f
- code: ostler/ostler/pages.py::files_in_book@e9f96e7b3156
- code: ostler/ostler/registry.py::base_type@cd37e79abc8c
- code: ostler/ostler/templates.py::find@401b5b3edc08

### ostler-template-delete
- usage: ostler template delete NAME: removes a template from `.agents/templates.yml`
- exits: 0 when the template exists
- run: invoke(argv=["-C", "plan-scratch", "template", "delete", "tpl2"])
- verify: exit_status(code=0)
- verify: stdout(matches="^deleted template 'tpl2'$")
- fixture: [plan scratch repo](fixtures/plan-scratch-repo.md) with a template tpl2
- code: ostler/ostler/_vendor/stablemate_core/base_cache.py::cache_root@79e1cc13c672
- code: ostler/ostler/_vendor/stablemate_core/config.py::config_path@45b4d92edb39
- code: ostler/ostler/dynamic_registry.py::load_kinds@09b3f9268893
- code: ostler/ostler/index.py::active@cfb08df1cba1
- code: ostler/ostler/markdown.py::extract_refs@115245786c4b
- code: ostler/ostler/model.py::doc_roots@7651c0781a8f
- code: ostler/ostler/pages.py::files_in_book@e9f96e7b3156
- code: ostler/ostler/registry.py::base_type@cd37e79abc8c
- code: ostler/ostler/templates.py::delete@401b5b3edc08

### ostler-template-apply
- usage: ostler template apply NAME: creates each kind's document folder and adds the guidance to
  `CLAUDE.md`
- exits: 0 when the template exists
- run: invoke(argv=["-C", "plan-scratch", "template", "apply", "tpl"])
- verify: exit_status(code=0)
- verify: stdout(matches="^applied template 'tpl' \\(1 dir\\(s\\) scaffolded\\)$")
- fixture: [plan scratch repo](fixtures/plan-scratch-repo.md) with a template tpl whose note folder
  is missing
- code: ostler/ostler/_vendor/stablemate_core/base_cache.py::cache_root@79e1cc13c672
- code: ostler/ostler/_vendor/stablemate_core/config.py::config_path@45b4d92edb39
- code: ostler/ostler/dynamic_registry.py::load_kinds@09b3f9268893
- code: ostler/ostler/index.py::active@cfb08df1cba1
- code: ostler/ostler/markdown.py::extract_refs@115245786c4b
- code: ostler/ostler/model.py::doc_roots@7651c0781a8f
- code: ostler/ostler/pages.py::files_in_book@e9f96e7b3156
- code: ostler/ostler/registry.py::base_type@cd37e79abc8c
- code: ostler/ostler/templates.py::apply@401b5b3edc08

### ostler-new-instance
- usage: ostler new KIND NAME [KEY=VALUE ...] [--json]: creates a document of a template-declared
  kind
- exits: 0 when the kind is declared and the name is free
- run: invoke(argv=["-C", "plan-scratch", "new", "note", "n1", "--json"])
- verify: exit_status(code=0)
- verify: json_path(path="ok", equals=true)
- verify: json_path(path="message", equals="created note 'n1'")
- fixture: [plan scratch repo](fixtures/plan-scratch-repo.md) with a declared note kind
- code: ostler/ostler/_vendor/stablemate_core/base_cache.py::cache_root@79e1cc13c672
- code: ostler/ostler/_vendor/stablemate_core/config.py::config_path@45b4d92edb39
- code: ostler/ostler/crud.py::dump_frontmatter@b34e5b5a7cfb
- code: ostler/ostler/crud_generic.py::create_instance@0c22ea0d56ea
- code: ostler/ostler/dynamic_registry.py::load_kinds@09b3f9268893
- code: ostler/ostler/index.py::active@cfb08df1cba1
- code: ostler/ostler/markdown.py::extract_refs@115245786c4b
- code: ostler/ostler/model.py::doc_roots@7651c0781a8f
- code: ostler/ostler/pages.py::files_in_book@e9f96e7b3156
- code: ostler/ostler/registry.py::base_type@cd37e79abc8c

### ostler-find-instances
- usage: ostler find KIND [NAME] [--json]: lists the documents of a template-declared kind
- exits: 0 when the kind is declared
- run: invoke(argv=["-C", "plan-scratch", "find", "note", "--json"])
- verify: exit_status(code=0)
- verify: json_path(path="[0].type", equals="note")
- verify: json_path(path="[0].path", matches="^docs/note/n[0-9]/note\\.md$")
- fixture: [plan scratch repo](fixtures/plan-scratch-repo.md) with a declared note kind with two
  notes
- code: ostler/ostler/_vendor/stablemate_core/base_cache.py::cache_root@79e1cc13c672
- code: ostler/ostler/_vendor/stablemate_core/config.py::config_path@45b4d92edb39
- code: ostler/ostler/crud_generic.py::find_instance@0c22ea0d56ea
- code: ostler/ostler/dynamic_registry.py::load_kinds@09b3f9268893
- code: ostler/ostler/index.py::active@cfb08df1cba1
- code: ostler/ostler/markdown.py::extract_refs@115245786c4b
- code: ostler/ostler/model.py::doc_roots@7651c0781a8f
- code: ostler/ostler/pages.py::files_in_book@e9f96e7b3156
- code: ostler/ostler/registry.py::base_type@cd37e79abc8c

### ostler-set-instance
- usage: ostler set KIND NAME KEY=VALUE [KEY=VALUE ...] [--json]: edits front-matter fields of a
  document of a template-declared kind
- exits: 0 when the document exists
- run: invoke(argv=["-C", "plan-scratch", "set", "note", "n2", "title=Hello", "--json"])
- verify: exit_status(code=0)
- verify: json_path(path="ok", equals=true)
- verify: json_path(path="message", equals="updated note 'n2'")
- fixture: [plan scratch repo](fixtures/plan-scratch-repo.md) with a note n2
- code: ostler/ostler/_vendor/stablemate_core/base_cache.py::cache_root@79e1cc13c672
- code: ostler/ostler/_vendor/stablemate_core/config.py::config_path@45b4d92edb39
- code: ostler/ostler/crud.py::dump_frontmatter@b34e5b5a7cfb
- code: ostler/ostler/crud_generic.py::edit_instance@0c22ea0d56ea
- code: ostler/ostler/dynamic_registry.py::load_kinds@09b3f9268893
- code: ostler/ostler/index.py::active@cfb08df1cba1
- code: ostler/ostler/markdown.py::extract_refs@115245786c4b
- code: ostler/ostler/model.py::doc_roots@7651c0781a8f
- code: ostler/ostler/pages.py::files_in_book@e9f96e7b3156
- code: ostler/ostler/registry.py::base_type@cd37e79abc8c

### ostler-remove-instance
- usage: ostler remove KIND NAME [--json]: deletes a document of a template-declared kind
- exits: 0 when the document exists
- run: invoke(argv=["-C", "plan-scratch", "remove", "note", "n3", "--json"])
- verify: exit_status(code=0)
- verify: json_path(path="ok", equals=true)
- verify: json_path(path="message", equals="deleted note 'n3'")
- fixture: [plan scratch repo](fixtures/plan-scratch-repo.md) with a note n3
- code: ostler/ostler/_vendor/stablemate_core/base_cache.py::cache_root@79e1cc13c672
- code: ostler/ostler/_vendor/stablemate_core/config.py::config_path@45b4d92edb39
- code: ostler/ostler/crud_generic.py::delete_instance@0c22ea0d56ea
- code: ostler/ostler/dynamic_registry.py::load_kinds@09b3f9268893
- code: ostler/ostler/index.py::active@cfb08df1cba1
- code: ostler/ostler/markdown.py::extract_refs@115245786c4b
- code: ostler/ostler/model.py::doc_roots@7651c0781a8f
- code: ostler/ostler/pages.py::files_in_book@e9f96e7b3156
- code: ostler/ostler/registry.py::base_type@cd37e79abc8c

### ostler-cache-clean
- usage: ostler cache clean [--all] [--max-age-days N] [--json]: deletes parse-index entries that
  nothing wrote for N days
- flags:
  - --all (remove every entry)
  - --max-age-days (the age, in days, past which an entry goes; default 14)
  - --json (print `{dir, removed}`)
- exits: 0 always
- run: invoke(argv=["-C", "plan-scratch", "cache", "clean", "--max-age-days", "36500", "--json"])
- verify: exit_status(code=0)
- verify: json_path(path="removed", equals=0)
- fixture: [plan scratch repo](fixtures/plan-scratch-repo.md) with no state of its own, since the
  cache is shared
- code: ostler/ostler/_vendor/stablemate_core/base_cache.py::cache_root@79e1cc13c672
- code: ostler/ostler/_vendor/stablemate_core/config.py::config_path@45b4d92edb39
- code: ostler/ostler/index.py::clean@cfb08df1cba1
