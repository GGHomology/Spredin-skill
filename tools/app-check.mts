// Check sprd.py against Spredin Pro's own reader and writer.
//
//   cd <spredin-pro checkout>
//   node_modules/.bin/vite-node <this repo>/tools/app-check.mts
//
// 1. Fixtures: a small workbook written by the APP in each form it writes
//    (compact, dual, full; and a plain uncompressed one with a byte-order
//    mark), with tests/fixtures/expected.json holding every cell as the app
//    reads it back. tests/test_sprd.py checks sprd.py reads the same cells.
// 2. The writer: runs `sprd.py write` on tests/fixtures/spec.json and reads the
//    result with the APP's reader: every cell, number format, bold, column
//    width, freeze and name must come back as the spec says, with nothing
//    left out. Exits 1 on any difference.
import { execFileSync } from 'node:child_process';
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { gunzipSync, gzipSync } from 'node:zlib';

const SRC = process.env.SPREDIN_SRC ?? process.cwd();
const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = join(HERE, '..');
const FIX = join(ROOT, 'tests', 'fixtures');
const SPRD = join(ROOT, 'skills', 'spredin-pro', 'scripts', 'sprd.py');

const wb = await import(join(SRC, 'src/grid/workbook.ts'));
const coords = await import(join(SRC, 'src/grid/coords.ts'));
const numparse = await import(join(SRC, 'src/grid/numparse.ts'));
type Sheet = ReturnType<typeof wb.makeSheet>;

const label = (r: number, c: number) => coords.cellLabel(r, c) as string;

function cellsOf(s: Sheet): Record<string, string> {
  const out: [number, number, string][] = [];
  for (const [r, c] of s.store.cells()) out.push([r, c, s.store.getRaw(r, c)]);
  out.sort((a, b) => a[0] - b[0] || a[1] - b[1]);
  return Object.fromEntries(out.map(([r, c, v]) => [label(r, c), v]));
}

function read(text: string) {
  const got = wb.parseSpredinText(text);
  if (got.notes.leftOut.length) throw new Error(`the app left parts out: ${JSON.stringify(got.notes.leftOut)}`);
  return got;
}

// --- 1. fixtures from the app's writer ---------------------------------------

function book(): Sheet[] {
  const sales = wb.makeSheet('Sales');
  const put = (s: Sheet, a1: string, raw: string) => {
    const p = coords.parseA1(a1);
    s.store.set(p.r, p.c, raw);
  };
  [['A1', 'Region'], ['B1', 'Q1'], ['C1', 'Q2'], ['D1', 'Total'], ['E1', 'Label'], ['F1', '1']].forEach(([a, v]) => put(sales, a, v));
  const regions = ['East', 'West', 'North', 'South'];
  regions.forEach((name, i) => {
    const r = i + 2;
    put(sales, `A${r}`, name);
    put(sales, `B${r}`, String(1200 + i * 75));
    put(sales, `C${r}`, String(1350.5 - i * 20.25));
    put(sales, `D${r}`, `=B${r}+C${r}`);
    put(sales, `E${r}`, `="{"&A${r}&"}"`);
    put(sales, `G${r}`, `=B${r}*2`);
    put(sales, `H${r}`, `=C${r}*2`);
  });
  for (let r = 2; r <= 12; r++) put(sales, `F${r}`, `=F${r - 1}+1`);
  put(sales, 'A7', 'Total');
  put(sales, 'B7', '=SUM(B2:B5)');
  put(sales, 'C7', '=SUM(C2:C5)');
  put(sales, 'A9', '007');
  put(sales, 'B9', "'1200");
  put(sales, 'C9', '46341');
  put(sales, 'D9', 'TRUE');
  put(sales, 'E9', '12345678901234567890');
  for (let c = 0; c < 5; c++) sales.styles.set(0, c, { bold: true });
  sales.styles.set(8, 2, { numFmt: 'yyyy-mm-dd' });
  const notes = wb.makeSheet('Notes, 2026');
  put(notes, 'A1', 'He said "hi", then\nleft');
  put(notes, 'B1', 'a,b');
  put(notes, 'A3', "='Sales'!D5*2");
  put(notes, 'A4', '=LEN(A1)');
  return [sales, notes];
}

