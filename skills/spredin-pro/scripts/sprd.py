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
# A sheet's fill lines together, the app's own bounds (sprdCompact.ts FILL_LIMITS);
# a line that would pass one is left out, as the app leaves it out:
MAX_FILL_CELLS = 20_000_000        #   their cells
MAX_FILL_COLUMNS = 6_666_666       #   the columns of their lines (each column a writer writes holds 3 cells or more)
MAX_FILL_LINE_TEXT = 2 ** 31 - 1   #   each line's cells times its template's length (in UTF-16 units, as the app counts)
MAX_FILL_MOVES = 2 ** 31           #   ranges moved aside to keep each column's ranges in row order
MAX_FILL_WORK = 20_000_000         # steps spent walking a sheet's fill lines row by row
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
    if not isinstance(doc, dict):
        raise SprdError("not a .sprd workbook (no sheets)")
    if is_newer_version(doc.get("spredin")):
        # As Spredin refuses it (workbook.ts deserializeWorkbook): such a file
        # may hold parts this version would misread with nothing to say so.
        raise SprdError(f"this workbook was saved by a newer version of Spredin (file version {int(doc['spredin'])}); "
                        "update Spredin to open it")
    if not isinstance(doc.get("compactSheets", doc.get("sheets")), list):
        raise SprdError("not a .sprd workbook (no sheets)")
    return doc


def is_newer_version(v):
    """Is `spredin` a version newer than the compact form's 2? A whole number
    from 3 to 999, as the app judges it: 3.0 and 1e2 are whole numbers in
    JSON, and one damaged value (3.7, 1e308, "3") costs nothing."""
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not 2 < v < 1000:
        return False
    return isinstance(v, int) or v.is_integer()


def form_of(doc):
    if isinstance(doc.get("compactSheets"), list):
        return "compact"
    sheets = doc.get("sheets")
    if isinstance(sheets, list) and any(isinstance(s, dict) and s.get("fills") for s in sheets):
        return "dual"
    return "full"


def rows_hold_every_cell(doc):
    """True unless the file is in the compact form. A file read from `sheets`
    holds every cell in its rows; fill lines beside them (the dual form) may
    confirm a cell but never add one, as the app reads them (workbook.ts
    deserializeWorkbook, store.ts applyFills with `complete`)."""
    return not isinstance(doc.get("compactSheets"), list)


def sheet_files(doc):
    """The sheets as the app reads them: `compactSheets` when present (`sheets`
    then holds only a stub for old versions), else `sheets`."""
    lst = doc.get("compactSheets") if isinstance(doc.get("compactSheets"), list) else doc.get("sheets", [])
    return [s for s in lst if isinstance(s, dict)] if isinstance(lst, list) else []


def sheet_name(sf):
    name = sf.get("name")
    return name if isinstance(name, str) else ""


# --- fill templates --------------------------------------------------------------
# A fill line is "RANGE TEMPLATE". The app keeps a line only if its template is
# exactly what its own writer would write for the formula the template reads at
# the first cell (fillTemplate.ts checkTemplate), and then every other cell holds
# that formula MOVED as the fill handle moves it (editops.ts shiftFormulaRefs,
# compileShift). Both rest on the app's one scanner of references (editops.ts
# scanRefs), ported below. Numbers the app's JavaScript might not hold exactly
# (a row or an offset of 2^52 or more) are not guessed at: such a line is left out.

_TOKEN = re.compile(r"\{\{|\}\}|\{(row|col)(?:([+-])([0-9]+))?\}|[{}]|[^{}]+")
_BIG = 2 ** 52  # a row this large, or an offset near it: the line is left out (see above)


