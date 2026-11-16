#!/usr/bin/env python3
"""Read and write Spredin workbooks (.sprd) without the app.

    python3 sprd.py info  Book.sprd
    python3 sprd.py read  Book.sprd [--sheet NAME] [--range A1:D20] [--format cells|csv|json] [--out FILE]
    python3 sprd.py write spec.json Book.sprd [--replace]

What it does, and nothing else:
- reads the one file it is given; writes only the file named after `write`
  (or `--out`), and never over an existing file unless --replace is given;
- uses only Python's standard library; no network, no other programs.

It reads cell CONTENTS as stored (a formula is its "=..." text). It cannot work
formulas out: open the file in Spredin for computed values. A `.sprd` is gzipped
JSON; see references/files.md for the layout.

A file may come from anyone. So the text is unzipped a piece at a time and
refused past a size; fill lines are kept as rectangles and counted, never
built; every output is measured before it is written; and text from the file
is printed with control and invisible characters shown as \\u{XXXX}. The
limits are below; real workbooks stay far inside them.
"""
import argparse
import csv
import gzip
import io
import json
import os
import re
import sys
import tempfile

# --- limits ------------------------------------------------------------------
# The largest workbooks measured hold ~14 million cells, in a ~420 MB text.
MAX_FILE_BYTES = 2 * 1024 ** 3     # a .sprd (or a spec) on disk
MAX_TEXT_BYTES = 2 * 1024 ** 3     # its JSON text, unzipped (the app's own ceiling: 2^31 characters)
MAX_JSON_ITEMS = 50_000_000        # JSON values and keys outside cell text (under 90 bytes each, parsed)
MAX_FILL_CELLS = 20_000_000        # a sheet's fill lines together: the app's own bound (sprdCompact.ts)
MAX_FILL_WORK = 20_000_000         # steps spent sorting out how a sheet's fill lines lie
MAX_ROW_FIELDS = 1_048_576         # cells in one row line: 2^20, the most columns the app's cell table holds
MAX_FIELD_CHARS = 64 * 1024 * 1024 # characters in one cell
MAX_LIST_CELLS = 50_000_000        # cells `read` lists (cells and json formats), and sheet_cells() builds
MAX_PRINT_CELLS = 10_000_000       # the rectangle `read --format csv` prints, empty cells included
MAX_FILL_TEXT = 2 ** 31            # characters of fill-line formulas one `read` writes out

MAX_ROW = 16_777_215  # the app's bound for a fill line (sprdCompact.ts)
MAX_COL = 475_253     # column ZZZZ
MAX_WRITE_CELLS = 2_000_000
MAX_FORMATTED = 200_000
STYLE_KEYS = {"numFmt", "bold", "italic", "underline", "color", "fill", "align", "valign", "wrap", "fontFamily", "fontSize"}
_CHUNK = 4 * 1024 * 1024

csv.field_size_limit(MAX_FIELD_CHARS)


class SprdError(Exception):
    pass


# --- showing text --------------------------------------------------------------
# Controls (C0, DEL, C1), invisible and direction-changing format characters,
# line and paragraph separators, lone surrogates and the invisible "tag"
# characters: they can steer a terminal or a reader, and none can be seen.
# Each is shown as \u{XXXX}, and a backslash as \\, so the two never mix.
_HIDDEN = re.compile(
    "[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f\u00ad\u061c\u180e\u200b-\u200f"
    "\u2028-\u202e\u2060-\u2064\u2066-\u206f\ufeff\ufff9-\ufffb\ud800-\udfff\U000e0000-\U000e007f]"
)
_SURROGATE = re.compile("[\ud800-\udfff]")


def show(text):
    """Text as it is safe to print: backslash, tab and line ends as \\\\ \\t \\n \\r,
    every other control or invisible character as \\u{XXXX}."""
    text = str(text)
    if text.isascii() and text.isprintable() and "\\" not in text:
        return text  # the usual case, quickly
    text = text.replace("\\", "\\\\").replace("\t", "\\t").replace("\n", "\\n").replace("\r", "\\r")
    return _HIDDEN.sub(lambda m: "\\u{%04X}" % ord(m.group()), text)


def _shown(text, most=80):
    """show(), cut to `most` characters: for names in messages and summaries."""
    s = show(text)
    return s if len(s) <= most else s[:most] + "..."


def _json_escape(m):
    n = ord(m.group())
    if n > 0xFFFF:
        n -= 0x10000
        return "\\u%04x\\u%04x" % (0xD800 + (n >> 10), 0xDC00 + (n & 0x3FF))
    return "\\u%04x" % n


_encode_text = json.encoder.encode_basestring  # json.dumps of one text, without its setup


def _json(text):
    """A text as JSON, with every hidden character written as a JSON escape:
    the same data, nothing invisible."""
    out = _encode_text(text)
    if text.isascii() and "\x7f" not in text:
        return out  # the encoder escapes C0 controls itself
    return _HIDDEN.sub(_json_escape, out)


def _encodable(text):
    """Exact text for a data file, but a lone surrogate (which UTF-8 cannot
    hold) shown as \\u{XXXX}."""
    return _SURROGATE.sub(lambda m: "\\u{%04X}" % ord(m.group()), text)


# --- addresses ---------------------------------------------------------------