const names = { Rate: 'Sales!$B$2' };
const expected: Record<string, { sheets: Record<string, Record<string, string>>; names: Record<string, string> }> = {};
const texts: Record<string, string> = {};
for (const form of ['compact', 'dual', 'full'] as const) {
  texts[form] = wb.toSpredinText(book(), 0, [], names, [], [], { form });
}
texts['plain-bom'] = '\uFEFF' + texts.full;
for (const [form, text] of Object.entries(texts)) {
  const file = `${form}.sprd`;
  writeFileSync(join(FIX, file), form === 'plain-bom' ? text : gzipSync(Buffer.from(text, 'utf8')));
  const got = read(text);
  expected[file] = {
    sheets: Object.fromEntries(got.sheets.map((s: Sheet) => [s.name, cellsOf(s)])),
    names: got.names,
  };
}
// The forms must differ where they should, or the fixtures test nothing.
if (!texts.compact.includes('"compactSheets"') || !texts.compact.includes('{row')) throw new Error('compact fixture has no fill lines');
if (!texts.dual.includes('"fills"')) throw new Error('dual fixture has no fill lines');
if (texts.full.includes('"fills"')) throw new Error('full fixture has fill lines');
writeFileSync(join(FIX, 'expected.json'), JSON.stringify(expected, null, 1) + '\n');
console.log(`fixtures: ${Object.keys(texts).length} files written by the app`);

// --- 2. sprd.py write, read by the app ---------------------------------------

const spec = JSON.parse(readFileSync(join(FIX, 'spec.json'), 'utf8'));
const dir = mkdtempSync(join(tmpdir(), 'sprd-check-'));
let bad = 0;
const fail = (msg: string) => {
  bad++;
  console.log(`DIFFERS: ${msg}`);
};
try {
  const out = join(dir, 'out.sprd');
  execFileSync('python3', ['-I', SPRD, 'write', join(FIX, 'spec.json'), out], { stdio: 'pipe' });
  const got = read(gunzipSync(readFileSync(out)).toString('utf8'));
  spec.sheets.forEach((ss: Record<string, unknown>, i: number) => {
    const s: Sheet = got.sheets[i];
    if (!s || s.name !== ss.name) return fail(`sheet ${i + 1} is ${s?.name}, the spec says ${ss.name}`);
    const want: Record<string, string> = {};
    const at = coords.parseA1((ss.at as string) ?? 'A1');
    // A number is written as the app writes one (numparse.ts numberText), and read back as that number.
    const text = (v: unknown) =>
      v === null ? '' : typeof v === 'boolean' ? (v ? 'TRUE' : 'FALSE') : typeof v === 'number' ? (numparse.numberText(v) as string) : String(v);
    const numbers = new Map<string, number>();
    ((ss.rows as unknown[][]) ?? []).forEach((row, dr) =>
      row.forEach((v, dc) => {
        if (text(v) !== '') want[label(at.r + dr, at.c + dc)] = text(v);
        if (typeof v === 'number') numbers.set(label(at.r + dr, at.c + dc), v);
      }),
    );
    for (const [a, v] of Object.entries((ss.cells as Record<string, unknown>) ?? {})) {
      want[a] = text(v);
      if (typeof v === 'number') numbers.set(a, v);
    }
    const have = cellsOf(s);
    for (const k of new Set([...Object.keys(want), ...Object.keys(have)]))
      if (want[k] !== have[k]) fail(`${ss.name}!${k}: app reads ${JSON.stringify(have[k])}, spec ${JSON.stringify(want[k])}`);
    for (const [k, v] of numbers)
      if (numparse.rawNumericValue(have[k] ?? '') !== v) fail(`${ss.name}!${k}: app reads ${JSON.stringify(have[k])} as ${numparse.rawNumericValue(have[k] ?? '')}, not the number ${v}`);
    for (const [rng, fmt] of Object.entries((ss.formats as Record<string, unknown>) ?? {})) {
      const r = coords.parseRangeLabel(rng);
      const style = typeof fmt === 'string' ? { numFmt: fmt } : (fmt as Record<string, unknown>);
      for (let rr = r.r0; rr <= r.r1; rr++)
        for (let cc = r.c0; cc <= r.c1; cc++)
          for (const [k, v] of Object.entries(style)) {
            const has = (s.styles.get(rr, cc) as Record<string, unknown> | undefined)?.[k];
            if (has !== v) fail(`${ss.name}!${label(rr, cc)} ${k}: app reads ${JSON.stringify(has)}, spec ${JSON.stringify(v)}`);
          }
    }
    for (const [col, w] of Object.entries((ss.widths as Record<string, number>) ?? {})) {
      const c = coords.colIndex(col);
      const has = s.cols.get(c);
      if (has !== w) fail(`${ss.name} column ${col} width: app ${has}, spec ${w}`);
    }
    const fz = ss.freeze as { rows?: number; cols?: number } | undefined;
    if (fz && (s.freeze.rows !== (fz.rows ?? 0) || s.freeze.cols !== (fz.cols ?? 0)))
      fail(`${ss.name} freeze: app ${JSON.stringify(s.freeze)}, spec ${JSON.stringify(fz)}`);
  });
  for (const [k, v] of Object.entries((spec.names as Record<string, string>) ?? {}))
    if (got.names[k] !== v) fail(`name ${k}: app ${got.names[k]}, spec ${v}`);
} finally {
  rmSync(dir, { recursive: true, force: true });
}
console.log(bad ? `sprd.py write: ${bad} difference(s)` : 'sprd.py write: the app reads every cell, format, width, freeze and name as written');
if (bad) process.exit(1);