def _compile(template):
    """A fill line's template as parts: text, or ('row'|'col', offset). None
    when it cannot be read ({rows}, a lone brace, an offset of 2^52 less a
    sheet's rows or more)."""
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
                if len(digits) > 16 or int(digits) >= _BIG - 2 ** 25:
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
    as the app's templateAt reads it: {row} is the row number, {col} the
    column letters, {row-1} the row above, {{ and }} are braces. None when it
    cannot be read. A kept line's first cell holds this; the others hold it
    moved (_Fill.text), which differs only in how references are spelled."""
    parts = _compile(template)
    return None if parts is None else _render(parts, r, c)


# -- references in a formula: the app's scanner (editops.ts scanRefs) --

_R_CELL = re.compile(r"(\$?)([A-Za-z]{1,4})(\$?)([0-9]+)")
_R_COLS = re.compile(r"(\$?)([A-Za-z]{1,4}):(\$?)([A-Za-z]{1,4})")
_R_ROWS = re.compile(r"(\$?)([0-9]+):(\$?)([0-9]+)")
_R_ANY_CELL = re.compile(r"(\$?)([A-Za-z]+)(\$?)([0-9]+)")
_R_ROW_SPAN = re.compile(r"(\$?)([0-9]+):(\$?)([0-9]+)")
_R_COL_SPAN = re.compile(r"(\$?)([A-Za-z]+):(\$?)([A-Za-z]+)")
_STR_QUOTES = '"\u201c\u201d'  # a string literal: straight or curly quotes, either closing it


class _Unsure(Exception):
    """A row number the app's JavaScript might not hold exactly."""


def _ident(ch):
    return ch != "" and ch.isascii() and (ch.isalnum() or ch in "_.")


def _letter(ch):
    return ("A" <= ch <= "Z") or ("a" <= ch <= "z")


def _row_of(digits):
    """A row as written (`007`), 0-based. Raises _Unsure past 2^52."""
    t = digits.lstrip("0")
    if len(t) > 16 or int(t or "0") >= _BIG:
        raise _Unsure
    return int(t or "0") - 1


def _end_of(m):
    """One end of a cell reference: (column absolute, column, row absolute, row)."""
    return (m.group(1) == "$", col_index(m.group(2)), m.group(3) == "$", _row_of(m.group(4)))


def _word_end(s, i, wide):
    """Where a sheet name's word starting at i ends ([A-Za-z_][A-Za-z0-9_.]*,
    or, in a formula with any character past ASCII, letters and digits of any
    script, as the app's \\p{L} and \\p{N}), or -1."""
    n = len(s)
    if i >= n:
        return -1
    ch = s[i]
    if not (ch == "_" or _letter(ch) or (wide and ch.isalpha())):
        return -1
    j = i + 1
    while j < n:
        ch = s[j]
        if ch in "_." or (ch.isascii() and ch.isalnum()) or (wide and (ch.isalpha() or ch.isnumeric())):
            j += 1
        else:
            break
    return j


