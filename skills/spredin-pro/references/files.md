# Files

## Which format

| Format | Use it for | Notes |
|---|---|---|
| `.sprd` | Spredin's own workbooks; everything kept | gzipped JSON. Read and write with `scripts/sprd.py`. |
| `.xlsx` | Workbooks made with an Excel library (openpyxl, xlsxwriter), or shared with Excel users | Spredin opens values, formulas, formats, merges, widths, frozen panes, names, validation, conditional formats, charts, and works the formulas out on opening. |
| `.csv` / `.tsv` | One table of plain data | Spredin reads each field as if typed: `1,200` and `$5` become numbers, `2024-01-15` a date, `007` stays text. |
| `.json` | Computed values out of the app | File → Export Workbook as JSON: `{"sheets": [{"name", "rows"}]}`, values only. The app does not open JSON. |

To get **computed values** without the app doing it on screen: open the file in
Spredin and export CSV or JSON, or print them from a Python panel script.

## The one rule

Edit a file only while it is **not open** in Spredin. The app does not reload a
file changed on disk; it notices the change, pauses AutoSave and asks before
saving over it. So: ask the user to close the window, edit, then
`open -a "Spredin Pro" <file>` (mac.md).

## Cell contents in a file you write

- A number: plain digits, a point for decimals, no thousands separators or
  currency signs: `1200`, `-3.5`, `0.075`. The look goes in a number format.
  A whole number of 16 or more digits takes an exponent, as Spredin writes it:
  `1.234567890123456E+15`. Written out in full it is read as text (an ID).
- Text: as is. A digit string with leading zeros (`007`) or more than 15 digits
  stays text. A leading apostrophe forces text: `'1200`, `'=not a formula`.
- A formula: `=` and Excel's syntax: `=SUM(B2:B9)`, `='Sales 2026'!B7*Rate`.
- `TRUE` / `FALSE` are logical values; `#N/A` and the other error names are errors.
- A date: Excel's day number with a date format. In Python:
  `(date - datetime.date(1899, 12, 30)).days`, so 2026-11-15 is `46341`.
  Or a formula: `=DATE(2026,11,15)`. A time is a fraction of a day (`0.5` is noon).

## `sprd.py write`: a workbook from a spec

```json
{
  "sheets": [
    {
      "name": "Budget",
      "rows": [
        ["Item", "Jan", "Feb", "Total"],
        ["Rent", 1800, 1800, "=B2+C2"],
        ["Food", 412.35, 398.1, "=B3+C3"],
        ["Total", "=SUM(B2:B3)", "=SUM(C2:C3)", "=SUM(D2:D3)"]
      ],
      "cells": {"A6": "Updated", "B6": 46341},
      "formats": {"A1:D1": {"bold": true}, "B2:D4": "#,##0.00", "B6": "yyyy-mm-dd"},
      "widths": {"A": 140},
      "freeze": {"rows": 1, "cols": 0}
    },
    {"name": "Rates", "at": "B2", "rows": [["Rate", 0.075]]}
  ],
  "names": {"Rate": "Rates!$C$2"}
}
```

- `rows` start at `at` (default `A1`); `cells` set single cells after them
  (`null` empties one). Values: text, numbers, `true` / `false`, `null`.
  Numbers are written as Spredin writes them: `1234567890123456` in the spec
  becomes the number `1.234567890123456E+15`; give the digits in quotes for
  text (an ID).