def col_name(c):
    s = ""
    c += 1
    while c:
        c, rem = divmod(c - 1, 26)
        s = chr(65 + rem) + s
    return s


def col_index(letters):
    n = 0
    for ch in letters.upper():
        n = n * 26 + (ord(ch) - 64)
    return n - 1


_CELL = re.compile(r"^\$?([A-Za-z]{1,4})\$?([1-9][0-9]{0,8})$")


def parse_cell(text):
    if not isinstance(text, str):
        raise SprdError(f"not a cell address: {_shown(json.dumps(text), 40)} (write it like B7)")
    m = _CELL.match(text.strip())
    if not m:
        raise SprdError(f"not a cell address: '{_shown(text, 40)}' (write it like B7)")
    return int(m.group(2)) - 1, col_index(m.group(1))


def parse_range(text):
    """'B2' or 'B2:D9' -> (r0, c0, r1, c1), 0-based, ordered."""
    if not isinstance(text, str):
        raise SprdError(f"not a range: {_shown(json.dumps(text), 40)}")
    parts = text.strip().split(":")
    if len(parts) > 2:
        raise SprdError(f"not a range: '{_shown(text, 40)}'")
    r0, c0 = parse_cell(parts[0])
    r1, c1 = parse_cell(parts[-1])
    return min(r0, r1), min(c0, c1), max(r0, r1), max(c0, c1)


_LETTERS = {}


def label(r, c):
    letters = _LETTERS.get(c)
    if letters is None:
        letters = col_name(c)
        if len(_LETTERS) < 100_000:
            _LETTERS[c] = letters
    return f"{letters}{r + 1}"


# --- reading the file ----------------------------------------------------------

def _too_big(what, limit, unit="bytes"):
    return SprdError(f"the {what} is over {limit:,} {unit}; sprd.py does not read files that large")


def _read_file(path, what="file"):
    """The file's bytes. Refuses anything but a regular file, and one over the limit."""
    if os.path.exists(path) and not os.path.isfile(path):
        raise SprdError(f"{path} is not a file")
    with open(path, "rb") as f:
        if os.fstat(f.fileno()).st_size > MAX_FILE_BYTES:
            raise _too_big(what, MAX_FILE_BYTES)
        data = f.read(MAX_FILE_BYTES + 1)
    if len(data) > MAX_FILE_BYTES:
        raise _too_big(what, MAX_FILE_BYTES)
    return data


class _Shape:
    """Counts, outside JSON strings, the values and keys json.loads would make,
    fed the text a piece at a time, so a hostile file is refused before it is
    held or parsed. An upper bound: every value but the first follows a '[',
    ',' or ':', and every key comes before a ':'. The dearest short values
    (a small list, an object, a short text, a long integer) take under 90
    bytes each in Python (measured on 3.9 and 3.14), so MAX_JSON_ITEMS holds
    the parsed JSON to about 4.5 GB; a long value takes about its own length."""

    def __init__(self):
        self.inside = False
        self.carry = b""
        self.items = 1

    def feed(self, chunk):
        data = (self.carry + chunk).replace(b"\\\\", b"")
        self.carry = b""
        if data.endswith(b"\\"):
            self.carry, data = b"\\", data[:-1]
        parts = data.replace(b'\\"', b"").split(b'"')
        outside = b"".join(parts[1::2] if self.inside else parts[0::2])
        if len(parts) % 2 == 0:
            self.inside = not self.inside
        self.items += outside.count(b"[") + outside.count(b",") + 2 * outside.count(b":")
        if self.items > MAX_JSON_ITEMS:
            raise SprdError(f"the file holds more than {MAX_JSON_ITEMS:,} JSON values; sprd.py does not read files that large")


def _gunzip(data, keep):
    """Unzip `data` a piece at a time, never past MAX_TEXT_BYTES. With keep,
    returns the text; without, only checks its size and shape, holding nothing."""
    out = bytearray() if keep else None
    shape = None if keep else _Shape()
    total = 0
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(data)) as g:
            while True:
                chunk = g.read(_CHUNK)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_TEXT_BYTES:
                    raise SprdError(f"the file unzips to more than {MAX_TEXT_BYTES:,} bytes; sprd.py does not read files that large")
                if keep:
                    out += chunk
                else:
                    shape.feed(chunk)
    except (OSError, EOFError, gzip.zlib.error):
        raise SprdError("not a .sprd workbook (the compressed data is damaged or cut short)") from None
    return out


def load(path):
    data = _read_file(path)
    if data[:2] == b"\x1f\x8b":
        _gunzip(data, keep=False)
        data = _gunzip(data, keep=True)
    else:
        if len(data) > MAX_TEXT_BYTES:
            raise _too_big("file", MAX_TEXT_BYTES)
        shape = _Shape()
        for i in range(0, len(data), _CHUNK):
            shape.feed(data[i:i + _CHUNK])
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise SprdError("not a .sprd workbook (the text is not UTF-8)") from None
    del data
    try:
        doc = json.loads(text)
    except RecursionError:
        raise SprdError("not a .sprd workbook (the JSON is nested too deeply)") from None
    except ValueError as e:
        raise SprdError(f"not a .sprd workbook (the JSON does not parse: {e})") from None
    if not isinstance(doc, dict) or not isinstance(doc.get("compactSheets", doc.get("sheets")), list):
        raise SprdError("not a .sprd workbook (no sheets)")
    return doc