// --- 3. reading rules, as the app reads them ---------------------------------
//
// tests/fixtures/rules.json: small hand-made workbooks and what the APP reads
// from them, for tests/test_sprd.py to hold sprd.py to.

const rules: Record<string, unknown> = {};

// A file in the dual form (`sheets` with fill lines beside the rows): the rows
// hold every cell, and a fill line never adds one. A compact file for contrast.
const dualDocs: Record<string, unknown>[] = [
  { spredin: 1, active: 0, sheets: [{ name: 'S', rows: { '0': '1', '1': '=A1+1' }, fills: ['A2:A3 =A{row-1}+1'] }] },
  { spredin: 1, active: 0, sheets: [{ name: 'S', rows: { '0': '1', '1': '=A1+1', '2': 'changed' }, fills: ['A2:A3 =A{row-1}+1'] }] },
  { spredin: 2, active: 0, sheets: [{ name: 'S', rows: { '0': 'x' }, fills: ['B1:B3 =A{row}'] }] },
  { spredin: 2, active: 0, sheets: [{ name: 'Update Spredin' }], compactSheets: [{ name: 'S', rows: { '0': '1' }, fills: ['A2:A3 =A{row-1}+1'] }] },
];
rules.dual = dualDocs.map((doc) => {
  const got = wb.parseSpredinText(JSON.stringify(doc));
  return { doc, form: got.form, cells: cellsOf(got.sheets[0]) };
});