def _scan_refs(s, far=()):
    """Every reference in formula s, left to right, as (where, length, ref):
    ('cells', end, end or None), ('cols', $, col, $, col) or ('rows', $, row,
    $, row). Text in quotes, function names, sheet and table names spelled
    like cells, and a defined name in `far` spelled like a cell (`Rate1`)
    are not references. Raises _Unsure for a row past 2^52."""
    out = []
    if not s.startswith("="):
        return out
    n = len(s)
    wide = not s.isascii()

    def take(i, qualified):
        """The length taken at i: a reference (noted), or a function name or
        a longer word spelled like one (not noted); 0 for nothing."""
        m = _R_CELL.match(s, i)
        if m:
            end = m.end()
            after = s[end:end + 1]
            if after == "(" or _ident(after):
                return end - i
            if far and qualified is None and after != ":" and m.group(0).lower() in far:
                return end - i
            a, b = _end_of(m), None
            if after == ":":
                m2 = _R_CELL.match(s, end + 1)
                if m2:
                    after2 = s[m2.end():m2.end() + 1]
                    if after2 != "(" and not _ident(after2):
                        b, end = _end_of(m2), m2.end()
            out.append((i, end - i, ("cells", a, b)))
            return end - i
        m = _R_COLS.match(s, i)
        if m:
            if s[m.end():m.end() + 1] == "(" or _ident(s[m.end():m.end() + 1]):
                return 0
            out.append((i, m.end() - i, ("cols", m.group(1), col_index(m.group(2)), m.group(3), col_index(m.group(4)))))
            return m.end() - i
        m = _R_ROWS.match(s, i)
        if m:
            if _ident(s[m.end():m.end() + 1]):
                return 0
            out.append((i, m.end() - i, ("rows", m.group(1), _row_of(m.group(2)), m.group(3), _row_of(m.group(4)))))
            return m.end() - i
        return 0

    i = 0
    while i < n:
        ch = s[i]
        if ch in _STR_QUOTES:  # a string literal, copied as it is
            i += 1
            while i < n:
                closes = s[i] in _STR_QUOTES
                i += 1
                if closes:
                    break
            continue
        prev = s[i - 1] if i else ""
        if ch == "[" and _ident(prev):  # a table's columns: T[Q1], T[[#This Row],[A1]]
            depth = 0
            while i < n:
                if s[i] == "[":
                    depth += 1
                elif s[i] == "]":
                    depth -= 1
                    if depth == 0:
                        i += 1
                        break
                i += 1
            continue
        if _ident(prev) or prev == "$" or prev == "!" or (wide and prev > "\x7f"):
            i += 1  # not at the start of a word
            continue
        if ch == "'":  # 'My Sheet'!A1, with '' for a quote
            j, closed = i + 1, False
            while j < n:
                if s[j] == "'":
                    if s[j + 1:j + 2] == "'":
                        j += 2
                        continue
                    closed = True
                    j += 1
                    break
                j += 1
            if closed and s[j:j + 1] == "!":
                i = j + 1
                i += take(i, "")
                continue
            i += 1
            continue
        if _letter(ch) or ch == "_" or (wide and ch > "\x7f"):
            # Sheet1!A1, Jan:Dec!B5: the names are sheets, whatever they look like.
            e = _word_end(s, i, wide)
            if e > 0:
                if s[e:e + 1] == ":":
                    e2 = _word_end(s, e + 1, wide)
                    if e2 > 0 and s[e2:e2 + 1] == "!":
                        i = e2 + 1
                        i += take(i, "")
                        continue
                if s[e:e + 1] == "!":
                    i = e + 1
                    i += take(i, "")
                    continue
        if _letter(ch) or "0" <= ch <= "9" or ch == "$":
            got = take(i, None)
            if got:
                i += got
                continue
        i += 1
    return out


def _ph(name, k):
    return "{%s}" % name if k == 0 else "{%s+%d}" % (name, k) if k > 0 else "{%s%d}" % (name, k)


def _fill_template(first, r0, c0, across, far):
    """The template the app's writer writes for formula `first` at (r0, c0)
    (fillTemplate.ts fillTemplate): every relative row of a reference as
    {row+k}, with `across` every relative column as {col+k}; braces doubled."""
    out, last = [], 0
    for at, length, ref in _scan_refs(first, far):
        out.append(first[last:at].replace("{", "{{").replace("}", "}}"))
        text = first[at:at + length]
        if ref[0] == "cells":
            ends = [e for e in ref[1:] if e is not None]
            pieces, pos = [], 0
            for k, m in enumerate(_R_ANY_CELL.finditer(text)):
                pieces.append(text[pos:m.start()])
                if k < len(ends):
                    col_abs, col, row_abs, row = ends[k]
                    pieces.append(m.group(1) + (_ph("col", col - c0) if across and not col_abs else m.group(2))
                                  + m.group(3) + (m.group(4) if row_abs else _ph("row", row - r0)))
                else:
                    pieces.append(m.group(0))
                pos = m.end()
            pieces.append(text[pos:])
            out.append("".join(pieces))
        elif ref[0] == "rows":
            m = _R_ROW_SPAN.fullmatch(text)
            out.append(m.group(1) + (m.group(2) if m.group(1) else _ph("row", ref[2] - r0)) + ":"
                       + m.group(3) + (m.group(4) if m.group(3) else _ph("row", ref[4] - r0)))
        elif across:
            m = _R_COL_SPAN.fullmatch(text)
            out.append(m.group(1) + (m.group(2) if m.group(1) else _ph("col", ref[2] - c0)) + ":"
                       + m.group(3) + (m.group(4) if m.group(3) else _ph("col", ref[4] - c0)))
        else:
            out.append(text)
        last = at + length
    out.append(first[last:].replace("{", "{{").replace("}", "}}"))
    return "".join(out)