def form_of(doc):
    if isinstance(doc.get("compactSheets"), list):
        return "compact"
    sheets = doc.get("sheets")
    if isinstance(sheets, list) and any(isinstance(s, dict) and s.get("fills") for s in sheets):
        return "dual"
    return "full"


def sheet_files(doc):
    """The sheets as the app reads them: `compactSheets` when present (`sheets`
    then holds only a stub for old versions), else `sheets`."""
    lst = doc.get("compactSheets") if isinstance(doc.get("compactSheets"), list) else doc.get("sheets", [])
    return [s for s in lst if isinstance(s, dict)] if isinstance(lst, list) else []


def sheet_name(sf):
    name = sf.get("name")
    return name if isinstance(name, str) else ""


# --- fill templates --------------------------------------------------------------

_TOKEN = re.compile(r"\{\{|\}\}|\{(row|col)(?:([+-])([0-9]+))?\}|[{}]|[^{}]+")


def _compile(template):
    """A fill line's template as parts: text, or ('row'|'col', offset). None
    when it cannot be read ({rows}, a lone brace, an offset past 9 digits)."""
    parts = []
    for m in _TOKEN.finditer(template):
        tok = m.group(0)
        if tok == "{{":
            parts.append("{")
        elif tok == "}}":
            parts.append("}")
        elif m.group(1):
            k = 0
            if m.group(2):
                digits = m.group(3).lstrip("0") or "0"
                if len(digits) > 9:
                    return None
                k = int(digits) * (-1 if m.group(2) == "-" else 1)
            parts.append((m.group(1), k))
        elif tok in ("{", "}"):
            return None
        else:
            parts.append(tok)
    return parts


def _render(parts, r, c):
    out = []
    for p in parts:
        if isinstance(p, str):
            out.append(p)
        elif p[0] == "row":
            if r + p[1] < 0:
                return None
            out.append(str(r + p[1] + 1))
        else:
            if c + p[1] < 0:
                return None
            out.append(col_name(c + p[1]))
    return "".join(out)


def template_at(template, r, c):
    """The formula a fill line's template reads at row r, column c (0-based),
    as the app reads it: {row} is the row number, {col} the column letters,
    {row-1} the row above, {{ and }} are braces. None when it cannot be read."""
    parts = _compile(template)
    return None if parts is None else _render(parts, r, c)


class _Fill:
    """A kept fill line: its rectangle, its compiled template, and the length
    of its longest formula (the last cell's: row numbers and letters only grow)."""
    __slots__ = ("r0", "c0", "r1", "c1", "parts", "longest", "_col", "_text")

    def __init__(self, r0, c0, r1, c1, parts):
        self.r0, self.c0, self.r1, self.c1, self.parts = r0, c0, r1, c1, parts
        self.longest = len(_render(parts, r1, c1))
        self._col = None

    def text(self, r, c):
        if self._col != c:  # the column's letters once, then only the rows change
            self._col = c
            self._text = [col_name(c + p[1]) if isinstance(p, tuple) and p[0] == "col" else p for p in self.parts]
        return "".join(p if isinstance(p, str) else str(r + p[1] + 1) for p in self._text)


# --- one sheet ----------------------------------------------------------------------

_ROW_KEY = re.compile(r"[0-9]{1,9}")
_CELL_KEY = re.compile(r"([0-9]{1,9}):([0-9]{1,9})")
_QUOTED = re.compile(r'"[^"]*"')
_END = float("inf")


def _row_width_ok(line):
    n = line.count(",") + 1
    if n > MAX_ROW_FIELDS and '"' in line:
        n = _QUOTED.sub("", line).count(",") + 1  # commas inside quotes part no fields
    return n <= MAX_ROW_FIELDS


