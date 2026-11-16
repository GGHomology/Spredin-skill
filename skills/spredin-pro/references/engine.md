# How Spredin decides

What an agent needs to predict the app's results. Function by function:
functions.md. How formulas are checked against Excel, with the figures:
https://spredin.com/benchmarks.

## Calculation

- Formulas are Excel's: the same syntax, operator precedence (`=-2^2` is 4), and
  389 functions, including LET, LAMBDA (with MAP, REDUCE, SCAN, BYROW, BYCOL,
  MAKEARRAY), XLOOKUP, the -IFS family, FILTER, UNIQUE, SORT, SEQUENCE, SUBTOTAL,
  AGGREGATE, the finance, statistics and matrix functions.
- Only what an edit can change is worked out again, and what is on screen first.
  A large edit finishes in the background: the status bar says so, and values
  that are not yet known show their old text dimmed.
- TODAY, NOW, RAND and RANDBETWEEN are worked out when the file opens and again on
  F9 (Data → Calculate Now), not on every edit.
- A circular reference shows `#CIRC!`. There is no iterative calculation.
- Numbers are 64-bit floating point, shown to 15 significant digits, as in Excel.
  ROUND rounds the decimal number you see (`ROUND(1.005,2)` is 1.01).
- A result with several values does not spill: the cell shows the first value.
  Wrap it in something that takes an array (SUM, INDEX, COUNTA, TEXTJOIN).
- A cell from Excel 365 that spilled keeps the values Excel last saved in the
  cells it spilled into; those do not recalculate.

## Values and comparisons

- An empty cell is 0 in arithmetic and left out by SUM and AVERAGE. A formula's
  `""` is text: `=A1+1` on it is `#VALUE!`.
- In `=`, `<`, `>`: every number comes before every text, and text before FALSE
  and TRUE; different kinds are never equal (`="5"=5` is FALSE). Text compares
  without regard to capitals, except EXACT and FIND. One exception, on purpose:
  a number from a cell against text that reads as a number compares by its
  digits, so `=A2="5"` is TRUE when A2 holds a typed 5 (Excel says FALSE).
- An empty cell equals 0, `""` and FALSE.
- Errors pass through functions unless catching them is the function's job
  (IFERROR, IFNA, the IS functions, AGGREGATE with an option that skips them).

## Entry: what typed, pasted or CSV text becomes

| Text | Becomes |
|---|---|
| `1,200` · `$1,200` · `€3.5` · `(1,200)` · `50%` | a number with a matching format |
| `2024-01-15` · `1/15/2024` · `5 Mar 2025` · `12:30` · `9:30 PM` | a date or time (a slashed date is read in the order of the computer's region) |
| `1 1/2` | 1.5 with a fraction format |
| `TRUE` · `false` | a logical value |
| `#N/A` and the other error names | that error |
| `007` · more than 15 digits · `SEPT2` · `Mar 2025` · `3/4` | text, as written |
| `'007` · `'=x` · `'TRUE` | text (the apostrophe is not shown) |
| `'tis` · `'s-Hertogenbosch` | text with its apostrophe: before an ordinary word it is a character |
| `=…` | a formula; one that cannot be read stays a formula and shows `#ERROR!` (only CSV import turns it into text) |

A Python script is exempt: `sheet.set(r, c, "50%")` writes the text `50%`; a
Python date, or ISO text like `2024-01-15`, becomes a date. Files you write are
stored as written (files.md).

## On purpose different from Excel

- **Text that is a number counts as one**: a cell a file stores as text but
  holding `1200` adds up in SUM and is found by VLOOKUP. Excel leaves it out.
- **IDs stay as written**: `007` keeps its zeros, a 19-digit account number every
  digit, `SEPT2` is not a date. Lookups (VLOOKUP, MATCH, XLOOKUP) find each ID
  on its own row. COUNTIF, SUMIF and the -IFS functions still match `007` with
  `7`, as Excel does.
- **SUMIF and COUNTIF over a closed linked workbook** answer from the values the
  file keeps (Excel shows `#VALUE!` until the other file is opened).
- **A tiny difference left by `+` or `-` is 0 wherever it arises**:
  `=(0.5-0.4-0.1)=0` is TRUE. A result smaller than 2^-48 of its numbers is
  taken as 0 (Excel does that only for a formula's last step outside
  brackets, so it says FALSE here).
- **Number-like text against a cell's number** compares by its digits (see
  Values and comparisons).

## Filling

- **Fill handle / series**: `1, 2` continues 3, 4…; `Item 1` continues Item 2;
  `Q1` runs to Q4 and starts again; day and month names continue (Mon, Tue… /
  Jan, Feb…); a date steps a day (two dates a month apart step by month). A
  single number is copied; hold ⌥ while dragging to count up instead.
- **Formulas move as in Excel**: relative references shift with the cell, `$`
  pins a column or row (`$A$1`, `A$1`, `$A1`).
- **Fill Down / Right / Up / Left** (⌘D, ⌘R, ⇧⌘D, ⇧⌘R) copy the first (or last)
  row or column of the selection over the rest. **Double-clicking the fill
  handle** fills down as far as the column beside it goes.
- Scripts: `sheet.fill_down('E2:E500')` copies E2 down; there is no series fill
  from a script (write the values).

## Sorting, duplicates, filters

- Sort and Remove Duplicates work on the table around the active cell (Excel's
  current region: up to blank rows and columns) or on the selection. The header
  row is found the way Excel finds it and stays put.
- Formulas in sorted rows are moved as cut-and-paste moves them, so totals stay
  right. A range containing merged cells is not sorted (the status line names
  the merge).
- Remove Duplicates compares what the cells show.
- A filter hides rows; SUBTOTAL 1–11 leaves out filtered rows, 101–111 every
  hidden row. Charts show only visible rows.

## Rows, columns, cut and paste

- Inserting or deleting rows and columns moves references as Excel does; a
  reference to a deleted cell becomes `#REF!`; a range shrinks or grows.
- Cut and paste moves: formulas that read the cells follow them.
- Paste starts at the top-left of the selection; one copied cell fills a selected
  range. Paste Values pastes each cell's worked-out value with every digit (not
  the formatted text it shows).

## Undo

- Every action is one step: a paste, a sort, a fill, a whole script run, an
  assistant change. Up to 200 steps are kept, fewer after very large changes
  (the steps kept hold about a million cells in all). Opening another file
  starts a new list.

## Large workbooks

- Rows up to 4,194,304, columns up to ZZZZ. An `.xlsx` opens a sheet at a time;
  a sheet still loading is marked and read-only.
- A `.sprd` keeps a filled-down column of formulas as one line, so large files
  stay small.
- Tools → Workbook Health… lists what makes a workbook slow, large or wrong.
