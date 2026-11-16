<!-- Generated from Spredin Pro 1.0.4 (src/App.tsx menus, English strings) by tools/gen-refs.mts. Do not edit by hand. -->

# Menus (Spredin Pro 1.0.4)

The menu row inside the window, in English. On the Mac the menu bar at the top of the
screen has the same menus. Every item is also in the command palette (⌘K on the Mac,
Ctrl+K on Windows): type a few words of its name. Some items show only in the desktop app
or when a setting is on; a label "A / B" is one item that reads A or B by state.


## File

- **New Workbook** (⌘N) — Open a new window with an empty workbook
- **Open…** (⌘O) — Open a file — .sprd, .xlsx, .xls, .csv or .tsv
- **Save** (⌘S) — Save the whole workbook (Python scripts included) as a .sprd file
- **Save a Copy… / Save As…** (⇧⌘S) — AutoSave is on, so this writes a copy; the workbook keeps saving to its own file.
- **Save a Copy Without Scripts…** — Write a second file with the Python scripts left out — the open workbook is untouched
- **Revert To** — Go back to an earlier version of this workbook
  - **Last Opened** — Put the workbook back the way it was when you opened it. What is there now is kept as a version.
  - **Browse Versions…** — See the earlier versions Spredin kept of this workbook, and restore one
- **Export Workbook as Excel…** — Export every sheet to one Excel .xlsx workbook
- **Export Workbook as JSON…** — All sheets' computed values as JSON — no styling or formulas
- **Export Sheet as CSV…** — Export this sheet's values to a .csv file
- **Export Sheet as TSV…** — Export this sheet's values to a tab-separated .tsv file
- **Export as PDF…** — Save the sheet as a PDF — the same pages Print makes
- **Print…** (⌘P) — Print the sheet, a selection or the whole workbook, with a preview
- **File Formats & Fidelity** — How Spredin reads and writes .sprd / .xlsx / .csv / .json — what survives, what does not

## Edit

- **Undo** (⌘Z) — Undo the last change
- **Redo** (⇧⌘Z) — Redo the last undone change
- **Cut** (⌘X) — Cut the selection to the clipboard
- **Copy** (⌘C) — Copy the selection to the clipboard
- **Paste** (⌘V) — Paste from the clipboard
- **Paste Values** — Paste values only — drop formulas and styling
- **Paste Formulas** — Paste formulas, adjusting their cell references
- **Paste Formats** — Paste only the cell formatting
- **Paste Transposed** — Paste turned: rows become columns and columns rows
- **Paste Values Transposed** — Paste values only, turned: rows become columns
- **Fill Down** (⌘D) — Copy the top row of the selection down over the rest (formulas shift).
- **Fill Right** (⌘R) — Copy the left column of the selection right over the rest (formulas shift).
- **Fill Up** (⇧⌘D) — Copy the BOTTOM row of the selection up over the rest — put the formula on the last row, select up, done.
- **Fill Left** (⇧⌘R) — Copy the RIGHT column of the selection left over the rest.
- **AutoSum** (⇧⌘T) — Add a total of the numbers above or to the left (⇧⌘T)
- **Find & Replace…** (⌘F) — Find and replace text in the sheet

## Insert

- **Chart from Selection…** — Insert a chart from the selected range
- **Slides** — Slide decks linked to this workbook: tables, charts and KPIs that follow the cells
- **Pivot Table…** — Summarise data into a pivot table on a new sheet
- **Comment on Cell…** — Add or edit a comment on the active cell
- **Define Name…** — Name a cell or range (use it in formulas: =SUM(Revenue))
- **New Sheet** — Add a new blank sheet
- **Rename Current Sheet** — Rename the current sheet
- **Delete Current Sheet** — Delete the current sheet
- **Hide Sheet** — Hide this sheet's tab; its cells still count in formulas
- **Unhide Sheet** — Show a hidden sheet's tab again

## Format

- **Format Cells…** (⌘1) — Set number format, font, alignment, borders and colours in one place
- **Custom Number Format…** — Type a number format code, as in Excel's Custom category
- **Conditional Formatting…** — Highlight cells by rules, colour scales or data bars
- **Borders** — Draw borders on the selected cells: one edge, a box or every line, in the line style and colour chosen.
  - **More Borders…** — Set number format, font, alignment, borders and colours in one place
- **AutoFit Column Width** — Fit the selected columns to their widest value
- **AutoFit Row Height** — Fit the selected rows to their tallest cell
- **Merge / Unmerge Cells** — Merge the selected cells into one
- **Merge & Combine Values** — Merge cells and combine their text
- **Split Cell by Symbol…** — Split the cell's text into columns by a delimiter
- **Clear Formats** — Remove all styling from the selected cells (contents stay)

## Data