class Sheet:
    """One sheet as sprd.py reads it, without building its cells: the fill
    lines the app keeps, as rectangles, and the row lines, as text. Fill lines
    are kept or left out as the app keeps them: a line past its bounds, whose
    first cell is not a formula, that covers a cell an earlier line covers, or
    that takes the sheet's fill lines past MAX_FILL_CELLS is left out, and
    `notes` says so. The rows win over the fills where both give a cell."""

    def __init__(self, sf):
        self.name = sheet_name(sf)
        self.notes = []
        self.fills = []
        self.rows = {}      # row -> its CSV line, or {col: text} from the old cell map
        self.work = 0
        legacy = sf.get("cells")
        if isinstance(legacy, dict):
            bad = 0
            for key, raw in legacy.items():
                m = _CELL_KEY.fullmatch(str(key))
                if not m or not isinstance(raw, str):
                    bad += 1
                elif raw != "":
                    self.rows.setdefault(int(m.group(1)), {})[int(m.group(2))] = raw
            if bad:
                self.notes.append(f"{bad} cell(s) of the old cell map could not be read")
            return
        self._keep_fills(sf.get("fills"))
        rows = sf.get("rows")
        if rows is None:
            rows = {}
        if not isinstance(rows, dict):
            self.notes.append("the rows could not be read")
            rows = {}
        bad = 0
        for key, line in rows.items():
            if not _ROW_KEY.fullmatch(str(key)) or not isinstance(line, str) or not _row_width_ok(line):
                bad += 1
            else:
                self.rows[int(key)] = line
        if bad:
            self.notes.append(f"{bad} row(s) could not be read (not a row number, or more than {MAX_ROW_FIELDS:,} cells)")

    def _spend(self, n):
        self.work += n
        if self.work > MAX_FILL_WORK:
            raise SprdError(f"sheet '{_shown(self.name, 40)}': its fill lines lie in too many pieces to sort out")

    def _keep_fills(self, lines):
        if not lines:
            return
        if not isinstance(lines, list):
            self.notes.append("the fill lines could not be read")
            return
        left_out = 0
        total = 0
        narrow = {}   # column -> [(r0, r1)] of kept lines up to 64 columns wide
        wide = []     # kept lines wider than that
        for line in lines:
            if not isinstance(line, str) or " " not in line:
                left_out += 1
                continue
            rng, template = line.split(" ", 1)
            try:
                r0, c0, r1, c1 = parse_range(rng)
            except SprdError:
                left_out += 1
                continue
            parts = _compile(template.lstrip(" "))
            first = _render(parts, r0, c0) if parts is not None else None
            size = (r1 - r0 + 1) * (c1 - c0 + 1)
            if r1 > MAX_ROW or c1 > MAX_COL or first is None or not first.startswith("=") or total + size > MAX_FILL_CELLS:
                left_out += 1
                continue
            # Does it cover a cell an earlier kept line covers? (by rectangle, so
            # a read of a part decides it exactly as a read of the whole does)
            self._spend(len(wide))
            clash = any(f.r0 <= r1 and f.r1 >= r0 and f.c0 <= c1 and f.c1 >= c0 for f in wide)
            if not clash:
                span = c1 - c0 + 1
                cols = range(c0, c1 + 1) if span <= len(narrow) else [k for k in narrow if c0 <= k <= c1]
                self._spend(min(span, len(narrow)))
                for k in cols:
                    spans = narrow.get(k, ())
                    self._spend(len(spans))
                    if any(a <= r1 and b >= r0 for a, b in spans):
                        clash = True
                        break
            if clash:
                left_out += 1
                continue
            total += size
            f = _Fill(r0, c0, r1, c1, parts)
            self.fills.append(f)
            if c1 - c0 + 1 > 64:
                wide.append(f)
            else:
                for k in range(c0, c1 + 1):
                    narrow.setdefault(k, []).append((r0, r1))
        if left_out:
            self.notes.append(f"{left_out} fill line(s) left out, as Spredin leaves them out (unreadable, past its bounds, "
                              f"not a formula, covering cells an earlier line covers, or past {MAX_FILL_CELLS:,} fill cells)")

    # -- rows in order ----------------------------------------------------------------

    def _row_cells(self, r, box):
        """The cells of row r's line, in column order: [(c, text)], empty ones left out."""
        line = self.rows[r]
        if isinstance(line, dict):
            items = sorted(line.items())
        else:
            try:
                fields = next(csv.reader(io.StringIO(line, newline=""), strict=False), [])
            except csv.Error:
                raise SprdError(f"a cell holds more than {MAX_FIELD_CHARS:,} characters, or a row cannot be read") from None
            items = enumerate(fields)
        return [(c, t) for c, t in items if t != "" and (box is None or box[1] <= c <= box[3])]

    def _clipped(self, box):
        """The kept fill lines as (r0, c0, r1, c1, fill), cut to the box."""
        out = []
        for f in self.fills:
            if box is None:
                out.append((f.r0, f.c0, f.r1, f.c1, f))
            else:
                r0, c0, r1, c1 = max(f.r0, box[0]), max(f.c0, box[1]), min(f.r1, box[2]), min(f.c1, box[3])
                if r0 <= r1 and c0 <= c1:
                    out.append((r0, c0, r1, c1, f))
        return out

    def _runs(self, box):
        """The rows that hold anything, in order, as (first, last, active, has_line):
        rows first..last are covered by the fills in `active` (an _Active, valid
        until the next step); has_line says row `first` (then == last) has a row
        line too. Each step costs what changed, so a sheet of many fill lines is
        as cheap to walk as its rows."""
        self.work = 0
        starts, ends = {}, {}
        for r0, c0, r1, c1, f in self._clipped(box):
            starts.setdefault(r0, []).append((c0, c1, f))
            ends.setdefault(r1 + 1, []).append((c0, c1, f))
        events = sorted(set(starts) | set(ends))
        rows = sorted(r for r in self.rows if box is None or box[0] <= r <= box[2])
        act = _Active(self)
        e = j = 0
        cur = min(rows[0] if rows else _END, events[0] if events else _END)
        while cur != _END:
            if e < len(events) and events[e] == cur:
                for x in ends.get(cur, ()):
                    act.drop(*x)
                for x in starts.get(cur, ()):
                    act.add(*x)
                e += 1
            first = cur
            if j < len(rows) and rows[j] == cur:
                yield cur, cur, act, True
                j += 1
                first = cur + 1
            nxt = min(rows[j] if j < len(rows) else _END, events[e] if e < len(events) else _END)
            if act.width and first <= nxt - 1:
                yield first, nxt - 1, act, False
            cur = nxt

    def stats(self, box=None):
        """Counted, never built: cells, formulas, fill cells, the characters
        the fill cells' formulas take, the longest of them, and the last row
        and column with a cell."""
        s = {"cells": 0, "formulas": 0, "fill_cells": 0, "fill_text": 0, "longest_fill": 0, "last_row": -1, "last_col": -1}
        for r0, c0, r1, c1, f in self._clipped(box):
            s["last_row"] = max(s["last_row"], r1)
            s["last_col"] = max(s["last_col"], c1)
            s["longest_fill"] = max(s["longest_fill"], f.longest)
        for first, last, act, has_line in self._runs(box):
            n = last - first + 1
            s["cells"] += n * act.width
            s["formulas"] += n * act.width
            s["fill_cells"] += n * act.width
            s["fill_text"] += n * act.text
            if has_line:
                cells = self._row_cells(first, box)
                for c, t in cells:
                    f = act.covering(c)
                    if f is not None:  # it takes a fill cell's place
                        s["formulas"] -= 1
                        s["fill_cells"] -= 1
                        s["fill_text"] -= f.longest
                    else:
                        s["cells"] += 1
                    if t.startswith("="):
                        s["formulas"] += 1
                if cells:
                    s["last_row"] = max(s["last_row"], first)
                    s["last_col"] = max(s["last_col"], cells[-1][0])
        return s

    def cells(self, box=None):
        """Every cell (r, c, text) in row, then column order."""
        for first, last, act, has_line in self._runs(box):
            order = act.ordered()
            if not has_line:
                for r in range(first, last + 1):
                    for c0, c1, f in order:
                        for c in range(c0, c1 + 1):
                            yield r, c, f.text(r, c)
                continue
            line = self._row_cells(first, box)
            k = 0
            for c0, c1, f in order:
                for c in range(c0, c1 + 1):
                    while k < len(line) and line[k][0] < c:
                        yield first, line[k][0], line[k][1]
                        k += 1
                    if k < len(line) and line[k][0] == c:  # the row wins
                        yield first, c, line[k][1]
                        k += 1
                    else:
                        yield first, c, f.text(first, c)
            for c, t in line[k:]:
                yield first, c, t