// Fill lines in a compact file: which the app keeps (a template must be what
// its writer would write), and the cells it gives. Each case is one sheet.
// The cases that need defined names come last: the app remembers every name
// it was told (editops.ts noteDefinedNames), so they must not reach the others.
const sc = await import(join(SRC, 'src/grid/sprdCompact.ts'));
const ed = await import(join(SRC, 'src/grid/editops.ts'));
const RATD = coords.colIndex('RATD') as number;
const fillCases: Record<string, string[]> = {
  quoted: ['A1:A3 ="Row {row}"'],
  absolute: ['A2:A4 =$B${row}'],
  oneColumn: ['B2:B4 ={col}1*2'],
  notFormula: ['A1:A3 x{row}'],
  written: ['A1:A3 =B5'],
  unknown: ['A1:A3 =A{rows}'],
  leftOfA: ['A1:A3 ={col-1}{row}'],
  lowercase: ['A1:A3 =b{row}+$c$01'],
  block: ['B2:D4 ={col-1}{row}*2'],
  wholeColumns: ['B1:C3 =SUM({col}:{col})+ROWS($1:{row})'],
  colsReversed: ['A1:B3 =SUM({col+1}:$B)'],
  rowsReversed: ['A2:A4 =ROWS({row+1}:$3)'],
  braces: ['A1:A2 ="{{"&A{row}&"}}"'],
  curly: ['A1:A3 =\u201cx{row}\u201d'],
  curlyCloses: ['A1:A3 ="x\u201c&B{row}'],
  sheetLikeCell: ['A1:A3 =Q1!B{row}'],
  quotedSheet: ["A1:A3 ='Q1 2025'!B{row}"],
  quoteInSheet: ["A1:A3 ='Bob''s'!B{row}"],
  functionName: ['A1:A3 =LOG10(B{row})+DEC2BIN(C{row})'],
  table: ['A1:A3 =SUM(T[Q1])+B{row}'],
  linked: ['A1:A3 =[1]Sheet1!B{row}'],
  sheetRun: ['A1:A3 =SUM(Jan:Dec!B{row})'],
  zeros: ['A1:A3 =A{row+007}*2'],
  minusZero: ['A1:A3 =B{row-0}'],
  bigOffset: ['A1:A3 =A{row+1000000000000000}'],
  overlap: ['A1:A3 =B{row}', 'A2:A5 =C{row}', 'C1:C2 =D{row}'],
  mixed: ['B2:C3 =$A{row}+{col}$1'],
  pastZZZZ: ['A1:B2 ={col+475253}{row}'],
  wideSheet: ['A1:A3 =\u6570\u636e!B{row}'],
  wideWord: ['A1:A3 =\u00c4B{row}'],
  dollarRange: ['$A$1:$A$3 =B{row}'],
  lowerRange: ['a1:a3 =B{row}'],
  zeroRow: ['A01:A3 =B{row}'],
  threeParts: ['A1:A3:Z9 =B{row}'],
  spaces: ['A1:A3   =B{row}'],
  tab: ['A1:A3\t=B{row}'],
  leadingSpace: [' A1:A3 =B{row}'],
  rowZero: ['A1:A3 =$A$0+B{row}'],
  pastRows: ['A16777215:A16777217 =1', 'B1:B2 =2'],
};
const nameCases: Record<string, string[]> = {
  farName: ['A1:A3 =Rate1*B{row}'],
  farRange: ['A1:A3 =Rate1:A{row}'],
  farMovedOnto: [`A1:B2 ={col+${RATD}}{row}*2`],
  scopedName: ['A1:A2 =YTD2024+B{row}'],
};
const names3 = { Rate1: 'S!$Z$1', 'Data!YTD2024': 'S!$Z$2' };
function readCases(cases: Record<string, string[]>, names?: Record<string, string>) {
  const out: Record<string, unknown>[] = [];
  for (const [name, fills] of Object.entries(cases)) {
    let leftOut = 0;
    sc.readFillLines(fills, () => leftOut++);
    const rows = name === 'overlap' ? { '1': 'kept' } : undefined;
    const doc = { spredin: 2, active: 0, sheets: [{ name: 'Update Spredin' }], compactSheets: [{ name, fills, ...(rows ? { rows } : {}) }], ...(names ? { names } : {}) };
    const got = wb.parseSpredinText(JSON.stringify(doc));
    out.push({ name, fills, ...(rows ? { rows } : {}), ...(names ? { names } : {}), leftOut, cells: cellsOf(got.sheets[0]) });
  }
  return out;
}
rules.fills = readCases(fillCases);
ed.noteDefinedNames(Object.keys(names3).map((k) => k.slice(k.lastIndexOf('!') + 1)));
rules.fills = [...(rules.fills as unknown[]), ...readCases(nameCases, names3)];
// What each case shows, so a wrong expectation is caught here, not believed.
const fillsRead = Object.fromEntries((rules.fills as { name: string; cells: Record<string, string> }[]).map((c) => [c.name, c.cells]));
const must: [string, string, string | undefined][] = [
  ['quoted', 'A1', undefined], ['absolute', 'A2', undefined], ['oneColumn', 'B2', undefined], ['written', 'A1', undefined],
  ['lowercase', 'A1', '=b1+$c$01'], ['lowercase', 'A2', '=B2+$C$1'], ['colsReversed', 'B1', '=SUM($B:C)'],
  ['rowsReversed', 'A4', '=ROWS($3:5)'], ['curly', 'A1', undefined], ['curlyCloses', 'A2', '="x\u201c&B2'],
  ['pastZZZZ', 'B2', '=AAAAA1'], ['rowZero', 'A2', '=#REF!+B2'], ['farName', 'A2', '=Rate1*B2'],
  ['farMovedOnto', 'B2', '=RATE1*2'], ['farRange', 'A1', undefined], ['wideWord', 'A1', undefined],
];
for (const [c, at, want] of must)
  if (fillsRead[c]?.[at] !== want) throw new Error(`rules: ${c}!${at} is ${JSON.stringify(fillsRead[c]?.[at])}, expected ${JSON.stringify(want)}`);