_NORM_ZERO = re.compile(r"\{(row|col)[+-]0+\}")
_NORM_LEAD = re.compile(r"\{(row|col)([+-])0*([0-9]+)\}")


def check_template(template, r0, c0, c1, far=()):
    """The first cell's formula of a line over rows from r0, columns c0..c1,
    or None when the app leaves the line out (fillTemplate.ts checkTemplate):
    the template cannot be read, its first cell is not a formula, or its
    placeholders are not exactly the relative parts of its references (a
    {row} inside text in quotes, one standing for an absolute part, a {col}
    in a line one column wide, a relative reference written out). `far`: the
    workbook's defined names spelled like a cell (far_names)."""
    first = template_at(template, r0, c0)
    if first is None or not first.startswith("="):
        return None
    # {row+0} and {row} are one placeholder, {row+007} and {row+7} too.
    normal = _NORM_LEAD.sub(r"{\1\2\3}", _NORM_ZERO.sub(r"{\1}", template))
    try:
        return first if _fill_template(first, r0, c0, c1 > c0, far) == normal else None
    except _Unsure:
        return None


_FAR_SHAPED = re.compile(r"(?:[A-Za-z]{4}|[X-Zx-z][A-Za-z]{2})[0-9]+")


def far_names(doc):
    """The workbook's defined names spelled like a cell past column XFD
    (`Rate1`, `YTD2024`), in lower case: the app reads such a word as the
    name, not as a cell (editops.ts noteDefinedNames). The app also remembers
    names of workbooks it opened before; sprd.py knows only this file's."""
    names = doc.get("names")
    out = set()
    if isinstance(names, dict):
        for key in names:
            at = key.rfind("!")
            name = key[at + 1:] if 0 < at < len(key) - 1 else key  # Sheet!name
            if _FAR_SHAPED.fullmatch(name) and col_index(name.rstrip("0123456789")) > 16383:
                out.add(name.lower())
    return frozenset(out)


# -- a kept line's cells --

def _pieces_of(s, far):
    """Formula s as its text between references, and its references, each with
    the text it is written with last."""
    pieces, last = [], 0
    for at, length, ref in _scan_refs(s, far):
        if at > last:
            pieces.append(s[last:at])
        pieces.append(ref + (s[at:at + length],))
        last = at + length
    if last < len(s):
        pieces.append(s[last:])
    return pieces


def _span(a0, n0, a1, n1, name):
    """Both ends of `B:D` or `5:7` as text, the lower one first (editops.ts)."""
    if n0 < 0 or n1 < 0:
        return "#REF!"
    return f"{a0}{name(n0)}:{a1}{name(n1)}" if n0 <= n1 else f"{a1}{name(n1)}:{a0}{name(n0)}"


def _row_name(n):
    return str(n + 1)


def _column_parts(pieces, dc):
    """A formula moved dc columns right, as parts for moving it down too: text;
    an int, a relative row's number before the move down; or a rows reference,
    (written, $, row, $, row). As the app moves it: a cell reference is written
    again ($ kept, letters in capitals, no leading zeros), `B:D` only when it
    moves, a reference off the sheet as #REF!."""
    parts = []

    def put(t):
        if parts and type(parts[-1]) is str:
            parts[-1] += t
        else:
            parts.append(t)

    for p in pieces:
        if type(p) is str:
            put(p)
        elif p[0] == "cells":
            ends = (p[1],) if p[2] is None else (p[1], p[2])
            if any(row_abs and row < 0 for _, _, row_abs, row in ends):
                put("#REF!")
                continue
            for k, (col_abs, col, row_abs, row) in enumerate(ends):
                put((":" if k else "") + ("$" if col_abs else "") + col_name(col if col_abs else col + dc) + ("$" if row_abs else ""))
                if row_abs:
                    put(str(row + 1))
                else:
                    parts.append(row + 1)
        elif p[0] == "cols":
            _, a0, n0, a1, n1, written = p
            put(written if dc == 0 else _span(a0, n0 if a0 else n0 + dc, a1, n1 if a1 else n1 + dc, col_name))
        else:
            parts.append((p[5],) + p[1:5])
    return parts