def _last_at_most(keys, x):
    """The index of the last key <= x in a sorted list, or -1."""
    lo, hi = 0, len(keys)
    while lo < hi:
        mid = (lo + hi) // 2
        if keys[mid] <= x:
            lo = mid + 1
        else:
            hi = mid
    return lo - 1


class _Active:
    """The fill lines covering the current row: no two cover the same column
    (the app keeps no overlapping lines). Lines up to 64 columns wide are kept
    by column; wider ones in a list sorted by their first column."""

    def __init__(self, sheet):
        self.sheet = sheet
        self.cols = {}
        self.wide_c0 = []
        self.wide = []
        self.width = 0
        self.text = 0
        self._order = None

    def add(self, c0, c1, f):
        self._order = None
        w = c1 - c0 + 1
        self.width += w
        self.text += w * f.longest
        if f.c1 - f.c0 + 1 > 64:
            k = _last_at_most(self.wide_c0, c0) + 1
            self.wide_c0.insert(k, c0)
            self.wide.insert(k, (c0, c1, f))
            self.sheet._spend(1)
        else:
            for c in range(c0, c1 + 1):
                self.cols[c] = f
            self.sheet._spend(w)

    def drop(self, c0, c1, f):
        self._order = None
        w = c1 - c0 + 1
        self.width -= w
        self.text -= w * f.longest
        if f.c1 - f.c0 + 1 > 64:
            k = _last_at_most(self.wide_c0, c0)
            while self.wide[k][2] is not f:
                k -= 1
            del self.wide_c0[k], self.wide[k]
            self.sheet._spend(1)
        else:
            for c in range(c0, c1 + 1):
                if self.cols.get(c) is f:
                    del self.cols[c]
            self.sheet._spend(w)

    def covering(self, c):
        f = self.cols.get(c)
        if f is not None:
            return f
        k = _last_at_most(self.wide_c0, c)
        if k >= 0 and c <= self.wide[k][1]:
            return self.wide[k][2]
        return None

    def ordered(self):
        """[(c0, c1, fill)] in column order."""
        if self._order is None:
            self._order = sorted([(c, c, f) for c, f in self.cols.items()] + self.wide, key=lambda x: x[0])
        return self._order


def sheet_cells(sf, box=None):
    """{(r, c): text} for one sheet: the fill lines first, then the rows, which
    win where they write a cell (the app's rule). Empty cells are left out.
    Refuses a sheet of more than MAX_LIST_CELLS cells."""
    sheet = Sheet(sf)
    n = sheet.stats(box)["cells"]
    if n > MAX_LIST_CELLS:
        raise SprdError(f"sheet '{_shown(sheet.name, 40)}' holds {n:,} cells, more than {MAX_LIST_CELLS:,}")
    return {(r, c): t for r, c, t in sheet.cells(box)}


def pick_sheet(doc, which):
    files = sheet_files(doc)
    if which is None:
        return files
    for sf in files:
        if sheet_name(sf).lower() == which.lower():
            return [sf]
    if re.fullmatch(r"[0-9]{1,9}", which) and 1 <= int(which) <= len(files):
        return [files[int(which) - 1]]
    names = ", ".join("'" + _shown(sheet_name(s), 40) + "'" for s in files[:20])
    more = f" and {len(files) - 20} more" if len(files) > 20 else ""
    raise SprdError(f"no sheet '{_shown(which, 40)}'; the sheets are {names}{more}")