- **Sort Selection ▲** — Sort the selection A→Z (ascending)
- **Sort Selection ▼** — Sort the selection Z→A (descending)
- **Sort by Multiple Columns…** — Sort by several columns with a custom order
- **Sort Table ▲** — Sort the table around the active cell by its column, smallest first
- **Sort Table ▼** — Sort the table around the active cell by its column, largest first
- **Filter (AutoFilter)** — Turn on AutoFilter dropdowns over the selection
- **Clear Filter** — Turn AutoFilter off and show all rows
- **Remove Duplicate Rows** — Remove duplicate rows from the selection
- **Data Validation…** — Restrict what a range accepts: a dropdown list or number/date/length rules
- **Connect to Database…** — Connect to a PostgreSQL, MySQL or SQLite database and import a query (read-only)
- **Open File as Data Table…** — Open a large file as a fast scrolling data table
- **Calculate Now** (F9) — Work out TODAY, NOW, RAND and the formulas that read them again

## Rows/Cols

- **Insert Rows** — Insert blank rows at the selection
- **Insert Columns** — Insert blank columns at the selection
- **Delete Rows** — Delete the selected rows
- **Delete Columns** — Delete the selected columns
- **Hide Rows** — Hide the selected rows
- **Hide Columns** — Hide the selected columns
- **Unhide Rows** — Reveal hidden rows within the selection
- **Unhide Columns** — Reveal hidden columns within the selection
- **Freeze Panes** — Freeze rows and columns above and left of the selection
- **Freeze Top Row** — Freeze the top row so it stays visible while scrolling
- **Freeze First Column** — Freeze the first column so it stays visible
- **Unfreeze Panes** — Unfreeze all panes
- **Gridlines** — Show or hide this sheet's gridlines; borders and fills stay

## Tools

- **Hide Python Panel / Show Python Panel** — Show or hide the Python scripting panel
- **Hide Assistant / Show Assistant** — Ask questions about your data or ask for changes, in a conversation
- **Hide History / Show History** — See what changed, when and by what, cell by cell, and put any value back
- **Search All Actions…** (⌘K) — Search every action in the command palette
- **Workbook Health…** — Find what is making this workbook slow, big or wrong — and what to do about it

## Settings

- **AutoSave & Versions** — Turn AutoSave on or off, see and restore earlier versions, and choose how much is kept and where
- **AI Model** — Choose the AI backend: local Ollama, an OpenAI-compatible endpoint, or Anthropic
- **Script Time Limit** — How long a script may run before it is stopped
- **Suggest Formulas as I Type** — While you type a formula, suggest the rest from the sheet around it; Tab takes it
- **Formula Preview** — Show the selected cell's formula typeset as mathematics, under the formula bar
- **Edit History**
  - **Keep Edit History** — Record every change so History can show it and undo from any point. The record stays on this Mac, beside the file: a copy, or a file you send, carries none.
  - **Record More Detail** — With Keep Edit History on, also note what a connected AI app read, and keep the script or cells each AI change was approved as.
  - **Mark Changes as Claude’s** — Record the next changes in Edit History as made by Claude: for Claude working in Spredin on screen.
- **Connect AI Apps** — Let an AI app on this Mac, such as Claude, read your open workbooks and ask to change them; changes are shown to you first unless you apply them without asking.
- **Excel Key Chains (⌥)** — Tap ⌥ (Option), then Excel's Alt letters: E S V pastes values, H O I fits the columns, D F F filters; Esc cancels
- **Keep Excel Content in Spredin Files** — A workbook opened from Excel keeps its pictures, pivot tables and charts as Excel drew them in its .sprd, so saving it as Excel later puts them back. Off makes smaller files; saving as Excel then says what is missing.
- **Save Workbooks in Compact Form** — A filled-down column of formulas, and a block of cells with one format, is written once instead of cell by cell: smaller files that open faster. Off writes every cell's text, as earlier versions did.
- **Zoom**
  - **Zoom In** (⌘+) — Make text, icons and the grid larger
  - **Zoom Out** (⌘−) — Make text, icons and the grid smaller
  - **Reset Zoom** (⌘0) — Back to the default size (115%)
- **Theme** — Switch the app's colour theme
- **Customise Themes**
- **Language** — Change the interface language

## Help

- **Send Feedback…** — Tell us what broke or what is missing — reports are what shape the next release
- **Rate Spredin Pro…** — Rate and review Spredin Pro on the App Store
- **Choosing an AI Model** — Run an AI model on this Mac — free, private, and offline
- **Coming from Excel?** — The Excel-to-Spredin transition guide: shortcuts, menu map, importing files, VBA→Python
- **Formula Reference** — Every function explained in plain words: what it is for, how Spredin works it out, how it compares with Excel, and an example
- **Assistant Guide (Pro)** — Spredin Pro: asking about your data, approving changes, memory, web search, what is kept
- **Slides Guide (Pro)** — Spredin Pro: decks linked to your cells — formatting, arranging, presenting
- **Python Scripting Guide** — Open the Python scripting guide
- **Agent / API Reference** — Open the Spredin API reference
- **Charting Guide** — Open the charting guide (types, options, ECharts, Python)
- **File Formats & Fidelity** — How Spredin reads and writes .sprd / .xlsx / .csv / .json — what survives, what does not
- **Check for Updates…** — Ask the download server whether a newer Spredin exists
- **About Spredin Pro** — Version and build information
- **Acknowledgements** — Open-source licences for everything Spredin ships
- **Privacy Policy** — What Spredin sends, to whom, and what stays on this Mac — opens spredin.com in your browser
