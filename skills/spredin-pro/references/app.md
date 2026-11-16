# The app

## Editions

- **Spredin Pro** (Mac App Store, paid). Everything below.
- **Spredin** (free, from spredin.com). The same spreadsheet, files and Python
  panel, without Pro's assistant, slides, edit history, formula preview,
  Connect AI Apps and Excel Key Chains.
  Each edition keeps the other's parts of a `.sprd` when it saves.
- Mac: Apple silicon (M1 or later), macOS 13 or later. Windows: planned.

## The window, top to bottom

1. **Title bar**: the document's name, a dot when there are unsaved changes, and
   the **AutoSave** switch (off by default).
2. **Menu row** inside the window: File, Edit, Insert, Format, Data, Rows/Cols,
   Tools, Settings, Help (the full list: menus.md). On the Mac the menu bar at the
   top of the screen has the same menus.
3. **Format toolbar**: bold, italic, colours, borders, alignment, number format.
4. **Name box and formula bar**: the name box (left) shows the active cell's
   address and takes an address to go to; the formula bar (`fx`) shows the active
   cell's exact content (a formula as `=...`) and can be typed into.
5. **The grid**: drawn as a picture (a canvas), so accessibility tools do not
   list its cells. Column letters across the top, row numbers down the left.
6. **Sheet tabs** at the bottom, with **+** for a new sheet and, in Pro, the
   **Slides** button.
7. **Status bar**: messages on the left; for a selection of several cells, its
   Count, Sum, Average, Min and Max on the right ("Calculating…" while working).

**Panels** open beside the grid, docked left, right or at the bottom, or in a
window of their own: **Python** (Tools → Show Python Panel), **Assistant** (Pro,
Tools → Show Assistant), **Slides** (Pro, the Slides button), **History** (Pro,
Tools → Show History, when Settings → Edit History → Keep Edit History is on;
it docks at the left or the right only).

**Command palette**: ⌘K on the Mac. Every menu item is in it; type a few words
("freeze", "pivot", "paste values") and press Return.

## Pro features, briefly

- **Assistant**: a chat about the open workbook, using the AI model the user
  chose (a hosted service with the user's own key, or a model on their computer).
  It asks before sending workbook data to a hosted service, shows each change as a
  card to approve (unless the user turned on Apply assistant changes without
  asking), and each change is one undo step. You normally do not need it:
  you are the assistant here.
- **Slides**: decks saved in the workbook whose tables, charts and numbers are
  links to cells, so they change when the cells do. Present, print, export PDF or
  HTML. Scripts drive them (python-api.md, "Slides").
- **Edit History**: off by default (Settings → Edit History → Keep Edit
  History). When on, every change is recorded cell by cell, with "Undo from
  here". The record is kept in Spredin's own folder on this Mac, not in the
  file or its folder: a copy of the file, or a file sent to someone, carries
  none. A change Claude makes through the
  connector is recorded as "Claude · connected"; on screen, as "Claude · on
  screen" while Mark Changes as Claude's is on (driving.md). Record More Detail
  (same submenu) also keeps what Claude read and each change's script or cells.
- **Connect AI Apps** (1.0.4 and later; Settings → Connect AI Apps, off by
  default): lets Claude Desktop use Spredin's tools through the Spredin
  connector extension (connector.md).
- **Formula Preview**: off by default; shows the active formula as mathematics.
- **Excel Key Chains** (Settings → Excel Key Chains): Windows Excel's Alt-key
  sequences on ⌥ (mac.md).
- **Help → Formula Reference**: every function in plain words (functions.md is
  the same content, shorter).

## Saving

- ⌘S saves; the first save asks where and in which format (Spredin Workbook
  `.sprd`, or Excel `.xlsx`). `.sprd` keeps everything; `.xlsx` says before
  saving what it cannot keep.
- With AutoSave on, changes are written a few seconds after they are made.
- Earlier versions of a Spredin Workbook are kept on this computer when it is
  saved, with ⌘S as well as with AutoSave (File → Revert To → Browse Versions).
- Closing a window with unsaved changes asks: Don't Save, Cancel, Save.
- Crash recovery keeps a snapshot of unsaved work, up to a size limit (the status
  bar says "No crash recovery" when past it).

## Limits

- Rows up to 4,194,304 (Excel: 1,048,576); columns up to ZZZZ (Excel: XFD).
  Saving as Excel asks first when a sheet goes past Excel's limits.
- Undo keeps 200 steps.
- A large `.xlsx` opens a sheet at a time; the tab of a sheet still loading is
  marked, and it is read-only until it has arrived.

## Not there yet

Spilling of multi-value results (wrap them, see SKILL.md); creating a structured
table with Ctrl+T (tables from `.xlsx` work); hyperlinks; cell and sheet
protection; Goal Seek and what-if tools; outlines and grouping; Flash Fill; rich
text inside one cell; diagonal borders; dragging sheet tabs to reorder; a Format
Painter button (copy, then Edit → Paste Formats); Power Query and Power Pivot
(Python covers the transformations, not refreshable steps or measures).
