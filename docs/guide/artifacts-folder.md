# The artifacts folder

The artifacts folder is the one place agents write what you do not review beside the code. It is a
git repository on your machine, `~/Documents/ai-artifacts` unless the home config names another.
`ostler` creates it on first use and never adds a remote.

Every path below is printed by a command. An agent asks the command and never builds the path by
hand.

## Layout

```
<artifacts>/
  company/<slug>.md                               company book, written by people
  teams/<team>/<slug>.md                          team book, written by people
  products/<product>/
    <slug>.md                                     product book, one page per rule
    milestones/NNNN-<slug>/milestone.md           a release contract, with its mockups beside it
    designs/<slug>.md                             a design note a milestone links
  services/<repo>/<name>/                         service book of one service of one repository
    decisions/<slug>.md                           why, tied to an element of that service
  services/<repo>/ops/stack.yml                   the repository's stack root

  epics/<epic-id>/epic.md                         untracked from here down
  epics/<epic-id>/stories/<story-id>/story.md
  specs/<story-id>/                               plan, review and QA files of one story
  backlogs/<repo>/<area>/<id>/record.md           the register
  notes/<repo>/<slug>/                            an agent's working notes
  researches/  benchmarks/  scratch/
```

Git tracks the top half. The bottom half stands in for a ticket board or a scratch pad, and the
artifacts repository ignores it.

| Document | Command that prints its place |
| --- | --- |
| milestone folder | `ostler path milestone <slug>` |
| design note | `ostler path design <slug>` |
| working notes | `ostler path notes <slug>` |
| epic folder | `ostler path epic <slug>` |
| story file | `ostler path story <story-id>` |
| spec folder | `ostler path spec <story-id>` |
| decision | written by hand into the service book's `decisions/`, listed by `ostler book decisions <module>` |
| product, team and company pages | `ostler book pages` |
| service book | `ostler book files <module>` |

Run each command from the code repository. Run in the artifacts folder itself, `ostler` knows no
product, so it lists every product's pages and refuses to create a milestone.

## How a repository reaches its product

Two names file everything. Both come from the code repository's `agents.yml`.

```yaml
book:
  product: acme        # default: the repository's name
  team: platform       # default: none, and then no team book is read
```

- **The repository name** files what belongs to one codebase: its service books under
  `services/<repo>/`, its register under `backlogs/<repo>/` and its notes under `notes/<repo>/`.
  The name is the workspace member name, else the folder name in lower case.
- **The product name** files what several codebases share: the product pages, the milestones and
  the design notes under `products/<product>/`.

A product with an API repository and a web repository gives both the same `book.product`. Each
keeps its own service books. Both read the same product pages and the same milestones.

The link goes one way. A repository names its product. Nothing under `products/<product>/` lists
its repositories. A repository with no `book.product` is a product of its own.

`ostler book search` started in a repository reads the company pages, its team's pages, its
product's pages and its own service books. It reads another repository's book only when
`--service services.<other>.<name>` names it.

## What stays in the code repository

- The code, and its `agents.yml`.
- Run folders under `.agents/`.
- The book, for a tool that publishes its own: `book.home: repo` keeps `services/<name>/` and
  `product/` in the repository. Milestones, designs and notes still go to the
  artifacts folder.

A repository or an artifacts folder that still holds `docs/decisions` or
`docs/milestones` is in the old layout. `ostler` refuses to read it and prints the commands that
move it.
