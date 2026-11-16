<!-- Generated from Spredin Pro 1.0.4 (src/script/api.ts) by tools/gen-refs.mts. Do not edit by hand. -->
# Python scripting API (Spredin Pro 1.0.4)

Scripts run in the Python panel (Tools → Show Python Panel), inside the app, on the open
workbook. One run is one undo step. numpy, pandas and scipy are bundled; nothing is
downloaded. A script cannot read files on the computer by itself: `open_file()` asks the
user. The same reference is on https://spredin.com/docs/api.

```text
Think in normal Python + pandas. `sheet` is the active sheet — read it into DataFrames, compute, write back. numpy/pandas/scipy are INSTALLED but NOT imported for you — write `import pandas as pd` / `import numpy as np` yourself before using pd/np, or you get NameError.

ROW NUMBERING — three systems, do not mix them:
- sheet.set/value/get are 0-INDEXED: row 0 is the top row (usually the header),
  so the first DATA row is row 1.
- sheet.rows counts EVERY used row INCLUDING the header. With a header, the data
  rows are 1 .. sheet.rows-1.
- sheet.read() turns the header into the DataFrame COLUMN NAMES, so it is NOT in
  the frame: len(df) == sheet.rows - 1. df.iloc[i] is sheet row i+1.
  Never index df with a sheet row number — that is off by one and runs off the end.
- A1 labels in FORMULAS are 1-BASED: sheet row r is spreadsheet row r+1. The
  formula for 0-indexed row r is "=B%d+C%d" % (r+1, r+1).
So: to fill a column, iterate `for r in range(1, sheet.rows)` and write with
sheet.set(r, c, ...); to read the same row from a DataFrame use df.iloc[r-1].
To copy a block somewhere else UNCHANGED, use read_values (keeps the header) and
write it — read() would silently drop the header row and shift everything up.

WRITE SCRIPTS THAT SURVIVE THE DATA CHANGING — the sheet summary gives exact
coordinates for the sheet AS IT IS RIGHT NOW. Use them to find things, but derive
sizes and offsets at run time (sheet.used_range, sheet.rows, len(rows)) instead of
pasting those numbers in as literals. The same script is run again after rows are
added, so "the block is 5 tall, so the next one starts at row 9" must be computed,
not hardcoded. (sheet.used_range is a PROPERTY — no parentheses.)

Read / write:
- sheet.read([range])  ->  Used range (or "A1:C20", "Sales!A1:C20", "A:C", or a sheet name) as a pandas DataFrame (row 1 = column names; empty cells None; an error cell is its text, e.g. "#DIV/0!", and read() prints a note when it meets one). A number heading stays a number (df[2023]); a date heading is the date it shows.
- sheet.read_values(range)  ->  A range as a plain 2D list (no pandas), INCLUDING the header row; empty cells None, an error cell its text ("#N/A"). Use this — not read() — to copy or move a block verbatim, since read() consumes the header into column names.
- sheet.write(data[, at='A1'], header=None, index=None, as_text=False, replace=False)  ->  Column names of a DataFrame go in the first row unless header=False. So write(df, "A2") puts the names in row 2 and the values from row 3; to write values under a header that is already there, pass header=False (a note is printed when the names land under themselves). Write a WHOLE DataFrame / Series / 2D list / numpy array at a top-left cell in ONE call (never loop); at may be "Report!A1". index: the index is written when it has a name or is not plain numbers (a groupby / pivot_table / describe result), not the 0..n numbering left by a read, filter or sort; index=True / False decides. A Series is a column of values (with its index, it gets a header row). A frame built from rows, pd.DataFrame(rows), has no names and none are written. Over a longer or wider table the old rest stays (a note says where); replace=True clears the table at the target first: write(df.drop_duplicates(), "A1", replace=True).
- sheet.write_col(col, values[, start_row=0], as_text=False)  ->  Write a list DOWN one column, from start_row (0 = the sheet's first row, the header row if there is one). col: index, letter ('E') or start cell ('E2'). as_text: True writes the values as text (a column of IDs).
- sheet.write_row(row, values[, start_col=0], as_text=False)  ->  Write a list ACROSS one row. as_text: True writes the values as text.
Cells:
- sheet.value(row, col) | sheet.value('A1')  ->  Computed value of one cell (None if empty, its text if an error). A formula that failed reads "#DIV/0!", "#N/A"…, never None.
- sheet.is_date(row, col) | sheet.is_date('A1')  ->  True when the cell shows a date or time. value() gives a date as a serial day number, so test this before adding a column up.
- sheet.get(row, col)  ->  RAW text of one cell — a formula comes back as its "=..." source, not its result.
- sheet.cell('A1')  ->  RAW text of one cell by A1 label.
- sheet.set(row, col, v, as_text=False) | sheet.set('A1', v)  ->  Write one cell; a "=..." string is a LIVE formula. A cell's type follows what is written: '345' is a number, '007' text, 'TRUE' a logical value; '1,200', '$5' and '50%' stay TEXT (convert them in Python, or use paste_csv). as_text: True writes the value as TEXT whatever it looks like ('345', '=not a formula').
- sheet.set_cell('A1', v, as_text=False)  ->  Write one cell by A1 label.
- sheet.rows  ->  Used row count (int).
- sheet.cols  ->  Used column count (int).
- sheet.col_letter(col)  ->  Column index -> letter (0 -> 'A', 26 -> 'AA'). Use this instead of writing your own.
- sheet.a1(row, col)  ->  0-based (row, col) -> an A1 label: sheet.a1(2, 1) -> 'B3'.
- sheet.used_range  ->  The used area as an A1 range, e.g. 'A1:E5' — pass it straight to pivot/cond_format/sort.
Spredin ops:
- sheet.chart(range, kind, title, **opts)  ->  ECharts chart bound to a range. kind: bar/stackedBar/horizontalBar/line/stepLine/area/stackedArea/pie/donut/rose/scatter/radar/funnel/polarBar/treemap/sunburst/heatmap/boxplot/candlestick/waterfall/histogram/range (waterfall = one column of changes, rows named Total/Subtotal/Opening or totals=[…] are totals; histogram = bins of one column, bins=, bin_width=, normal_curve; range = low, high, optional point per row, highlight_misses=True reddens intervals missing the first ref line; pie/donut/rose/funnel/treemap = sum per row; scatter = first col X + each other col a colored series; boxplot = a box per column; candlestick needs 4 cols named Open/High/Low/Close, or in that order). opts: x_title, y_title, y_min, y_max, legend, legend_pos, labels, label_fmt, gridlines, smooth, log_y, dual_axis, transpose (swap rows/cols), horizontal (swap X/Y), series_types=[…] (combo), zoom (slider), mean_line (average), toolbox, colors=[…], empty (gap default, zero or connect: empty cells and #N/A), refs=[{kind: line|band, value|from|to: number, cell B20 or =formula, label with {value}, axis: category for a category name or an =formula giving one}], trend (linear/exp/log/poly2/movingAvg) + trend_label/trend_period, color_by_sign, end_labels, or echarts={…} (raw ECharts fragment, deep-merged — full library). See the Charting guide.
- sheet.merge(range, combine=False)  ->  Merge cells (combine=True joins their text).
- sheet.unmerge(range)  ->  Split any merged cells inside a region.
- sheet.style(range, bold=, italic=, underline=, color=, fill=, align=, valign=, wrap=, border=, border_style=, border_color=, font=, size=, number_format=)  ->  Format a range, changing only what you give. bold/italic/underline/wrap: True or False. color (text) / fill: hex '#206dc5'. align 'left'/'center'/'right', valign 'top'/'middle'/'bottom', font a font name, size in px, number_format a code or word ('0.0%', 'date', 'text'). border: True, False or a preset ('outside', 'bottom', 'thick_bottom', 'bottom_double', 'inside'); Excel's border menu over the range, in border_style ('thin', 'medium', 'thick', 'double', 'dashed', 'dotted'…) and border_color (hex). A value it cannot use raises.
- sheet.sort(range, by=[(column, direction), …])  ->  Sort the DATA rows of a range in place (not the header row), first key first. column: its offset in the range, its letter or its heading in the row above. direction: True/'asc' or False/'desc'. e.g. sheet.sort('A2:F9', by=[('Region', 'asc'), ('Total', 'desc')]) or by=(5, False).
- sheet.freeze(rows=0, cols=0)  ->  Freeze leading rows/columns (freeze(1) pins the header row; freeze(0,0) unfreezes).
- sheet.cond_format(range, kind, value=|min=|max=|text=|n=, fill=, color=)  ->  Conditional formatting. kind: 'greaterThan'/'lessThan'/'equalTo' (value=), 'between' (min=, max=), 'textContains' (text=), 'top'/'bottom' (n=), 'duplicates', 'colorScale' (lo=, hi=), 'dataBar' (bar=). A kind or value it cannot use raises.
Structure:
- sheet.insert_rows(at, count=1)  ->  Insert blank rows before row index `at`.
- sheet.delete_rows(at, count=1)  ->  Delete rows from index `at` (refs into them → #REF!).
- sheet.insert_cols(at, count=1)  ->  Insert blank columns before column index `at`.
- sheet.delete_cols(at, count=1)  ->  Delete columns from index `at`.
- sheet.set_col_width(col, px)  ->  Set a column width in pixels (clamped to a minimum — use hide_cols to hide).
- sheet.set_row_height(row, px)  ->  Set a row height in pixels (clamped to a minimum — use hide_rows to hide).
- sheet.hide_rows(at, count=1)  ->  Hide whole rows (0-indexed). This is the ONLY way to hide — width/height 0 is clamped.
- sheet.hide_cols(at, count=1)  ->  Hide whole columns (0-indexed).
- sheet.unhide_rows(at, count=1)  ->  Show hidden rows in the span [at, at+count).
- sheet.unhide_cols(at, count=1)  ->  Show hidden columns in the span [at, at+count).
Data tools:
- sheet.filter(range, column, op, value[, value2])  ->  Filter a table as Data > Filter does (hide the rows that fail). range = the DATA rows ('A2:F100'; the row above is the header; it runs to the last used row). column = its offset in the range, its letter ('C') or its heading ('Region'). op: '=' '!=' '>' '>=' '<' '<=' 'between' (value, value2) 'contains' 'notContains' 'startsWith' 'endsWith' 'empty' 'notEmpty' 'top' / 'bottom' (value = how many) 'aboveAvg' 'belowAvg'. A second call on ANOTHER column narrows the first; the header shows the filter and the user can clear it. Returns rows hidden.
- sheet.clear_filter([range])  ->  Take the sheet's filter off and show its rows (and any hidden rows in range).
- sheet.remove_duplicates(range)  ->  Drop duplicate rows in a range (keeps first). Returns count removed. The range is anything read() takes ('A2:G100', 'Data!A2:G100', 'A:G', a sheet's name).
- sheet.pivot(range, rows=['Region'], values=[('Q1','sum')], cols=None, filters=None, show_as='value', name=None)  ->  Build a DYNAMIC (re-editable) pivot into a NEW sheet. Fields are header NAMES or 0-based offsets of the range's columns (each with a heading). rows=a LIST of nested row fields (rows=['Region']); values=a list of fields or (field, agg) pairs (sum/count/average or mean/min/max; any other raises); cols=one column field; filters=(field, value) or (field, op, v1[, v2]); show_as 'value'/'pctOfTotal'; name= the new sheet's name (default 'Pivot of <source sheet>'). Returns the new sheet handle. Legacy sheet.pivot(range, row_field, value_field, agg, col_field) still works.
- pivot_sheet.update_pivot(rows=, values=, cols=, filters=, show_as=)  ->  Reconfigure an existing pivot sheet in place (same args as pivot) and rebuild from its live source — Excel-style field edit.
- pivot_sheet.refresh_pivot()  ->  Recompute a pivot sheet from its (possibly changed) source, keeping the same configuration.
- sheet.validate(range, kind, op=, f1=, f2=, options=, error=)  ->  Data validation. kind 'list' (options=['A','B'], 'A,B,C', a range or a defined name), 'whole'/'decimal'/'date'/'textLength' (op '>=' '>' '<' '<=' '=' '!=' with f1=, or 'between'/'notBetween' with f1=, f2=), 'custom' (f1='=formula'). A rule it could not run raises.
- sheet.clear(range)  ->  Clear cell contents in a range (styling kept).
- sheet.clear_validation([range])  ->  Remove validation rules: all of the sheet's, or those inside a range. Returns how many. validate() on a range already replaces the rules inside it.
Spredin ops:
- sheet.clear_cond_formats([range])  ->  Remove conditional formats: all of the sheet's, or those inside a range. Returns how many. Call it before cond_format() in a script that is run again.
Cells:
- sheet.fill_down(range)  ->  Fill Down: copy the first row of a range to the rows below it. A formula's relative references move row by row ($ pins them), a value repeats, formats come along. e.g. sheet.set_cell('E2', '=C2*D2'); sheet.fill_down('E2:E%d' % sheet.rows).
Data tools:
- sheet.define_name(name, target)  ->  Define a workbook name: a range on this sheet ('B2:B13'), a value ('0.2') or a formula ('=Rate*2').
- sheet.defined_names()  ->  The workbook's defined names, a dict name -> definition.
- sheet.delete_name(name)  ->  Delete a defined name (any case); False if there is none.
- sheet.memory()  ->  The workbook's assistant memory (ASSISTANT.md, saved in the file): Markdown notes; '' when none.
- sheet.set_memory(text)  ->  Replace the workbook's assistant memory; to add a line: sheet.set_memory(sheet.memory() + '- note\n').
Slides (PRO):
- sheet.decks()  ->  Names of this workbook's slide decks.
- sheet.deck(name, create=False)  ->  A slide deck saved in the workbook; its tables, charts and numbers stay linked to the cells. See "Slides" below.
Import / export:
- sheet.to_csv([range], sep=',')  ->  A range as CSV text (computed values). Dates as the dates they show. The range is anything read() takes: none (used sheet), 'A1:C9', 'Sales!A1:C9', 'A:C', a sheet's name. A range it cannot read raises.
- sheet.to_json([range])  ->  A range as a JSON string (2D array of values). Dates as the dates they show, errors as their text. The same ranges as to_csv.
- sheet.paste_csv(text, at='A1', sep=',', as_text=False)  ->  Parse CSV/TSV text and write it in at a cell. Fields are read as File > Open reads a CSV: $1,200.50, 50%, (300) and dates become numbers and dates with their formats, 007 stays text. as_text=True writes every field as text.
Printing & PDF:
- sheet.page_setup(**changes)  ->  Read (no arguments) or change how the sheet prints; returns the whole setup as a dict. Settings: paper ('a4','a3','a5','letter','legal','tabloid'), orientation ('portrait'/'landscape'), margins ('normal'/'wide'/'narrow' or a dict of points, 72 = 1 inch), scale=percent OR fit=(pages wide, pages tall; 0 = no limit), print_area='A1:F40', title_rows='1:1', title_cols='A:A', gridlines, headings, center_h, center_v, page_order ('down_then_over'/'over_then_down'), header/footer (text, or a dict of left/center/right; &P page &N pages &A sheet &F file &D date &T time), row_breaks=[rows a new page starts at], col_breaks=['F']. None clears print_area/title_rows/title_cols. Saved with the workbook.
- sheet.page_count(area=None, workbook=False)  ->  How many pages a print would make — of the sheet, of just area='A1:F40', or with workbook=True of every visible sheet (each with its own setup).
- await sheet.export_pdf(path=None, area=None, pages=None, workbook=False)  ->  Save a PDF. path: a FULL path ('/Users/you/Documents/Q3.pdf'; Spredin asks the user to allow it) or None for the save panel. pages=(first, last) from 1. Returns the path written, or None if the user declined. Not a file in the workbook — never call it unless asked for a PDF.
- await sheet.print_out(area=None, pages=None, workbook=False)  ->  Print: opens the Mac's print panel over the pages for the user to confirm. True when printed, False when cancelled. Only when asked to print.
Sheets:
- sheet.add_sheet(name, replace=False)  ->  Create and return a new sheet handle. replace=True reuses an existing sheet of that name, EMPTIED: cells, formats, charts, merges, hidden rows, sizes, frozen panes, rules, filter and comments all go. Use it so re-running the script updates one sheet instead of piling up copies.
- sheet.delete_sheet('Old')  ->  Delete a sheet by name. False if it does not exist, or is the last sheet.
Charts:
- sheet.charts()  ->  List this sheet's charts as dicts {id, range, type, title}.
- sheet.clear_charts()  ->  Remove every chart from this sheet; returns how many. Charts are append-only, so call this before re-adding on a re-run.
- sheet.update_chart(which, **changes)  ->  Change a chart in place (which: its id or its place in charts()): type=, title=, range=, chart() options; None = default.
Sheets:
- sheet.copy([name], replace=False)  ->  A full copy of this sheet as a new sheet: formulas, formats, widths. Returns its handle. Formulas stay formulas and dates stay dates; number formats, bold and colours, merges, column widths, row heights, hidden rows, frozen panes, conditional formats, validation rules, comments and charts come with them. No name: '<sheet> (2)'. replace=True reuses an existing sheet of that name.
- sheet.copy_to(dest[, range], at='A1', values=False)  ->  Copy a range (default: all) onto another sheet as copy and paste does. dest: a sheet handle or name. Cells arrive as written with their formats and merges; a formula stays a formula, its relative references moved by the distance pasted. values=True copies what formulas show instead (Paste Values).
- sheet.book(name)  ->  Get an existing sheet by name, in any case (book("sales") finds Sales). A name that is no sheet raises and lists the sheets.
- sheet.names()  ->  List all sheet names.
- sheet.name  ->  This sheet's name.

Cross-sheet (combine multiple sheets):
- Every handle from sheet.book(name) / sheet.add_sheet(name) supports the SAME methods
  (read/write/value/set/chart/style/…), each acting on ITS own sheet.
- Example — join two sheets and write the result to a third:
    import pandas as pd
    a = sheet.book('Sales').read()
    b = sheet.book('Targets').read()
    merged = a.merge(b, on='Region')
    out = sheet.add_sheet('Combined'); out.write(merged)
- Formulas can also reference other sheets directly, e.g. sheet.set('B2', "=Sales!B2-Targets!B2").
Other workbooks on disk (read-only, no window) — NOTE the await:
    wb = await open_file('/path/jan.xlsx')   # .sprd .xlsx .xls .csv .tsv
    wb.sheets; wb.sheet('Summary').cell('B12'); wb.sheet('Raw').read(); wb.close()
  The user is asked (shown the path) before a file they did not open themselves is read; a refusal raises.

Slides (Spredin Pro) — decks saved in this workbook, LINKED to its cells (slides and blocks numbered from 1):
    d = sheet.deck('Q3 pack', create=True)      # d.name
    d.add_slide('Q3 review', subtitle='Board, October')     # returns the slide number
    d.add_slide('By region', table='Sales!A1:E9', notes='West dipped')   # range, defined name, table or sheet (a pivot sheet)
    d.add_slide('Headlines', kpis=[('Revenue', 'Summary!B7', 'Summary!C7')])   # (label, cell or '=AVERAGE(…)'[, compare cell])
    d.add_slide('Trend', blocks=[{'chart': {'source': 'Sales!A1:C13', 'type': 'line'}}, {'table': 'Totals'}])
    d.add_block(3, text='- Margin {{=Summary!B9|0.0%}}'); d.update_block(3, 1, chart={'id': chart_id})
    d.move_block(3, 2, to=1); d.copy_block(3, 1, to_slide=5); d.delete_block(3, 2)
    d.paste_block(5, other.slides()[0]['blocks'][1])   # a block as slides() shows one, from this deck or another (picture= for another deck's picture)
    d.add_image(4, '<svg viewBox="0 0 400 200">…</svg>', alt='Pipeline')   # SVG you write (no script/links), or a PNG/JPEG/GIF/WebP file's bytes
    d.add_shape(4, 'arrow', text='Next', direction='down')   # rect ellipse triangle diamond polygon star arrow doubleArrow chevron pentagon callout ring arc plus line…
        # settings by shape (corner rounds any shape's corners, sides, points, head, shaft, tail_x/tail_y, thickness, start/sweep, ends, caps…); any: rotation, flip_h, flip_v, opacity
    d.add_math(4, r'R = \frac{v_0^2 \sin 2\theta}{g} \approx {{=Inputs!B5|0.0}}\,\mathrm{m}')   # TeX, typeset; a list: several equations; $...$ in any text is typeset too
    d.add_anim(5, 'trace', y='Sim!B1:C200', equal=True)   # plays from cells: trace (x,y columns), curve (x + a column per frame), bars (a row per frame); dur= once= labels= t=
    d.build_block(5, 2, 1)   # block 2 appears on the first click while presenting (0: with the slide); or build=1 beside a block
    d.add_control(5, 'Inputs!B3', 'slider', min=0, max=90)   # sets the cell while presenting; slider|stepper|list; range/choices default to the cell's validation
    d.add_code(6, script='fit.py', lines='5-14')   # a workbook script's lines, live and coloured; or text='…'
    d.update_slide(2, title='Revenue by region', arrange='rows'); d.move_slide(4, 2); d.duplicate_slide(2); d.delete_slide(5)
    d.place_block(3, 2, x=700, y=170, w=500, h=320)   # by hand, slide px; body x 80-1200, y 160-650; arrange='auto' undoes
    d.size_block(3, 2, 28)   # text size, slide px 10-120 (body / table cells / chart labels / KPI number); 'auto' fits
    d.layer_block(3, 2, to='front', opacity=0.8)   # overlap: layer=int -100..100, higher in front (below 0: behind the title); to front|back|forward|backward; opacity 0.05-1
    d.style_block(3, 2, bold=True, align='center', valign='middle', fill='#f4efe6', border='#b5553a', color='#171c26', font='Avenir Next')
        # the grid's format bar for a block; None/False removes one; reset=True; a table's border draws every cell edge
    d.style_title(3, align='center', color='#1f4e79', size=48)   # the slide title's own format: italic, underline, align, color, font, size 20-96|'auto'
    d.set_style(bg='#0f1b33', text='#f1f3f8', accent='#e5604f', heading_font='Avenir Next'); d.set_style(reset=True)
    d.set_style(palette='shuffle-dark'); d.save_theme('Board navy')   # palette by name, or shuffle / shuffle-light / shuffle-dark
    await d.export_pdf(); await d.export_html('/Users/you/Desktop/q3.html'); d.present(2)   # no path: the save panel
    d.slides(); d.info(); d.set_theme('dusk'); d.freeze(); d.unfreeze(); d.rename('Board pack'); d.delete()   # info: theme, size, style, frozen
    d.set_ink(3, [{'tool': 'pen', 'color': '#be3427', 'w': 4, 'pts': [100, 600, 400, 610]}]); d.ink(3); d.clear_ink(3)   # handwriting, slide px
    d.set_size('a4')   # wide (16:9, default) standard (4:3) wide1610 a4 letter a4Landscape letterLandscape square vertical, '1080x1350', or w=, h=
  A slide holds up to 12 blocks: text, a table, a chart (a range, or {'id': ...} of a sheet chart), KPI tiles, a picture, a shape, an equation, an animation or a control. One block
  is centred; several sit side by side with their edges aligned (arrange='columns' or 'rows'), or each where place_block
  puts it (arrange='free'; blocks not placed keep the grid's spot). update_slide(text=…)
  replaces a one-block slide's content; on several blocks use update_block.
  Text may hold live values: {{Revenue}} or {{=Sales!F12/Sales!F11|0.0%}} — shown exactly as the grid shows them; never type a number.
  Fonts: macOS names (Avenir Next, Charter, Futura, Georgia, Gill Sans, Helvetica Neue, Optima, Palatino, Menlo…).
  A deck holds no HTML. export_pdf / export_html write only where the user chooses (the save panel) or allows (a full path).
```