def cmd_info(args):
    doc = load(args.file)
    version = doc.get("spredin")
    version = version if isinstance(version, int) and not isinstance(version, bool) and 0 <= version < 10 ** 6 else "?"
    out = [f"form: {form_of(doc)} (file version {version})"]
    for i, sf in enumerate(sheet_files(doc), 1):
        sheet = Sheet(sf)
        s = sheet.stats()
        extent = " " + label(0, 0) + ":" + label(s["last_row"], s["last_col"]) if s["cells"] else ""
        parts = [f"{s['cells']} cells", f"{s['formulas']} formulas"]
        for key, what in (("fills", "fill lines"), ("charts", "charts"), ("merges", "merges"), ("cf", "conditional formats"), ("validations", "validation rules"), ("comments", "notes")):
            v = sf.get(key)
            if v:
                parts.append(f"{len(v) if isinstance(v, (list, dict)) else 1} {what}")
        if sf.get("styles") or sf.get("styleRuns") or sf.get("formats"):
            parts.append("formatted")
        if sf.get("hidden"):
            parts.append("hidden")
        if sf.get("pivot"):
            parts.append("pivot table")
        out.append(f"sheet {i}: '{_shown(sheet.name)}'{extent} - " + ", ".join(parts + sheet.notes))
    names = doc.get("names")
    if isinstance(names, dict) and names:
        shown = [f"{_shown(k)} = {_shown(v if isinstance(v, str) else json.dumps(v)[:200])}" for k, v in list(names.items())[:50]]
        more = f", and {len(names) - 50:,} more" if len(names) > 50 else ""
        out.append("names: " + ", ".join(shown) + more)
    scripts = doc.get("scripts")
    if isinstance(scripts, list):
        files = [_shown(s["name"]) for s in scripts if isinstance(s, dict) and isinstance(s.get("name"), str)]
        if files:
            more = f", and {len(files) - 50:,} more" if len(files) > 50 else ""
            out.append("Python files: " + ", ".join(files[:50]) + more)
    pro = [what for key, what in (("decks", "slide decks"), ("memory", "assistant memory"), ("chat", "kept conversation")) if doc.get(key)]
    if pro:
        out.append("Spredin Pro parts: " + ", ".join(pro))
    print("\n".join(out))


def cmd_read(args):
    if args.out and not args.replace and os.path.exists(args.out):
        raise SprdError(f"{args.out} exists; pass --replace to write over it")
    if args.max < 0:
        raise SprdError("--max is a number of cells, 0 for all")
    doc = load(args.file)
    chosen = [Sheet(sf) for sf in pick_sheet(doc, args.sheet)]
    box = parse_range(args.range) if args.range else None
    # Measure what will be written before writing any of it.
    listed = printed = fill_text = 0
    plan = []
    for sheet in chosen:
        s = sheet.stats(box)
        if args.format == "csv":
            r0, c0 = (box[0], box[1]) if box else (0, 0)
            area = (s["last_row"] - r0 + 1) * (s["last_col"] - c0 + 1) if s["cells"] else 0
            printed += area
            fill_text += s["fill_text"]
            if printed > MAX_PRINT_CELLS:
                raise SprdError(f"a CSV of sheet '{_shown(sheet.name, 40)}' would be {label(r0, c0)}:{label(s['last_row'], s['last_col'])}, "
                                f"{area:,} cells with the empty ones (the limit is {MAX_PRINT_CELLS:,}); read a smaller part with --range, "
                                "or use --format cells or json, which list only the cells that hold something")
        else:
            cap = args.max if args.format == "cells" and args.max > 0 else None
            listed += s["cells"] if cap is None else min(s["cells"], cap)
            fill_text += s["fill_text"] if cap is None else min(s["fill_cells"], cap) * s["longest_fill"]
            if listed > MAX_LIST_CELLS:
                raise SprdError(f"that would list more than {MAX_LIST_CELLS:,} cells; read one sheet (--sheet), a part (--range), or fewer (--max)")
        if fill_text > MAX_FILL_TEXT:
            raise SprdError(f"the fill lines would write out more than {MAX_FILL_TEXT:,} characters of formulas; read a part with --range")
        plan.append((sheet, s))
    for sheet in chosen:
        for n in sheet.notes:
            print(f"sprd.py: note: sheet '{_shown(sheet.name, 40)}': {n}", file=sys.stderr)
    to_file = bool(args.out)

    def fill(sink):
        if args.format == "json":
            sink.write("{")
            for k, (sheet, _) in enumerate(plan):
                sink.write(("," if k else "") + "\n " + _json(sheet.name) + ": {")
                n = 0
                for r, c, t in sheet.cells(box):
                    sink.write(f'{"," if n else ""}\n  "{label(r, c)}": {_json(t)}')
                    n += 1
                sink.write("\n }" if n else "}")
            sink.write("\n}\n" if plan else "}\n")
            return
        for sheet, s in plan:
            if args.format == "csv":
                if len(plan) > 1:
                    sink.write(f"# sheet {show(sheet.name)}\n")
                if not s["cells"]:
                    continue
                r0, c0 = (box[0], box[1]) if box else (0, 0)
                width = s["last_col"] - c0 + 1
                # On the screen every hidden character is shown; a file gets the text exactly.
                cell = _encodable if to_file else show
                w = csv.writer(sink, lineterminator="\n")
                row, fields = r0, [""] * width
                for r, c, t in sheet.cells(box):
                    while row < r:
                        w.writerow(fields)
                        row, fields = row + 1, [""] * width
                    fields[c - c0] = cell(t)
                w.writerow(fields)
                continue
            sink.write(f"# sheet {show(sheet.name)}: {s['cells']} cells\n")
            shown = 0
            for r, c, t in sheet.cells(box):
                if args.max and shown >= args.max:
                    sink.write(f"# ... {s['cells'] - shown} more: use --range, --max 0 or --out\n")
                    break
                sink.write(f"{label(r, c)}\t{show(t)}\n")
                shown += 1

    if to_file:
        _write_out(args.out, args.replace, fill, text=True)
    else:
        fill(sys.stdout)


