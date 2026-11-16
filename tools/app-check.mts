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
texts['plain-bom'] = '﻿' + texts.full;
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
    const text = (v: unknown) => (v === null ? '' : typeof v === 'boolean' ? (v ? 'TRUE' : 'FALSE') : String(v));
    ((ss.rows as unknown[][]) ?? []).forEach((row, dr) =>
      row.forEach((v, dc) => {
        if (text(v) !== '') want[label(at.r + dr, at.c + dc)] = text(v);
      }),
    );
    for (const [a, v] of Object.entries((ss.cells as Record<string, unknown>) ?? {})) want[a] = text(v);
    const have = cellsOf(s);
    for (const k of new Set([...Object.keys(want), ...Object.keys(have)]))
      if (want[k] !== have[k]) fail(`${ss.name}!${k}: app reads ${JSON.stringify(have[k])}, spec ${JSON.stringify(want[k])}`);
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
