# Examples

Each example says which way in it uses. Keys are the Mac's.

## 1. What is in a workbook (files)

```text
python3 scripts/sprd.py info ~/Documents/Budget.sprd
python3 scripts/sprd.py read ~/Documents/Budget.sprd --sheet Budget --range A1:F20
```

`read` prints `A1<TAB>content` lines; a formula is its `=...` text. For an
`.xlsx`, read it with a library (openpyxl) or open it in Spredin.

## 2. A new workbook from data (files)

Write the spec (files.md shows every field), make the file, open it:

```text
python3 scripts/sprd.py write spec.json ~/Documents/Trip.sprd
open -a "Spredin Pro" ~/Documents/Trip.sprd
```

Then check it on screen: select the totals and read the status bar, or read a
formula from the formula bar.

## 3. A computed column in the open workbook (Python panel)

```python
# Sales has Region in A, Units in C, Price in D, a header in row 1.
last = sheet.rows                       # rows used, header included
sheet.set_cell('E1', 'Revenue')
sheet.set_cell('E2', '=C2*D2')          # a live formula
sheet.fill_down('E2:E%d' % last)        # E3 =C3*D3, ...
sheet.style('E2:E%d' % last, number_format='#,##0.00')
print('filled E2:E%d' % last)
```

Formulas stay live: change a price and the revenue follows.

## 4. A summary sheet, a pivot and a chart (Python panel)

```python
import pandas as pd
df = sheet.read()                                   # header row -> column names
summary = df.groupby('Region', as_index=False)['Revenue'].sum()
out = sheet.add_sheet('Summary', replace=True)      # re-running updates one sheet
out.write(summary, 'A1')
out.chart('A1:B%d' % (len(summary) + 1), 'bar', 'Revenue by region')
sheet.pivot(sheet.used_range, rows=['Region'], values=[('Revenue', 'sum')], name='Pivot')
# Run again, this last line adds a second pivot, "Pivot (2)". To change the
# pivot later: sheet.book('Pivot').update_pivot(rows=['Region'], values=[...]).
```

A pivot made this way can be edited from its sheet like one made from the menu.

## 5. Clean a column (Python panel)

For plain data. This writes the whole table back as values, so a formula in it
becomes its value:

```python
import pandas as pd
df = sheet.read()
df['Email'] = df['Email'].str.strip().str.lower()
df = df.drop_duplicates('Email')
sheet.write(df, 'A1', replace=True)     # replace=True clears the old, longer table
```

For a table with formulas, write only the Email column, then remove the rows
that are the same in every column (formulas stay live and follow their rows):

```python
df = sheet.read()                                   # the header is row 1
col = list(df.columns).index('Email')
sheet.write_col(col, df['Email'].str.strip().str.lower().tolist(), start_row=1)
last = sheet.a1(sheet.rows - 1, sheet.cols - 1)     # the table's bottom-right cell
print(sheet.remove_duplicates('A2:' + last), 'rows removed')
```

## 6. A total on screen (computer use)

1. Click the name box, type `B41`, Return.
2. Type `=SUM(B2:B40)` and press Return.
3. Click the name box, type `B41`, Return; read the formula bar to check it.

Or select `B2:B40` and press ⇧⌘T (AutoSum) to put the total under the column.

## 7. Run a menu command (computer use)

Press ⌘K, type `freeze top row`, press Return. Any command works this way:
`paste values`, `remove duplicate`, `new sheet`, `export workbook as excel`.

## 8. Many values off the screen (Python panel)

```python
for row in sheet.read_values('A1:F12'):
    print(row)
```

Run it, then read the Output pane: exact values, no screenshot reading.

## 9. Slides linked to cells (Pro, Python panel)

```python
d = sheet.deck('Monthly review', create=True)
d.add_slide('Monthly review', subtitle='November')
d.add_slide('By region', table='Summary!A1:B6')
d.add_slide('Headline', kpis=[('Revenue', 'Summary!B7')])
d.add_block(3, text='Revenue is {{=Summary!B7|#,##0}} this month')
print(d.slides())
```

Numbers on slides are links (`{{=...}}`), never typed, so they follow the cells.

## 10. Another workbook on disk (Python panel)

```python
wb = await open_file('/Users/you/Documents/January.xlsx')   # the user is asked first
jan = wb.sheet('Summary').read()
wb.close()
```