## Number formats

```text
Number formats (`sheet.style(range, number_format=…)`, and the numFmt of a cell):
- 'general'   — default; plain number.
- Dates are serial numbers (days since 1899-12-30); a date format changes how the
  serial is SHOWN. Excel picture codes work: 'yyyy-mm-dd', 'mm/dd/yyyy',
  'dd-mmm-yy', 'mmm yyyy', 'hh:mm', 'yyyy-mm-dd hh:mm'. The keywords 'date',
  'time' and 'datetime' are short forms (2024-01-15, 14:30:00, both).
- Numeric picture codes work Excel-style: '0', '0.00', '#,##0', '#,##0.00',
  '$#,##0', '$#,##0.00', '0%', '0.00%', '0.00E+00'.
  · a leading symbol is the currency: '$', '€', '£'
  · ',' = thousands separators, '.00' = fixed decimals, '%' scales by 100
  · ';' splits positive;negative;zero — '$#,##0;[Red]($#,##0)' shows red parens
    for negatives
- The words 'number', 'percent', 'currency', 'integer', 'accounting',
  'scientific' and 'text' are taken as the toolbar's codes; anything else that is
  no format raises an error naming what to give.
- Formatting NEVER changes the stored value, only its display.
- DATES FROM A SCRIPT: write datetime.date / datetime.datetime objects, pandas
  Timestamps, numpy datetime64 or ISO text like '2024-01-15' — the cell becomes a
  real date (a serial with the 'date' format), no serial arithmetic needed. A
  locale form like '1/2/2024' stays text. Reading a date cell back gives its
  serial; pd.to_datetime(serial, unit='D', origin='1899-12-30') is the way back.
```