def _join(parts, dr):
    out = []
    for p in parts:
        t = type(p)
        if t is str:
            out.append(p)
        elif t is int:
            out.append(str(p + dr))
        else:  # a rows reference, written as it is in the line's first row
            written, a0, n0, a1, n1 = p
            out.append(written if dr == 0 else _span(a0, n0 if a0 else n0 + dr, a1, n1 if a1 else n1 + dr, _row_name))
    return "".join(out)


def _moves_away(pieces, width, far):
    """Could moving the formula across the line spell a reference the app's
    scanner then reads otherwise (past column ZZZZ, or a defined name like
    `Rate1`)? Then each column is moved, then read again, as the app does."""
    for p in pieces:
        if type(p) is str:
            continue
        if p[0] == "cells":
            for e in p[1:3]:
                if e is not None and not e[0] and (far or e[1] + width > MAX_COL):
                    return True
        elif p[0] == "cols" and ((not p[1] and p[2] + width > MAX_COL) or (not p[3] and p[4] + width > MAX_COL)):
            return True
    return False


class _Fill:
    """A kept fill line: its rectangle, the formula of its first cell, and the
    length of its longest formula. Every other cell holds that formula moved
    as the app moves it: across to the cell's column, then down to its row."""
    __slots__ = ("r0", "c0", "r1", "c1", "first", "far", "pieces", "reread", "longest", "_cache")

    def __init__(self, r0, c0, r1, c1, first, far=()):
        self.r0, self.c0, self.r1, self.c1, self.first, self.far = r0, c0, r1, c1, first, far
        self.pieces = _pieces_of(first, far)
        self.reread = c1 > c0 and _moves_away(self.pieces, c1 - c0, far)
        self._cache = None
        # Row numbers and letters only grow, and leading zeros go after the
        # first cell, so the longest is the first, or the last column's in the
        # first or last row (written as if no reference were read otherwise:
        # never shorter than what is written).
        last = _column_parts(self.pieces, c1 - c0)
        self.longest = max(len(first), len(_join(last, 0)), len(_join(last, r1 - r0)))

    def _column(self, dc):
        cache = self._cache
        if cache is None:
            cache = self._cache = {}
        got = cache.get(dc)
        if got is None:
            if len(cache) >= 1024:
                cache.clear()
            if not self.reread:
                got = _column_parts(self.pieces, dc)
            else:  # moved across, then read again, as the app does (readFillLines, then applyFills)
                master = self.first if dc == 0 else _join(_column_parts(self.pieces, dc), 0)
                got = (master, _column_parts(_pieces_of(master, self.far), 0))
            cache[dc] = got
        return got

    def text(self, r, c):
        dr, dc = r - self.r0, c - self.c0
        if dr == 0 and dc == 0:
            return self.first
        got = self._column(dc)
        if not self.reread:
            return _join(got, dr)
        return got[0] if dr == 0 else _join(got[1], dr)


def _starting_by(t, r):
    """In a column's ranges [r0, r1, r0, r1, ...], in row order and apart: how
    many start at or above row r."""
    lo, hi = 0, len(t) >> 1
    while lo < hi:
        m = (lo + hi) >> 1
        if t[2 * m] <= r:
            lo = m + 1
        else:
            hi = m
    return lo


