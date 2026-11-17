# Journal lists grouped by publisher (branch journal-groups, 2026-11-17)

Matthew: "I really like the way prose organizes the view of journals in the drop down by
publishing group. Can we add that same grouping structure to mosaic?"

## What he sees

Every list of journals in mosaic is now grouped by publisher, the way prose's Journal list is:
a heading for each publisher, in alphabetical order, with its journals under it in alphabetical
order.

AAAS (Science) · BMC (Springer Nature) · Cell Press · Cold Spring Harbor Laboratory Press ·
Genetics Society of America · In house (bioRxiv) · My journals (his own, when he has any) ·
National Academy of Sciences · Oxford University Press · PLOS · Springer Nature · Wiley

- **Size ▸ Journal**: a heading over each publisher's journals (the picture in the guide,
  `docs/images/journalmenu.png`).
- **Page panel ▸ Journal**, **Check ▸ Check against**, **Settings ▸ New documents ▸ Page size**:
  the same groups as headed sections of the drop-down list.
- **`mosaic export --journal`** with a name mosaic doesn't know lists the ones it does, by
  publisher. (There is no Export ▸ for a journal in the window: relabelling for a journal is only
  the command line's `export --journal`.)
- Typing a letter still jumps to the first journal starting with it, in the Size menu and in the
  drop-down lists.

## Where the groups come from

One place for both apps: the shared journal table (labapp `journals.py`, `PUBLISHERS`, put on
each journal as `"publisher"`), with the same names prose's Journal list has always shown.
prose now reads them from there too, and shows exactly what it showed before (its whole journal
list compared before and after: identical). A person's own journals carry none; both apps list
them as "My journals". bioRxiv is "In house", where prose lists its bioRxiv (in house) template.

## Decided on my own

- The field is called `publisher` (prose's own word for it), not `group`.
- In the Size ▸ Journal submenu, the line between journals inside one publisher's group is gone:
  the publisher headings and a line between groups separate them, as prose's list does.
- Settings' New documents list had a group per journal; it now has a group per publisher (each
  line still starts with the journal's name).
- The command line's "no journal called …" message lists the journals by publisher.

## Branches and commits

- labapp `journal-groups` (worktree `~/Projects/labapp-worktrees/journal-groups`): the field.
- mosaic `journal-groups` (this one): re-vendored labapp, the grouped lists, tests, guide.
- prose `journal-groups` (worktree `~/Projects/prose-worktrees/journal-groups`): re-vendored
  labapp; `journals.py` SETUP drops its publisher column and reads the shared table's.
  Merge note: the journal-format work rewrites the same tables; keep reading the publisher from
  the shared table.

## Tests

- mosaic pytest: 352 passed, 7 skipped (new `tests/test_journal_groups.py`); headless editor
  self-test 788/788 (new checks in `--only sizes`, `--only journals` and the Check part).
- labapp pytest: 43 passed. prose pytest: 660 passed, 6 skipped; editor tests 393 passed.
- WebKit self-test in the app's window (hidden, scratch MOSAIC_HOME, MOSAIC_FAKE_CLIPBOARD=1):
  789/789, `SMOKE ready errors=[]`.
- Not run: the real-keyboard smoke run (presses real keys on his Mac).
