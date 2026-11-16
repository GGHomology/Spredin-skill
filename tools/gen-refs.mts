// Regenerate the skill's generated references from a Spredin Pro source
// checkout, so they always match the app they describe.
//
//   cd <spredin-pro checkout>
//   node_modules/.bin/vite-node <this repo>/tools/gen-refs.mts
//
// Writes, in skills/spredin-pro/references/:
//   python-api.md  the scripting API, from src/script/api.ts (the list the
//                  app's own tests hold against the Python runtime)
//   functions.md   every formula function, from src/grid/functionGuide.ts
//   menus.md       the window's menus, from App.tsx and the English strings
// and VERSION's `app` line.
//
// `--check` writes nothing and exits 1 when a file would change (for tests).
import { readFileSync, writeFileSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const SRC = process.env.SPREDIN_SRC ?? process.cwd();
const HERE = dirname(fileURLToPath(import.meta.url));
const SKILL = join(HERE, '..', 'skills', 'spredin-pro');
const REFS = join(SKILL, 'references');
const CHECK = process.argv.includes('--check');

const version: string = JSON.parse(readFileSync(join(SRC, 'src-tauri/tauri.conf.json'), 'utf8')).version;
const stamp = (what: string) =>
  `<!-- Generated from Spredin Pro ${version} (${what}) by tools/gen-refs.mts. Do not edit by hand. -->\n`;

const api = await import(join(SRC, 'src/script/api.ts'));
const prompt = await import(join(SRC, 'src/script/promptDocs.ts'));
const guide = await import(join(SRC, 'src/grid/functionGuide.ts'));
const formula = await import(join(SRC, 'src/grid/formula.ts'));

// --- python-api.md ----------------------------------------------------------

function pythonApi(): string {
  return (
    stamp('src/script/api.ts') +
    `# Python scripting API (Spredin Pro ${version})\n\n` +
    'Scripts run in the Python panel (Tools → Show Python Panel), inside the app, on the open\n' +
    'workbook. One run is one undo step. numpy, pandas and scipy are bundled; nothing is\n' +
    'downloaded. A script cannot read files on the computer by itself: `open_file()` asks the\n' +
    'user. The same reference is on https://spredin.com/docs/api.\n\n' +
    '```text\n' +
    api.SPREDIN_API +
    '\n```\n\n## Number formats\n\n```text\n' +
    prompt.FORMAT_CODES +
    '\n```\n'
  );
}

// --- functions.md -----------------------------------------------------------

const PART_TITLES = ['Maths', 'Logic and lookup', 'Statistics', 'Distributions', 'Text', 'Dates and times', 'More'];

function functions(): string {
  const sigOf = new Map<string, string>();
  for (const h of formula.FUNCTION_HELP as { name: string; sig: string }[]) sigOf.set(h.name, h.sig);
  const out: string[] = [
    stamp('src/grid/functionGuide.ts'),
    `# Formula functions (Spredin Pro ${version})\n`,
    'Search this file for a function name; do not read it whole. Each line: the signature, what',
    'it is for, and, when Spredin differs from Excel, how. In the app: Help → Formula Reference.\n',
    '## Rules for every function\n',
  ];
  for (const r of guide.GUIDE_RULES as { title: string; text: string }[]) out.push(`- **${r.title}.** ${r.text}`);
  let n = 0;
  (guide.GUIDE_PARTS as { name: string; line: string; excel: string }[][]).forEach((part, i) => {
    out.push(`\n## ${PART_TITLES[i] ?? 'More'}\n`);
    for (const e of [...part].sort((a, b) => a.name.localeCompare(b.name))) {
      n++;
      const diff = e.excel === 'same' ? '' : ` Excel: ${e.excel}`;
      out.push(`- \`${sigOf.get(e.name) ?? e.name}\` ${e.line}${diff}`);
    }
  });
  out.splice(2, 0, `${n} functions.\n`);
  return out.join('\n') + '\n';
}

// --- menus.md ---------------------------------------------------------------

/** The English dictionary: the first value of each key in i18n.ts (en comes first). */
function englishStrings(): Map<string, string> {
  const text = readFileSync(join(SRC, 'src/i18n.ts'), 'utf8');
  const map = new Map<string, string>();
  const re = /(['"])([\w.-]+)\1\s*:\s*(['"])((?:\\.|(?!\3)[^\\])*)\3/g;
  for (const m of text.matchAll(re)) {
    if (map.has(m[2])) continue;
    map.set(
      m[2],
      m[4]
        .replace(/\\u([0-9a-fA-F]{4})/g, (_x, h: string) => String.fromCharCode(parseInt(h, 16)))
        .replace(/\\(['"\\])/g, '$1')
        .replace(/\\n/g, ' '),
    );
  }
  return map;
}

interface Item {
  /** 0 for a menu itself, 1 for its items, 2 for a submenu's items. */
  level: number;
  label: string;
  hint?: string;
  desc?: string;
}

/** The menus block of App.tsx, read item by item: a label followed by
 *  `items:` is a menu, one inside `submenu: [` a submenu item. */
function menuItems(): Item[] {
  const app = readFileSync(join(SRC, 'src/App.tsx'), 'utf8');
  const start = app.indexOf('const menus: Menu[] = useMemo(() => [');
  if (start < 0) throw new Error('menus block not found in App.tsx');
  const en = englishStrings();
  const say = (k: string) => en.get(k) ?? k;
  const items: Item[] = [];
  let depth = 0;
  let pendingSub = false;
  const subs: number[] = []; // the depth inside each open submenu's bracket
  let i = app.indexOf('=> [', start) + 3;
  const begin = i;
  for (; i < app.length; i++) {
    const ch = app[i];
    if (ch === '/' && app[i + 1] === '/') {
      i = app.indexOf('\n', i);
      continue;
    }
    if (ch === "'" || ch === '"' || ch === '`') {
      const q = ch;
      for (i++; i < app.length && app[i] !== q; i++) if (app[i] === '\\') i++;
      continue;
    }
    if (ch === '[' || ch === '{' || ch === '(') {
      depth++;
      if (ch === '[' && pendingSub) {
        subs.push(depth);
        pendingSub = false;
      }
    } else if (ch === ']' || ch === '}' || ch === ')') {
      depth--;
      while (subs.length && depth < subs[subs.length - 1]) subs.pop();
      if (depth === 0 && i > begin) break;
    } else if (app.startsWith('submenu:', i)) {
      pendingSub = true;
    } else if (app.startsWith('label:', i)) {
      // The object's text from here to the next label (or its end).
      const next = app.indexOf('label:', i + 6);
      const seg = app.slice(i, next < 0 ? i + 400 : next);
      const labelExpr = seg.slice(6, seg.search(/,\s*(icon|hint|desc|run|items|submenu|separator|preview)\b|\n/));
      const keys = [...labelExpr.matchAll(/tr\('([\w.-]+)'\)/g)].map((m) => m[1]);
      if (!keys.length) continue;
      const hintTr = /hint:\s*tr\('([\w.-]+)'\)/.exec(seg);
      const hintLit = /hint:\s*'([^']*)'/.exec(seg);
      const descTr = /desc:\s*tr\(\s*(?:[\w.]+\s*\?\s*)?'([\w.-]+)'/.exec(seg);
      items.push({
        level: /\bitems:/.test(seg) ? 0 : 1 + subs.length,
        label: keys.map(say).join(' / '),
        hint: hintTr ? say(hintTr[1]) : hintLit?.[1],
        desc: descTr ? say(descTr[1]) : undefined,
      });
    }
  }
  return items;
}

function menus(): string {
  const items = menuItems();
  const out: string[] = [
    stamp('src/App.tsx menus, English strings'),
    `# Menus (Spredin Pro ${version})\n`,
    'The menu row inside the window, in English. On the Mac the menu bar at the top of the',
    'screen has the same menus. Every item is also in the command palette (⌘K on the Mac,',
    'Ctrl+K on Windows): type a few words of its name. Some items show only in the desktop app',
    'or when a setting is on; a label "A / B" is one item that reads A or B by state.\n',
  ];
  for (const it of items) {
    if (it.level === 0) {
      out.push(`\n## ${it.label}\n`);
      continue;
    }
    const indent = '  '.repeat(it.level - 1);
    const key = it.hint && /[⌘⌥⇧⌃]|^F\d+$/.test(it.hint) ? ` (${it.hint})` : '';
    const note = it.desc ? ` — ${it.desc}` : '';
    out.push(`${indent}- **${it.label}**${key}${note}`);
  }
  return out.join('\n') + '\n';
}

// --- write ------------------------------------------------------------------

let changed = 0;
function put(path: string, text: string) {
  let old = '';
  try {
    old = readFileSync(path, 'utf8');
  } catch {
    /* new file */
  }
  if (old === text) return;
  changed++;
  if (CHECK) console.log(`would change: ${path}`);
  else writeFileSync(path, text);
}

put(join(REFS, 'python-api.md'), pythonApi());
put(join(REFS, 'functions.md'), functions());
put(join(REFS, 'menus.md'), menus());

const versionFile = join(HERE, '..', 'VERSION');
const vText = readFileSync(versionFile, 'utf8').replace(/^app: .*$/m, `app: Spredin Pro ${version}`);
put(versionFile, vText);

console.log(CHECK ? (changed ? `${changed} file(s) out of date` : 'references are current') : `wrote; ${changed} file(s) changed`);
if (CHECK && changed) process.exit(1);