class _Budget:
    """What a sheet's fill lines have cost so far, counted as the app counts it
    (sprdCompact.ts FillBudget), so a line is left out exactly where the app
    leaves it out."""

    def __init__(self):
        self.cells = self.columns = self.text = self.moves = 0
        self.taken = {}  # column -> [r0, r1, r0, r1, ...] of the lines kept

    def fits(self, size, width, length):
        """Weighed before any column of the line is looked at."""
        return (self.cells + size <= MAX_FILL_CELLS and self.columns + width <= MAX_FILL_COLUMNS
                and self.text + size * length <= MAX_FILL_LINE_TEXT)

    def take(self, r0, r1, c0, c1, length):
        """Keep the line, or False when it covers a cell a line before it took
        or would move too many ranges. Its columns count either way."""
        width = c1 - c0 + 1
        self.columns += width
        taken = self.taken
        moves = 0
        # The same answer from whichever is fewer: the line's columns, or the columns taken.
        for c in (range(c0, c1 + 1) if width <= len(taken) else [k for k in taken if c0 <= k <= c1]):
            t = taken.get(c)
            if t is None:
                continue
            i = _starting_by(t, r1)
            if i > 0 and t[2 * i - 1] >= r0:
                return False
            moves += (len(t) >> 1) - i
        if self.moves + moves > MAX_FILL_MOVES:
            return False
        self.moves += moves
        for c in range(c0, c1 + 1):
            t = taken.get(c)
            if t is None:
                taken[c] = [r0, r1]
            else:
                i = _starting_by(t, r1)
                t[2 * i:2 * i] = (r0, r1)
        size = (r1 - r0 + 1) * width
        self.cells += size
        self.text += size * length
        return True


_JS_SPACE = "\t\n\x0b\x0c\r \xa0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000\ufeff"
_A1 = re.compile(r"\$?([A-Za-z]+)\$?([0-9]+)")


def _fill_cell(text):
    """One end of a fill line's range as the app reads it (coords.ts parseA1):
    $ allowed, letters in any case, leading zeros; (row, column) or None. A
    column or row past every bound is given as one past the bound."""
    m = _A1.fullmatch(text.strip(_JS_SPACE))
    if not m:
        return None
    letters, digits = m.group(1), m.group(2).lstrip("0")
    c = col_index(letters) if len(letters) <= 5 else MAX_COL + 1
    r = int(digits or "0") - 1 if len(digits) <= 9 else MAX_ROW + 1
    return None if r < 0 else (r, c)


def _fill_range(text):
    """A fill line's range as the app reads it (coords.ts parseRangeLabel):
    (r0, c0, r1, c1) or None."""
    parts = text.split(":")
    a = _fill_cell(parts[0])
    b = _fill_cell(parts[1]) if a is not None and len(parts) > 1 else a
    if b is None:
        return None
    return min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1])


def _js_length(text):
    """The length JavaScript gives a text: UTF-16 units."""
    return len(text) if text.isascii() else len(text.encode("utf-16-le", "surrogatepass")) // 2


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


def _read_fill_line(line, budget, far):
    """One fill line, read and checked in the app's order (readFillLines): its
    range, the budget, its template, then whether it covers a cell taken. The
    kept line, or None."""
    sp = line.find(" ")
    rng = _fill_range(line[:sp]) if sp > 0 else None
    if rng is None or rng[2] > MAX_ROW or rng[3] > MAX_COL:
        return None
    r0, c0, r1, c1 = rng
    template = line[sp + 1:].lstrip(" ")
    width = c1 - c0 + 1
    length = _js_length(template)
    if not budget.fits((r1 - r0 + 1) * width, width, length):
        return None
    first = check_template(template, r0, c0, c1, far)
    if first is None or not budget.take(r0, r1, c0, c1, length):
        return None
    return _Fill(r0, c0, r1, c1, first, far)


class Sheet:
    """One sheet as sprd.py reads it, without building its cells: the fill
    lines the app keeps, as rectangles, and the row lines, as text. Fill lines
    are kept or left out as the app keeps them (sprdCompact.ts readFillLines):
    a line that cannot be read, is past the sheet's bounds, is not written as
    the app writes a fill (check_template), covers a cell an earlier line
    covers, or would take the sheet's lines past one of the app's limits
    (MAX_FILL_CELLS and the three after it) is left out, and `notes` says so.
    The rows win over the fills where both give a cell.

    `complete`: the rows hold every cell (a file in the dual form, see
    rows_hold_every_cell), so the fill lines add none. They are still read,
    so a line the app would leave out is noted as it is in the app.
    `far`: the workbook's names spelled like a cell (far_names)."""

    def __init__(self, sf, complete=False, far=()):
        self.name = sheet_name(sf)
        self.notes = []
        self.fills = []
        self.left_out = 0   # fill lines left out
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
        self._keep_fills(sf.get("fills"), far)
        if complete:
            self.fills = []  # in this form the rows hold every cell: a fill line adds none
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

    def _keep_fills(self, lines, far):
        if lines is None:
            return
        if not isinstance(lines, list):
            self.notes.append("the fill lines could not be read")
            return
        budget = _Budget()
        for line in lines:
            f = _read_fill_line(line, budget, far) if isinstance(line, str) else None
            if f is None:
                self.left_out += 1
            else:
                self.fills.append(f)
        if self.left_out:
            self.notes.append(f"{self.left_out} fill line(s) left out, as Spredin leaves them out (unreadable, past its bounds, "
                              "not written as Spredin writes a fill, covering cells an earlier line covers, "
                              "or past the sheet's limits for fill lines)")

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