# --- writing -----------------------------------------------------------------

def _write_out(path, replace, fill, text):
    """Write a file through a temporary file in the same folder and a rename;
    `fill(f)` writes the content. Never over an existing file unless `replace`."""
    folder = os.path.dirname(os.path.abspath(path))
    fd, tmp = tempfile.mkstemp(prefix=".sprd-", dir=folder)
    try:
        with (os.fdopen(fd, "w", encoding="utf-8", newline="") if text else os.fdopen(fd, "wb")) as f:
            fill(f)
        if replace:
            os.replace(tmp, path)
        else:
            try:
                os.link(tmp, path)  # fails if the file exists, with no gap to race
            except FileExistsError:
                raise SprdError(f"{path} exists; pass --replace to write over it") from None
            except OSError:
                if os.path.exists(path):  # a folder that cannot hold links
                    raise SprdError(f"{path} exists; pass --replace to write over it") from None
                os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


_BAD_NAME = re.compile(r"[\[\]:*?/\\]")


def check_sheet_name(name, seen):
    if not isinstance(name, str) or not name.strip():
        raise SprdError("every sheet needs a name")
    if len(name) > 31 or _BAD_NAME.search(name) or _HIDDEN.search(name) or name.startswith("'") or name.endswith("'"):
        raise SprdError(f"sheet name '{_shown(name, 40)}': at most 31 characters, none of [ ] : * ? / \\ nor control characters, no apostrophe at either end")
    if name.lower() in seen:
        raise SprdError(f"two sheets are called '{_shown(name, 40)}'")
    seen.add(name.lower())


def cell_text(v, where):
    if v is None:
        return ""
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    if isinstance(v, int):
        if abs(v) >= 10 ** 300:
            raise SprdError(f"{where}: the number is too large for a cell")
        return str(v)
    if isinstance(v, float):
        if v != v or v in (float("inf"), float("-inf")):
            raise SprdError(f"{where}: {v!r} is not a number a cell can hold")
        return repr(v) if v != int(v) or abs(v) >= 1e15 else str(int(v))
    if isinstance(v, str):
        if len(v) > MAX_FIELD_CHARS:
            raise SprdError(f"{where}: more than {MAX_FIELD_CHARS:,} characters")
        return v
    raise SprdError(f"{where}: {type(v).__name__} is not a cell value (use text, a number, true/false or null)")


def encode_row(fields):
    out = []
    for f in fields:
        if any(ch in f for ch in ',"\n\r'):
            f = '"' + f.replace('"', '""') + '"'
        out.append(f)
    while out and out[-1] == "":
        out.pop()
    return ",".join(out)


def _object(v, where, what):
    if v is None:
        return {}
    if not isinstance(v, dict):
        raise SprdError(f"{where}: {what} is an object ({{...}})")
    return v


def _whole(v, where, what, most):
    if isinstance(v, bool) or not isinstance(v, (int, float)) or v != v or not 0 <= v <= most:
        raise SprdError(f"{where}: {what} is a number from 0 to {most:,}")
    return int(v)


