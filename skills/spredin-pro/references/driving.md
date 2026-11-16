# Operating Spredin Pro on screen

For computer use: screenshots, clicks and keys. Keys here are the Mac's; on
Windows read windows.md for the differences.

## Before you start

- Take a screenshot first. A launch may show **Recover unsaved work?** (a crash
  left work behind): ask the user, do not decide for them.
- Find the four places you will use: the **name box** (left, above the grid), the
  **formula bar** (`fx`, right of it), the **menu row** and the **status bar**.
- Zoom in on the area you need instead of reading a whole-screen picture.

## Say that the changes are yours

Spredin cannot tell your keys and clicks from the person's. So that its Edit
History records what you change as Claude's:

1. ⌘K, type `mark changes`, choose **Edit History: Mark Changes as Claude's**,
   Return. A
   banner appears: "Changes are being recorded as Claude's." If the status
   bar says to turn on Keep Edit History first, tell the person; do not turn
   it on yourself unless they ask.
2. Do the work.
3. ⌘K → **Edit History: Stop Marking Changes as Claude's** (or the banner's
   **Stop**) when you
   are done, before the person works again.

Marking works in the window it was turned on in, and ends when that window
closes: turn it on in each workbook's window you work in.

If the Spredin connector's tools are available, use them instead of the
screen (connector.md): Spredin records those changes as Claude's by itself.

## Go to a cell, and select

1. Click the **name box**, type an address, press Return: `B7`, `A1:D20`,
   `'Sales 2026'!A1`, `Sales!C3`, or a defined name. The cell is selected and the
   keyboard is on the grid.
2. Or click a cell. Shift-click extends a selection; ⌘-click adds another area.
   Click a column letter or row number to select a whole column or row.
3. Arrows move one cell; ⌘+arrow jumps to the edge of the data; ⇧ extends.

## Enter and change content

- With a cell selected, **type**: it replaces the content. **Return** commits and
  moves down, **Tab** moves right, an **arrow** commits and moves that way (as in
  Excel), **Escape** cancels.
- Edit what is there: **F2** (or double-click the cell), or click the **formula
  bar**, change the text, press Return. In this edit mode the arrows move the text
  cursor; F2 switches between the two modes.
- A formula: type `=` then the formula, e.g. `=SUM(B2:B40)`, Return. While typing
  a formula, an arrow key right after an operator, `(` or `,` picks a cell
  reference (as in Excel).
- A line break inside a cell: ⌥Return.
- The same entry in every selected cell: select, type, ⌘Return. A formula's
  references follow each cell.
- Fill a column without dragging: put the formula in the top cell, select from it
  down to the last row (name box `E2:E500`), press ⌘D (Fill Down).
- Delete clears contents only; Format → Clear Formats clears formats.
- Undo ⌘Z, redo ⇧⌘Z.

## Read what is in the cells

The grid is a drawn picture: accessibility tools see the menus, buttons, name box,
formula bar and status bar, but not the cells. So:

- **One cell, exactly**: select it (name box), then read the **formula bar**. It
  holds the exact content: a formula as `=...`, a number without its format.
- **What the user sees**: zoom a screenshot. Values are shown with their number
  format; `#####` means the column is too narrow for the number.
- **Totals of a selection**: select the range and read the status bar (Count,
  Sum, Average, Min, Max). Wait if it says "Calculating…".
- **Many values**: do not read them off screenshots. Use the Python panel
  (`print(sheet.read_values('A1:F40'))`, then read the Output pane), or export the
  sheet (File → Export Sheet as CSV…) and read the file.
- **Why an error**: hover the error cell; a note says what went wrong.

## Commands

- **⌘K** opens the command palette: type a few words of a command ("freeze top
  row", "remove duplicate", "pivot"), Return. Every menu item is there. This is
  the most reliable way to run a command.
- The menu row works too (menus.md lists every item). On the Mac, the menu bar's
  Help menu has a search box that finds every command.
- Right-click menus, dragging the fill handle and dragging charts need precise
  pointer work; prefer the menu or palette command that does the same.

## Dialogs and prompts

- Dialogs open inside the window. Read every button. Escape closes most of them
  without changing anything.
- **Closing with unsaved changes**: Don't Save / Cancel / Save. Never choose
  Don't Save unless the user said to discard the changes.
- **Replace?** when saving over a file, and **the file was changed by another
  app**: ask the user.
- Saving the first time opens the system's save panel: the name field, the
  folder, a **File Format** menu, Save. The menu has five choices: Spredin
  Workbook, Excel Workbook, CSV, TSV and JSON (and Excel Macro-Enabled
  Workbook for a workbook that came with macros). CSV, TSV and JSON write a
  copy: the document stays as it was, and unsaved.
- **Run a script from this workbook?** means the workbook came with someone
  else's scripts. Stop and ask the person; never press Run Script for them.

## The Python panel (for many cells at once)

1. Tools → Show Python Panel (or ⌘K "Python").
2. Put your script in a new file: open the file list (the button with the
   current file's name, in the panel's top bar), click **+** (New script
   file), then click into the new file's editor. Do not paste over a script that
   is already there: it is the person's. Pasting from the clipboard is the
   cleanest way to put a script in: the editor indents new lines by itself, so
   typing a long script line by line can double its indentation.
3. Press **Run** (⌘Return). The Output pane shows what the script printed, and a
   traceback if it failed. The whole run is one undo step. If **Run a script
   from this workbook?** appears, stop and ask the person (Dialogs, above).
4. Show the user the script before you run it if they have not seen it.

The API: python-api.md. A script works on the open workbook only; it cannot read
files on the computer unless the user allows it when asked (`open_file`).

## When the app is busy

After a large change (a sort of many rows, a big paste, opening a large file) the
app may keep working for a moment: the status bar shows progress, and a sheet
still loading has a marked tab and cannot be edited. Wait before reading values.
If a click seems to do nothing, take a new screenshot before trying again: the
first click after a menu was open may only close the menu.
