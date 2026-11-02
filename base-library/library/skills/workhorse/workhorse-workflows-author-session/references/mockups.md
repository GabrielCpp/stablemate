# Story mockups

A coder run copies the mockup, so everything on it gets built. Read this before writing the
first mockup of an epic, and when a rendered state looks wrong.

## How to build them

- Build one shell of the product's real chrome and one page per epic, then generate each
  story's self-contained `mockup.html` from them. A shared shell keeps a figure from drifting
  between stories, and one fix reaches them all.
- Give each mockup a state switcher with one entry for every state the story's criteria name:
  the loaded view, reading, failed and retried, empty, and each special case.
- Look at the render. Screenshot every state, and read the screenshots on a contact sheet. The
  source of a mock hides what the operator sees.

## What a state shows

A mockup shows what is true when its story lands. A column or a tab that a later story adds
stays off this one, and an earlier story's work stays on.

The page carries product content only. A note such as "unchanged until story 5" or "this tab
arrives later" reads as copy, and a builder ships it.

## Defects to look for on every sheet

- A figure from another story, or a figure that differs from its twin elsewhere on the page.
- Parts that do not add up to their total: headings against the timeline, a column against its
  tile, status bar counts against the rows.
- A selected row that disagrees with the pane beside it.
- A finished item that still shows a running chip or a live control.
- A half-width list where the full table belongs, or a blank pane.
- A narrowed row that wraps.
- A status told by color alone.
- A breakdown that keeps its last selection after the state changes.