def build_sheet(spec, i):
    where = f"sheet {i + 1}"
    grid = {}
    r0, c0 = parse_cell(spec.get("at", "A1"))
    rows = spec.get("rows") or []
    if not isinstance(rows, list):
        raise SprdError(f"{where}: rows is a list of rows (lists)")

    def put(r, c, t):
        if r > MAX_ROW or c > MAX_COL:
            raise SprdError(f"{where}: {label(r, c)} is past the last row or column")
        if (r, c) not in grid and len(grid) >= MAX_WRITE_CELLS:
            raise SprdError(f"{where}: more than {MAX_WRITE_CELLS:,} cells; write a .csv for data this size")
        grid[(r, c)] = t

    for dr, row in enumerate(rows):
        if not isinstance(row, list):
            raise SprdError(f"{where}: row {dr + 1} is not a list")
        for dc, v in enumerate(row):
            t = cell_text(v, f"{where} {label(r0 + dr, c0 + dc)}")
            if t != "":
                put(r0 + dr, c0 + dc, t)
    for addr, v in _object(spec.get("cells"), where, "cells").items():
        r, c = parse_cell(addr)
        t = cell_text(v, f"{where} {addr}")
        if t == "":
            grid.pop((r, c), None)
        else:
            put(r, c, t)
    by_row = {}
    for (r, c), t in grid.items():
        by_row.setdefault(r, {})[c] = t
    sf = {"name": spec["name"], "rows": {}}
    for r in sorted(by_row):
        fields = by_row[r]
        sf["rows"][str(r)] = encode_row([fields.get(c, "") for c in range(max(fields) + 1)])
    styles = {}
    for rng, fmt in _object(spec.get("formats"), where, "formats").items():
        style = {"numFmt": fmt} if isinstance(fmt, str) else fmt
        if not isinstance(style, dict) or not style or set(style) - STYLE_KEYS:
            raise SprdError(f"{where}: format for {_shown(rng, 40)}: a number format text, or an object with {sorted(STYLE_KEYS)}")
        a, b, c, d = parse_range(rng)
        if (c - a + 1) * (d - b + 1) + len(styles) > MAX_FORMATTED:
            raise SprdError(f"{where}: too many formatted cells; format whole columns in the app instead")
        for r in range(a, c + 1):
            for col in range(b, d + 1):
                styles.setdefault(f"{r}:{col}", {}).update(style)
    if styles:
        sf["styles"] = styles
    widths = _object(spec.get("widths"), where, "widths")
    if widths:
        colw = {}
        for k, v in widths.items():
            if not re.fullmatch(r"[A-Za-z]{1,4}", k):
                raise SprdError(f"{where}: widths: '{_shown(k, 20)}' is not a column letter")
            colw[str(col_index(k))] = _whole(v, where, f"the width of column {k}", 10_000)
        sf["colW"] = colw
    freeze = spec.get("freeze")
    if freeze:
        freeze = _object(freeze, where, "freeze")
        sf["freeze"] = {"rows": _whole(freeze.get("rows", 0), where, "freeze rows", MAX_ROW),
                        "cols": _whole(freeze.get("cols", 0), where, "freeze cols", MAX_COL)}
    return sf, len(grid)


def cmd_write(args):
    if os.path.exists(args.out) and not args.replace:
        raise SprdError(f"{args.out} exists; pass --replace to write over it")
    try:
        spec = json.loads(_read_file(args.spec, "spec").decode("utf-8-sig"))
    except UnicodeDecodeError:
        raise SprdError("the spec is not UTF-8 text") from None
    except RecursionError:
        raise SprdError("the spec is nested too deeply") from None
    except ValueError as e:
        raise SprdError(f"the spec is not JSON: {e}") from None
    sheets = spec.get("sheets") if isinstance(spec, dict) else None
    if not isinstance(sheets, list) or not sheets:
        raise SprdError('the spec needs "sheets": [{"name": ..., "rows": [[...], ...]}]')
    seen = set()
    files = []
    total = 0
    for i, s in enumerate(sheets):
        if not isinstance(s, dict):
            raise SprdError(f"sheet {i + 1} is not an object")
        check_sheet_name(s.get("name"), seen)
        sf, n = build_sheet(s, i)
        total += n
        if total > MAX_WRITE_CELLS:
            raise SprdError(f"more than {MAX_WRITE_CELLS:,} cells in all; write a .csv for data this size")
        files.append(sf)
    doc = {"spredin": 1, "active": 0, "sheets": files}
    names = _object(spec.get("names"), "the spec", "names")
    if names:
        for k, v in names.items():
            if not isinstance(v, str):
                raise SprdError(f"name '{_shown(k, 40)}': its target is text, like Sheet1!$B$2")
        doc["names"] = dict(names)
    data = gzip.compress(json.dumps(doc, ensure_ascii=False, indent=1).encode("utf-8"))
    _write_out(args.out, args.replace, lambda f: f.write(data), text=False)
    print(f"wrote {args.out}: {len(files)} sheet(s), {total} cells")


def main(argv=None):
    p = argparse.ArgumentParser(prog="sprd.py", description="Read and write Spredin .sprd workbooks.")
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("info", help="what is in a workbook")
    a.add_argument("file")
    a.set_defaults(run=cmd_info)
    a = sub.add_parser("read", help="cell contents (formulas as written)")
    a.add_argument("file")
    a.add_argument("--sheet", help="name or number (from 1); default every sheet")
    a.add_argument("--range", help="only these cells, e.g. A1:D20")
    a.add_argument("--format", choices=("cells", "csv", "json"), default="cells")
    a.add_argument("--max", type=int, default=500, help="cells format: stop after this many (0 = all)")
    a.add_argument("--out", help="write to this file instead of the screen")
    a.add_argument("--replace", action="store_true", help="let --out write over a file")
    a.set_defaults(run=cmd_read)
    a = sub.add_parser("write", help="make a .sprd from a JSON spec (see references/files.md)")
    a.add_argument("spec")
    a.add_argument("out")
    a.add_argument("--replace", action="store_true", help="write over an existing file")
    a.set_defaults(run=cmd_write)
    args = p.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):  # a console that cannot show a character gets an escape, not a crash
            stream.reconfigure(errors="backslashreplace")
    what = "spec" if args.cmd == "write" else "file"
    try:
        args.run(args)
        return 0
    except SprdError as e:
        msg = str(e)
    except OSError as e:
        msg = str(e)
    except RecursionError:
        msg = f"the {what} is nested too deeply"
    except MemoryError:
        msg = f"not enough memory for this {what}"
    except (ValueError, TypeError, AttributeError, KeyError, IndexError, OverflowError) as e:
        # A shape no check above expected: one line, with nothing from the file in it.
        msg = f"the {what} is not in a shape sprd.py can read ({type(e).__name__})"
    print(f"sprd.py: {msg}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
