# Milestone authoring: grill record

The settled tree from the grill session of 2026-10-22. Each entry gives the question, the
answer, and the reason the answer holds. The design note
[milestone-authoring.md](milestone-authoring.md) derives the design from these decisions.

Client repos appear as placeholders: `acme` is the web client with today's only milestone,
`globex` is the mobile client.

## The milestone as input

1. **Roadmap or milestone.** A milestone folder replaces the roadmap item. Today's
   roadmap-to-milestone stage goes away, and Author starts at the epic split. Roadmap and
   milestone were already one to one, so that stage only transcribed one into the other.
2. **Where the folder lives.** Wherever the docs live, at `docs/milestones/<slug>/`. It is
   the contract Author, the PM and the coder bind to, so a reviewer sees it change.
3. **Grill records.** A grill record is the settled tree from running the grill skill on any
   part of the milestone or of a design. A milestone holds several, and it links to one or
   more decompose notes.
4. **Folder layout.** `milestone.md` is required. It carries the roadmap's sections and the
   frontmatter `type`, `title`, `status` and `dependsOn`. The optional parts are
   `grills/<topic>.md`, `mockups/<journey>.html` and `artifacts/`. Decompose notes stay in
   `docs/design/` and `milestone.md` links them, because a design outlives the milestone that
   first needed it.
5. **Epics and stories.** They stay in `docs/epics/<slug>/stories/`. The milestone lists its
   epics as today.
6. **Status and selection.** `milestone.md` takes the roadmap statuses: `proposed`,
   `approved`, `authored`, `delivered`, `superseded`. Author authors from the one approved
   milestone and fails when it finds two.
7. **Recording grills.** The milestone skill tells the session to write each grill tree into
   `grills/`, or the human asks for it. The grill skill itself does not change.
8. **Session order in the milestone skill.** Write `milestone.md`, grill it, run decompose
   where a design is needed, write a mockup for each journey through a web or mobile book,
   pass doctor, and the human sets `approved`.
9. **Ready gate.** ostler's doctor checks a milestone folder before it can be `approved`:
   required sections, resolving links, a mockup for every web or mobile journey, and no
   `Open Decisions` section. Author refuses a milestone that fails it.
10. **Skills.** The milestone skill replaces `workhorse-workflows-author-roadmap`. The
    pipeline pattern is documented in `workhorse-engine`.
11. **Migration.** `acme` holds the only milestone, and its epics and stories already exist.
    It is migrated by hand, and only the new format is supported.

## Docs location, workspaces and services

12. **What a service is.** Both a book inside one product repo and a separate repo in a
    multi-repo workspace.
13. **One docs location per run.** A run launched without `--workspace` uses the repo's
    `docs/`. A run launched with it uses `<artifacts_dir>/docs/`. The two are never mixed,
    and nothing searches across locations.
14. **No workspace segment.** `<artifacts_dir>/docs/` is one tree for every workspace. A
    workspace uses a subset of the whole, and two workspaces may share repos.
15. **docRoots.** The `docRoots` key is removed. The artifacts dir in the home config is the
    only location setting.
16. **Rename.** `features` becomes `services` all the way down: the directory, ostler's code
    names, the skills and the prompts. The old name fails doctor. stablemate, `acme` and
    `globex` move with `git mv`.
17. **Book names.** Book names are unique, so a book lives at `docs/services/<book>` in either
    location.
18. **Naming a workspace.** The home config holds `workspaces: {name: [folders]}`. Every
    workflow takes `--workspace <name>`, which replaces the coder's `.code-workspace` file.
    The `agents.yml` section `workspace:` becomes `services:`, since it marks the services
    inside one repo.
19. **The artifacts repo.** stablemate runs `git init` on the artifacts dir, with no remote.
    `docs/` is tracked and `specs/` is gitignored. Changes stay local, and the human pushes
    when there is a remote.
20. **The coder and the artifacts repo.** The coder treats the artifacts dir as one more
    workspace member under the same branch policy. With no remote, it merges story branches
    there locally and never pushes or opens a PR.
21. **Story services.** A story lists its services by book name, `services: [api, web]`.
    The coder passes them into the dev prompt.
22. **UI book.** A book whose driver is `web` or `mobile`.

## Author as a pipeline

23. **Pipeline semantics.** The stablemate counterpart of a workflow `pipeline(found.files,
    file => ...)`: a kind on the run's work list is the list of items. Items run one at a
    time, in chunks. There is no parallel work.
24. **Call site.** `return self.pipeline("epic", to=EpicAuthor, n=1) or Continue(None,
    self.split_stories)`. `to` takes a state or a sub-flow. The run's work list is implicit,
    and an item settles when its target returns.
25. **Filling a kind.** A barrier state fills the next kind from the ostler graph. The graph
    is the source of truth, and a stage that also wrote items would keep a second record of
    the same fact.
26. **Stage chain.**
    1. Split the milestone into epics, check epic coverage, PM review. Barrier, fills `epic`.
    2. Pipeline `epic` to the epic author.
    3. Pipeline `epic` to the story split, with story coverage and the PM review. Fills
       `story`.
    4. Pipeline `story` to the story author. A UI story gets its mockup first, then the PM
       reviews it.
    5. Finalize.
27. **Completion.** Every work-list item is done at the end of a run. Otherwise Finalize stops
    at a gate that lists the unfinished items, and the answer requeues them with that answer
    as context. The milestone becomes `authored` only when the work list is complete.
28. **Missing mockup.** A UI story with no mockup blocks that story only.

## The PM

29. **Sole reviewer.** The PM is the only agent reviewer. It replaces the epic-split review,
    the coverage review and the story audit.
30. **Deterministic checks.** They stay, as lint. A passing check says the graph is well
    formed and nothing about what it means.
31. **Angles.** Each stage has a fixed list of angles in code, one prompt per angle.
32. **Sub-PMs.** The PM turn spawns one sub-PM per angle through the agent CLI's subagent
    tool. Micromanaging agents from the engine has proved slow. A CLI with no subagent tool
    has the PM review every angle in its own turn.
33. **Product answers.** The PM also answers product questions, by filling gaps only. It
    infers scope from the milestone, past decisions and the books. A question whose answer
    would change the release contract goes to the human.
34. **PM memory.** A fresh turn answers each question. Answers go to `grills/pm.md`, which
    every later turn binds to and the human can edit to overrule.
35. **Mockup agreement.** The PM judges whether a story mockup agrees with the milestone
    mockup, against the design skills and the requirements.

## Deliveries, in order

1. The `features` to `services` rename, named workspaces, the artifacts git repo and the
   coder migration.
2. The milestone folder, its skill, the doctor gate, Author's intake and the `acme`
   migration.
3. The pipeline primitive, the stage chain and the completion gate.
4. The PM, required mockups and the story `services` field.