def sheet_cells(sf, box=None, complete=False, far=()):
    """{(r, c): text} for one sheet: the fill lines first, then the rows, which
    win where they write a cell (the app's rule); with `complete` (a file not
    in the compact form: rows_hold_every_cell), the rows alone. `far`: the
    workbook's far_names. Empty cells are left out. Refuses a sheet of more
    than MAX_LIST_CELLS cells."""
    sheet = Sheet(sf, complete, far)
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
    form = form_of(doc)
    complete = rows_hold_every_cell(doc)
    far = far_names(doc)
    out = [f"form: {form} (file version {version})" + (": the rows hold every cell, and the fill lines add none" if form == "dual" else "")]
    for i, sf in enumerate(sheet_files(doc), 1):
        sheet = Sheet(sf, complete, far)
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
    elif isinstance(doc.get("script"), str) and doc["script"].strip(_JS_SPACE):
        out.append("Python files: main.py (the old single `script`, which Spredin opens as main.py)")
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
    complete, far = rows_hold_every_cell(doc), far_names(doc)
    chosen = [Sheet(sf, complete, far) for sf in pick_sheet(doc, args.sheet)]
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


def _digits(f):
    """For f > 0: the shortest digits that read back as f, and where the point
    goes (f is 0.DIGITS times 10 to that power)."""
    mant, _, e = repr(f).partition("e")
    whole, _, frac = mant.partition(".")
    digits = whole + frac
    lead = len(digits) - len(digits.lstrip("0"))
    return digits[lead:].rstrip("0"), len(whole) + (int(e) if e else 0) - lead


def _js_string(f):
    """A float as JavaScript's String(f) writes it."""
    if f == 0:
        return "0"
    digits, n = _digits(abs(f))
    k = len(digits)
    if k <= n <= 21:
        out = digits + "0" * (n - k)
    elif 0 < n <= 21:
        out = digits[:n] + "." + digits[n:]
    elif -6 < n <= 0:
        out = "0." + "0" * -n + digits
    else:
        out = digits[0] + ("." + digits[1:] if k > 1 else "") + ("e+" if n >= 1 else "e-") + str(abs(n - 1))
    return ("-" if f < 0 else "") + out


def number_text(f):
    """A number as Spredin writes it in a cell (numparse.ts numberText): as
    JavaScript writes it, but a whole number of 16 or more digits with an
    exponent (1.234567890123456E+15), since 16 digits read as an ID, as text."""
    t = _js_string(f)
    if len(t) <= 15 or not t.isdigit():
        return t
    digits, n = _digits(f)
    return digits[0] + ("." + digits[1:] if len(digits) > 1 else "") + "E+" + str(n - 1)


def cell_text(v, where):
    if v is None:
        return ""
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    if isinstance(v, int):
        if abs(v) >= 10 ** 300:
            raise SprdError(f"{where}: the number is too large for a cell")
        # Up to 15 digits exactly; past that the number Spredin holds, written its way.
        return str(v) if abs(v) < 10 ** 15 else number_text(float(v))
    if isinstance(v, float):
        if v != v or v in (float("inf"), float("-inf")):
            raise SprdError(f"{where}: {v!r} is not a number a cell can hold")
        return number_text(v)
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