- `formats`: a range and either a number format (see python-api.md, "Number
  formats") or an object with any of `numFmt`, `bold`, `italic`, `underline`,
  `color`, `fill` (`"#rrggbb"`), `align` (`left` / `center` / `right`),
  `valign` (`top` / `middle` / `bottom`), `wrap`, `fontFamily`, `fontSize`.
- `widths`: column letter → width in pixels. `freeze`: rows and columns kept in
  view. `names`: defined names.
- Charts, pivots, conditional formats, validation and slides are not in the
  spec: add them afterwards with a Python panel script, or write an `.xlsx`.
- It refuses to write over an existing file unless `--replace` is given, and
  checks sheet names as Excel does (at most 31 characters, none of `[ ] : * ? / \`,
  and no control characters).
- **It cannot change a workbook in place.** `write --replace` writes a new
  workbook from the spec alone: the old file's charts, scripts, slides,
  formats, names and document id are gone (so its Edit History starts over).
  To change an existing workbook, use the connector (connector.md) or a
  Python panel script (python-api.md).

## The `.sprd` layout (for reading, or writing by hand)

A `.sprd` is UTF-8 JSON, gzipped (the app also reads it unzipped).

```text
{ "spredin": 1, "active": 0,
  "sheets": [ { "name": "Sales",
                "rows":   { "0": "Region,Q1,Q2", "1": "East,1200,=B2*2" },
                "styles": { "0:0": {"bold": true}, "1:1": {"numFmt": "#,##0"} },
                "colW": {"0": 140}, "rowH": {}, "merges": ["A1:C1"],
                "freeze": {"rows": 1, "cols": 0},
                "charts": [...], "cf": [...], "validations": [...], "comments": {"1:0": "note"} } ],
  "names": { "Rate": "Sales!$B$2" },
  "scripts": [ {"name": "main.py", "code": "..."} ] }
```

- `rows`: one CSV line per non-empty row, keyed by the row index from 0; the
  fields are the cells from column A, quoted as in CSV when they hold `,` `"` or
  a line break. An empty field is an empty cell.
- `styles` keys are `"row:col"`, both from 0.
- `scripts`: the workbook's Python files. An old file may have one `script`
  text instead, which Spredin opens as `main.py`.
- `spredin` is the file's version: 1 (plain or dual) or 2 (compact). A whole
  number from 3 to 999 means a newer Spredin saved it: Spredin refuses to open
  it, and so does `sprd.py`.
- **The compact form**, which the app writes by default, has `"spredin": 2`, the
  real sheets under `compactSheets`, and under `sheets` only a stub named
  *Update Spredin* (for old versions). Read `compactSheets` when it is there.
  Each sheet may have:
  - `fills`: one line per filled-down range, `"E2:E200001 =C{row}*D{row}"`.
    `{row}` is the cell's own row number, `{row-1}` the row above, `{col}` its
    column letters, `{{` and `}}` a brace. The first cell holds the template
    read there; every other cell holds that formula moved to it, as the fill
    handle moves it (references written in capitals, without leading zeros).
    Spredin keeps a line only on the rules below.
  - `rows`: only the cells no fill gives; a cell in `rows` wins over a fill.
  - `formats` (`"A2:A200001 3"`) into `styleTable` (a list of formats), with
    `styles` holding only cells formatted by hand.
- **The dual form** (what Spredin writes when it saves a file it opened in
  the plain form) has `"spredin": 1`, full `rows` in `sheets` as the plain form has,
  and the `fills` and `formats` lines beside them. The rows hold every cell,
  so a fill line adds none: a cell the rows leave empty stays empty, even
  inside a fill line's range. Any file without `compactSheets` is read this way.
- Pro parts: `decks` (slides), `memory` (the assistant's note), `chat` (a kept
  conversation). Change slides with the Python deck API, not by hand.
- The app checks a file as it opens it: a part it cannot read is left out and
  named in the status line; a field it does not know is kept. Write the plain
  form (`"spredin": 1`, every cell in `rows`) and leave the rest to the app.

### Fill lines Spredin keeps

A line is a range, one space and a template. Spredin keeps it only if the
template is exactly what Spredin itself writes for the formula it reads at the
first cell: each relative row of a reference is `{row+k}`, and in a line wider
than one column each relative column is `{col+k}`. Absolute parts, text in
quotes, function names and sheet names stay as written. `{row+0}` is `{row}`.
So Spredin leaves out, with its cells:

- a placeholder inside quoted text: `A1:A3 ="Row {row}"`;
- a placeholder for an absolute part: `A2:A4 =$B${row}`;
- `{col}` in a line one column wide: `B2:B4 ={col}1*2`;
- a relative reference written out: `A1:A3 =B5` (write `=B{row+4}`);
- a line whose first cell is not a formula, or whose range or template
  cannot be read;
- a line over a cell an earlier line covers;
- a line that takes the sheet's lines past Spredin's limits: 20,000,000
  cells; 6,666,666 columns named by the lines (a line left out for covering a
  cell still counts its columns); 2^31 - 1 for the lines' cells times the
  length of their templates (counted in UTF-16 units, so an emoji is two);
  2^31 ranges moved to keep each column's lines in order.

A defined name spelled like a cell past column XFD (`Rate1`) is the name in a
template, not a reference. Spredin also knows the names of workbooks it opened
earlier; `sprd.py` knows only this file's.

`sprd.py read` applies all of this: it prints each cell's content as Spredin
reads it, with fills expanded in the compact form and the rows alone in the
others. A line Spredin would leave out is left out, and a note on stderr (and
in `info`) says how many. One difference: `sprd.py` also leaves out a line
with a row number, or a `{row+k}` step, of 2^52 or more, which Spredin's
numbers may not hold exactly. If you write fill lines by hand, run
`sprd.py info` on the file: no note means Spredin keeps them all.

## What `sprd.py` refuses, and what it shows

A `.sprd` can come from anyone, so `sprd.py` measures before it builds or
writes. Real workbooks stay far inside these (the largest measured hold about
14 million cells in a 420 MB text):

| Limit | Refused past it |
|---|---|
| The file on disk, and its text unzipped | 2 GiB each (Spredin's own longest text is 2^31 characters); unzipped a piece at a time, so a small file that unzips to more is refused holding nothing |
| JSON values and keys outside cell text | 50 million (each takes under 90 bytes once parsed) |
| A sheet's fill lines | Spredin's own limits (above): the line past one is left out, as in the app; 20 million steps to walk them row by row |
| One cell | 64 MiB of text |
| One row line | 1,048,576 cells (that row is left out) |
| `read` in the `cells` or `json` format, and `sheet_cells()` | 50 million cells listed |
| `read --format csv` | 10 million cells in the rectangle printed, empty ones included: a far-away cell makes a huge CSV, so read a part with `--range` |
| Formulas written out from fill lines | 2^31 characters in one `read` |

Fill lines are kept as rectangles and counted, never written out to be read:
`info` on a sheet of 20 million filled cells takes about as long as its rows,
and `read --range` writes out only the cells in the range.

On the screen (`info`, the `cells` format, the CSV printed without `--out`,
notes and errors), text from the file is shown with a backslash as `\\`, tab and
line ends as `\t` `\n` `\r`, and every other control or invisible character
(C0 and C1 controls, DEL, zero-width and direction marks, direction overrides
and isolates, the byte order mark, line and paragraph separators, the
invisible tag characters, a lone surrogate) as `\u{XXXX}`. The `json` format
writes them as JSON escapes, so the data is the same; a CSV written with
`--out` holds the text exactly (but a lone surrogate, which UTF-8 cannot hold).