// The four bounds on a sheet's fill lines, at small sizes: which lines the
// app keeps, and the first formula of each column it keeps.
const limitCases: { why: string; limits: Record<string, number>; lines: string[] }[] = [
  { why: 'cells', limits: { cells: 5, columns: 100, text: 1e9, moves: 100 }, lines: ['A1:A3 =B{row}', 'B1:B3 =C{row}', 'C1:C2 =D{row}'] },
  { why: 'a line the template check refuses names no columns', limits: { cells: 1000, columns: 2, text: 1e9, moves: 100 }, lines: ['A1:A1 =1', 'B1:B1 x', 'C1:C1 =3'] },
  { why: 'a line refused for covering a cell names its columns', limits: { cells: 1000, columns: 3, text: 1e9, moves: 100 }, lines: ['A1:A1 =1', 'A1:A1 =2', 'B1:B1 =3', 'C1:C1 =4'] },
  { why: 'text', limits: { cells: 1000, columns: 100, text: 20, moves: 100 }, lines: ['A1:A2 =B{row}', 'B1:B1 =12345', 'C1:C1 =1'] },
  { why: 'text in UTF-16 units', limits: { cells: 1000, columns: 100, text: 4, moves: 100 }, lines: ['A1:A1 ="\u{1F600}"', 'B1:B1 ="a"'] },
  { why: 'moves', limits: { cells: 1000, columns: 100, text: 1e9, moves: 1 }, lines: ['A5:A5 =1', 'A3:A3 =2', 'A1:A1 =3', 'A9:A9 =4'] },
  { why: 'a block', limits: { cells: 1000, columns: 3, text: 1e9, moves: 100 }, lines: ['B2:C3 ={col-1}{row}', 'D1:E1 =1', 'D2:D2 =2'] },
];
rules.limits = limitCases.map((lc) => {
  let leftOut = 0;
  const kept = sc.readFillLines(lc.lines, () => leftOut++, lc.limits).map((f: { c: number; r0: number; r1: number; master: string }) => [f.c, f.r0, f.r1, f.master]);
  return { ...lc, leftOut, kept };
});

// Numbers in a spec, written as the app writes a number in a cell. As JSON
// text, so both languages read the same double.
let seed = 20261116;
const rnd = () => ((seed = (Math.imul(seed, 1103515245) + 12345) >>> 0) / 2 ** 32);
const numberTexts = [
  '0', '-0', '-0.0', '1', '1.0', '1200', '412.35', '0.1', '0.30000000000000004', '1e-7', '0.000001', '1e-6', '123456.789',
  '999999999999999', '1000000000000000', '1234567890123456', '9007199254740993', '12345678901234567890',
  '99999999999999999999', '1e21', '1.5e300', '-1234567890123456', '-12345678901234567890', '1E5', '5e-324', '1.7976931348623157e308',
];
for (let e = -30; e <= 30; e++) for (let i = 0; i < 4; i++) numberTexts.push(String((rnd() * 10 + 1) * 10 ** e * (rnd() < 0.2 ? -1 : 1)));
for (let d = 15; d <= 25; d++) for (let i = 0; i < 3; i++) numberTexts.push(String(1 + Math.floor(rnd() * 9)) + Array.from({ length: d - 1 }, () => Math.floor(rnd() * 10)).join(''));
rules.numbers = numberTexts.map((t) => [t, numparse.numberText(JSON.parse(t)) as string]);

// A file from a newer version of Spredin is refused, with nothing read.
rules.versions = ['3', '999', '3.0', '1e2', '1000', '2.5', '"3"', 'true', '2', '1', '-3'].map((v) => {
  const text = `{"spredin": ${v}, "active": 0, "sheets": [{"name": "S"}]}`;
  try {
    wb.parseSpredinText(text);
    return { text, newer: false };
  } catch (e) {
    if ((e as Error).message !== wb.NEWER_FILE) throw e;
    return { text, newer: true };
  }
});

writeFileSync(join(FIX, 'rules.json'), JSON.stringify(rules, null, 1) + '\n');
console.log(
  `rules: ${(rules.dual as unknown[]).length} dual-form files, ${(rules.fills as unknown[]).length} fill-line sheets, ` +
    `${(rules.limits as unknown[]).length} limit cases, ${(rules.versions as unknown[]).length} version numbers ` +
    `and ${(rules.numbers as unknown[]).length} numbers read or written by the app`,
);
