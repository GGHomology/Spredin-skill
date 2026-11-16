"""scripts/sprd.py against files made to hurt it.

Each limit the script has is tested here against the file that would pass it:
a decompression bomb, a fill line over a whole sheet, a cell far away, text
that would steer a terminal, a cell larger than the csv module's default, and
specs and workbooks in shapes the script does not expect. The slow ones run the
script in its own process and measure its time and peak memory.
"""
import contextlib
import csv
import gzip
import importlib.util
import io
import json
import os
import random
import re
import subprocess
import sys
import tempfile
import time
import unittest
import zlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(ROOT, "skills", "spredin-pro", "scripts", "sprd.py")

spec = importlib.util.spec_from_file_location("sprd_hostile", SCRIPT)
sprd = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sprd)

# Runs sprd.py as a program and reports its own peak memory on the last line
# of stderr (ru_maxrss: bytes on macOS, kilobytes on Linux).
WRAP = (
    "import resource, runpy, sys\n"
    "sys.argv = sys.argv[1:]\n"
    "code = 0\n"
    "try:\n"
    "    runpy.run_path(sys.argv[0], run_name='__main__')\n"
    "except SystemExit as e:\n"
    "    code = e.code or 0\n"
    "r = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss\n"
    "sys.stderr.write('\\nMAXRSS %d\\n' % (r if sys.platform == 'darwin' else r * 1024))\n"
    "sys.exit(code)\n"
)
MB = 1024 * 1024
# The child's memory with nothing large in it is ~10-20 MB; a guard that
# works keeps it well under this.
SMALL_MEMORY = 300 * MB


def program(*argv, timeout=120):
    """(exit code, stdout, stderr, seconds, peak bytes) of sprd.py run as a program."""
    t = time.monotonic()
    p = subprocess.run([sys.executable, "-I", "-c", WRAP, SCRIPT, *argv], capture_output=True, text=True, timeout=timeout)
    took = time.monotonic() - t
    m = re.search(r"\nMAXRSS (\d+)\n$", p.stderr)
    return p.returncode, p.stdout, p.stderr[: m.start()] if m else p.stderr, took, int(m.group(1)) if m else -1


def run(*argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = sprd.main(list(argv))
    return code, out.getvalue(), err.getvalue()


@contextlib.contextmanager
def limit(**values):
    """Lower one of the script's limits for a test, then put it back."""
    old = {k: getattr(sprd, k) for k in values}
    for k, v in values.items():
        setattr(sprd, k, v)
    try:
        yield
    finally:
        for k, v in old.items():
            setattr(sprd, k, v)


def gzip_of_repeats(piece, count, head=b"", tail=b""):
    """A valid gzip file of head + piece * count + tail, made without
    compressing the whole: each part compressed and flushed so it stands
    alone, then the piece's bytes repeated. Small on disk, large unzipped."""
    co = zlib.compressobj(9, zlib.DEFLATED, -15)
    h = co.compress(head) + co.flush(zlib.Z_FULL_FLUSH)
    block = co.compress(piece) + co.flush(zlib.Z_FULL_FLUSH)
    t = co.compress(tail) + co.flush(zlib.Z_FINISH)
    crc = zlib.crc32(head)
    for _ in range(count):
        crc = zlib.crc32(piece, crc)
    crc = zlib.crc32(tail, crc)
    size = len(head) + len(piece) * count + len(tail)
    return (b"\x1f\x8b\x08\x00\x00\x00\x00\x00\x00\x03" + h + block * count + t
            + crc.to_bytes(4, "little") + (size & 0xFFFFFFFF).to_bytes(4, "little"))


class Folder(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.dir.cleanup()

    def path(self, name):
        return os.path.join(self.dir.name, name)

    def book(self, doc, name="book.sprd", raw=None):
        p = self.path(name)
        data = raw if raw is not None else gzip.compress(json.dumps(doc).encode("utf-8"))
        with open(p, "wb") as f:
            f.write(data)
        return p

    def assertRefused(self, code, err, words):
        self.assertEqual(code, 1, err)
        self.assertNotIn("Traceback", err)
        self.assertIn(words, err)


def sheet(name="S", **parts):
    return {"name": name, **parts}


def doc_of(*sheets, **top):
    return {"spredin": 2, "active": 0, "sheets": [sheet("Update Spredin")], "compactSheets": list(sheets), **top}


class Bombs(Folder):
    def test_the_bomb_builder_makes_a_real_gzip(self):
        data = gzip_of_repeats(b"[],", 1000, head=b'{"sheets": [', tail=b"[]]}")
        self.assertEqual(gzip.decompress(data), b'{"sheets": [' + b"[]," * 1000 + b"[]]}")
        self.assertEqual(json.loads(gzip.decompress(data))["sheets"], [[]] * 1001, "valid JSON: a guard is all that stops it")

    def test_a_decompression_bomb_is_refused_quickly_in_little_memory(self):
        # ~2 MB on disk, a valid workbook of 2 GiB and more (spaces inside its
        # sheet list): refused while unzipping, holding nothing.
        piece = b" " * MB
        bomb = gzip_of_repeats(piece, sprd.MAX_TEXT_BYTES // MB + 8, head=b'{"sheets": [', tail=b"]}")
        self.assertLess(len(bomb), 4 * MB)
        p = self.book(None, raw=bomb)
        code, out, err, took, peak = program("info", p)
        self.assertRefused(code, err, "unzips to more than 2,147,483,648 bytes")
        self.assertLess(took, 60)
        self.assertLess(peak, SMALL_MEMORY, f"peak {peak // MB} MB")

    def test_a_json_bomb_under_the_size_limit_is_refused_before_it_is_parsed(self):
        # 160 MB of "[]," (~170 KB on disk): ~56 million lists, ~4 GB in Python.
        piece = b"[]," * (MB // 3)
        bomb = gzip_of_repeats(piece, 160, head=b'{"sheets": [', tail=b"[]]}")
        p = self.book(None, raw=bomb)
        code, out, err, took, peak = program("info", p)
        self.assertRefused(code, err, "more than 50,000,000 JSON values")
        self.assertLess(took, 60)
        self.assertLess(peak, SMALL_MEMORY, f"peak {peak // MB} MB")

    def test_a_plain_file_is_measured_the_same_way(self):
        p = self.book(None, raw=b'{"sheets": [' + b"[]," * 2000 + b"[]]}")
        with limit(MAX_JSON_ITEMS=1000):
            code, _, err = run("info", p)
        self.assertRefused(code, err, "more than 1,000 JSON values")

    def test_a_file_over_the_size_limit_is_refused_unread(self):
        p = self.book(doc_of(sheet(rows={"0": "a"})))
        with limit(MAX_FILE_BYTES=10):
            code, _, err = run("info", p)
        self.assertRefused(code, err, "over 10 bytes")

    def test_only_a_regular_file_is_read(self):
        code, _, err = run("info", self.dir.name)
        self.assertRefused(code, err, "is not a file")
        if os.path.exists("/dev/zero"):
            code, _, err = run("info", "/dev/zero")
            self.assertRefused(code, err, "is not a file")


class ShapeCount(unittest.TestCase):
    """The JSON measure is an upper bound on what json.loads makes, whatever
    the text holds and wherever the pieces are cut."""

    def actual(self, value):
        if isinstance(value, dict):
            return 1 + sum(1 + self.actual(v) for v in value.values())
        if isinstance(value, list):
            return 1 + sum(self.actual(v) for v in value)
        return 1

    def measure(self, text, cut):
        s = sprd._Shape()
        data = text.encode("utf-8")
        for i in range(0, len(data), cut):
            s.feed(data[i:i + cut])
        return s.items

    def test_an_upper_bound_cut_anywhere(self):
        rnd = random.Random(7)
        nasty = ['"', "\\", "\\\\", '\\"', "[", "]", "{", "}", ",", ":", "x", "\u00e9", "{row}"]

        def value(depth):
            k = rnd.random()
            if depth > 3 or k < 0.3:
                return "".join(rnd.choice(nasty) for _ in range(rnd.randint(0, 6)))
            if k < 0.45:
                return rnd.choice([0, 1.5, -2, True, None])
            if k < 0.75:
                return [value(depth + 1) for _ in range(rnd.randint(0, 4))]
            return {"".join(rnd.choice(nasty) for _ in range(rnd.randint(0, 3))): value(depth + 1) for _ in range(rnd.randint(0, 4))}

        for _ in range(300):
            v = value(0)
            text = json.dumps(v, ensure_ascii=bool(rnd.getrandbits(1)), indent=rnd.choice([None, 1]))
            whole = self.measure(text, len(text.encode()) + 1)
            self.assertGreaterEqual(whole, self.actual(v), text)
            for cut in (1, 2, 3, 7):
                self.assertEqual(self.measure(text, cut), whole, (text, cut))

    def test_text_inside_strings_is_not_counted(self):
        # The document, then two keys and their two values.
        self.assertEqual(self.measure(json.dumps({"rows": {"0": "a,b,c,d:e[f]{" * 1000}}), 10), 1 + 2 + 2)

    def test_an_item_takes_under_90_bytes_parsed(self):
        # What MAX_JSON_ITEMS means in memory: the dearest short shapes
        # (Python 3.9's dicts ~84 bytes an item, 3.14's ~50; lists ~70).
        import resource
        for shape in ("{}", "[]", "1.5", '"ab"', '{"k":0}', "12345678901234567890", "[[1]]"):
            with self.subTest(shape):
                code = ("import json, resource, sys\n"
                        f"text = '[' + ','.join([{shape!r}] * 2_000_000) + ']'\n"
                        "base = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss\n"
                        "doc = json.loads(text)\n"
                        "print(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss - base)\n")
                grew = int(subprocess.run([sys.executable, "-I", "-c", code], capture_output=True, text=True, check=True).stdout)
                grew = grew if sys.platform == "darwin" else grew * 1024
                items = self.measure("[" + ",".join([shape] * 2_000_000) + "]", 1 << 20)
                self.assertLess(grew / items, 90, f"{grew / items:.1f} bytes an item")


class Fills(Folder):
    def test_the_reviewers_95_byte_file_is_read_at_once(self):
        # One fill line over A1:ZZZZ16777215 used to expand without end.
        p = self.book(doc_of(sheet(fills=["A1:ZZZZ16777215 =1"])))
        code, out, err, took, peak = program("info", p)
        self.assertEqual(code, 0, err)
        self.assertIn("0 cells", out)
        self.assertIn("1 fill line(s) left out", out)
        self.assertLess(took, 10)
        self.assertLess(peak, SMALL_MEMORY)
        code, out, err, took, peak = program("read", p, "--format", "csv")
        self.assertEqual((code, out), (0, ""))
        self.assertIn("left out", err)

    def test_the_sheets_fill_lines_stop_at_the_apps_bound(self):
        # Two lines of 15 million: the second would pass 20 million, as in the app.
        p = self.book(doc_of(sheet(fills=["A1:A15000000 =B{row}", "C1:C15000000 =D{row}", "E1:E3 =F{row}"])))
        code, out, err = run("info", p)
        self.assertEqual(code, 0, err)
        self.assertIn("15000003 cells, 15000003 formulas", out)
        self.assertIn("1 fill line(s) left out", out)
        code, out, _ = run("read", p, "--range", "C1:F3", "--format", "json")
        self.assertEqual(json.loads(out), {"S": {"E1": "=F1", "E2": "=F2", "E3": "=F3"}})

    def test_a_huge_fill_listed_whole_is_refused_quickly(self):
        # 19.9 million a sheet (two columns, under the app's row bound), three sheets.
        sheets = [sheet(f"S{i}", fills=["A1:B9950000 =C{row}*2"]) for i in range(3)]
        p = self.book(doc_of(*sheets))
        code, out, err, took, peak = program("read", p, "--format", "json")
        self.assertRefused(code, err, "more than 50,000,000 cells")
        self.assertEqual(out, "")
        self.assertLess(took, 10)
        self.assertLess(peak, SMALL_MEMORY)
        # ... and the screen's first 500 of each sheet are still there at once.
        code, out, err, took, peak = program("read", p)
        self.assertEqual(code, 0, err)
        self.assertIn("# sheet S2: 19900000 cells", out)
        self.assertIn("B250\t=C250*2\n# ... 19899500 more", out)
        self.assertLess(took, 10)

    def test_a_small_range_of_a_huge_fill_is_cheap_and_right(self):
        # 15 million down column A, and 4.75 million across B1:ZZZZ10: under the app's 20 million.
        p = self.book(doc_of(sheet(fills=["A1:A15000000 =B{row}*2", "B1:ZZZZ10 ={col}{row-0}+$A$1"], rows={"9999999": ",x"})))
        code, out, err, took, peak = program("read", p, "--range", "A9999998:C10000001", "--format", "json")
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(out), {"S": {
            "A9999998": "=B9999998*2", "A9999999": "=B9999999*2", "A10000000": "=B10000000*2",
            "B10000000": "x", "A10000001": "=B10000001*2"}})
        self.assertNotIn("left out", err)
        code, out, err, took, peak = program("read", p, "--range", "ZZZY9:ZZZZ11", "--format", "csv")
        self.assertEqual(out.splitlines(), ["=ZZZY9+$A$1,=ZZZZ9+$A$1", "=ZZZY10+$A$1,=ZZZZ10+$A$1"])
        self.assertLess(took, 10)
        self.assertLess(peak, SMALL_MEMORY)

    def test_fill_formulas_are_measured_before_they_are_written(self):
        long = "=" + "+".join(f"B{{row}}*{i}" for i in range(40))  # ~400 characters a cell
        p = self.book(doc_of(sheet(fills=[f"A1:B9950000 {long}"])))
        code, out, err, took, peak = program("read", p, "--format", "cells", "--max", "0", "--out", self.path("out.txt"))
        self.assertRefused(code, err, "more than 2,147,483,648 characters of formulas")
        self.assertFalse(os.path.exists(self.path("out.txt")))
        self.assertLess(took, 10)

    def test_the_fill_text_limit_counts_what_would_be_written(self):
        p = self.book(doc_of(sheet(fills=["A1:A20 =B{row}*1234567"])))  # 12-13 characters a cell
        with limit(MAX_FILL_TEXT=200):
            self.assertRefused(*run("read", p, "--format", "json")[::2], "characters of formulas")
            self.assertEqual(run("read", p, "--format", "json", "--range", "A1:A10")[0], 0)
            self.assertEqual(run("read", p, "--max", "10")[0], 0, "the screen's first ten only")

    def test_fill_lines_in_too_many_pieces_are_refused_quickly(self):
        # A cell in every column of row 1 and one at ZZZZ2; then lines A2:ZZZZ2
        # that each clash only at their far end, over and over.
        lines = [f"{sprd.col_name(c)}1:{sprd.col_name(c)}1 =1" for c in range(0, sprd.MAX_COL + 1)]
        lines.append("ZZZZ2:ZZZZ2 =1")
        lines += ["A2:ZZZZ2 =1"] * 1000
        p = self.book(doc_of(sheet(fills=lines)))
        code, out, err, took, peak = program("info", p)
        self.assertRefused(code, err, "too many pieces")
        self.assertLess(took, 30)


class Output(Folder):
    def test_a_far_away_cell_is_not_printed_as_a_csv(self):
        p = self.book(doc_of(sheet(rows={"0": "a", "99999999": "x"})))
        out = self.path("out.csv")
        code, stdout, err, took, peak = program("read", p, "--format", "csv", "--out", out)
        self.assertRefused(code, err, "A1:A100000000, 100,000,000 cells")
        self.assertIn("--range", err)
        self.assertFalse(os.path.exists(out))
        self.assertEqual(os.listdir(self.dir.name), ["book.sprd"], "no temporary file left behind")
        self.assertLess(took, 10)
        code, stdout, err = run("read", p, "--format", "csv")
        self.assertRefused(code, err, "100,000,000 cells")
        self.assertEqual(stdout, "")
        # The cells that hold something are still there, and a range of the CSV.
        code, stdout, err = run("read", p, "--format", "cells")
        self.assertEqual(stdout.splitlines(), ["# sheet S: 2 cells", "A1\ta", "A100000000\tx"])
        code, stdout, err = run("read", p, "--format", "csv", "--range", "A99999999:B100000000")
        self.assertEqual(stdout.splitlines(), ['""', "x"])

    def test_the_print_limit_counts_every_sheet(self):
        p = self.book(doc_of(sheet("A", rows={"0": "a", "59": "b"}), sheet("B", rows={"0": "a", "59": "b"})))
        with limit(MAX_PRINT_CELLS=100):
            code, _, err = run("read", p, "--format", "csv")
            self.assertRefused(code, err, "sheet 'B'")
            self.assertEqual(run("read", p, "--format", "csv", "--sheet", "A")[0], 0)

    def test_list_limit(self):
        p = self.book(doc_of(sheet(rows={str(r): "1,2" for r in range(60)})))
        with limit(MAX_LIST_CELLS=100):
            self.assertRefused(*run("read", p, "--format", "json")[::2], "more than 100 cells")
            self.assertRefused(*run("read", p, "--max", "0")[::2], "more than 100 cells")
            self.assertEqual(run("read", p, "--max", "50")[0], 0, "50 is under the limit")
            with self.assertRaises(sprd.SprdError):
                sprd.sheet_cells(sprd.sheet_files(sprd.load(p))[0])


# Every kind of character that must never reach the screen as itself.
HIDDEN = {
    "escape (C0)": "\x1b", "bell": "\x07", "delete": "\x7f", "C1 next line": "\x85", "C1 CSI": "\x9b",
    "zero width space": "\u200b", "left-to-right mark": "\u200e", "right-to-left mark": "\u200f",
    "right-to-left override": "\u202e", "left-to-right embedding": "\u202a", "isolate": "\u2066",
    "pop isolate": "\u2069", "byte order mark": "\ufeff", "line separator": "\u2028", "soft hyphen": "\u00ad",
    "tag character": "\U000e0041", "lone surrogate": "\ud800", "Arabic letter mark": "\u061c",
    "Mongolian vowel separator": "\u180e", "word joiner": "\u2060", "invisible times": "\u2062",
    "old format character": "\u206a", "interlinear annotation": "\ufff9", "paragraph separator": "\u2029",
    "pop directional formatting": "\u202c", "zero width joiner": "\u200d", "cancel tag": "\U000e007f",
}
# Written out here, not taken from the script: SECURITY.md's list, as a test.
VISIBLE = re.compile("[^\x00-\x08\x0b-\x1f\x7f-\x9f\u00ad\u061c\u180e\u200b-\u200f\u2028-\u202e"
                     "\u2060-\u2064\u2066-\u206f\ufeff\ufff9-\ufffb\ud800-\udfff\U000e0000-\U000e007f]*")


class WritesNeverOverAFile(Folder):
    def test_a_file_that_appears_while_writing_is_left_alone(self):
        target = self.path("out.txt")

        def fill(f):
            f.write("mine")
            with open(target, "w") as other:  # someone else takes the name meanwhile
                other.write("theirs")

        with self.assertRaises(sprd.SprdError):
            sprd._write_out(target, False, fill, text=True)
        with open(target) as f:
            self.assertEqual(f.read(), "theirs")
        self.assertEqual(os.listdir(self.dir.name), ["out.txt"], "no temporary file left behind")

    def test_replace_writes_over_it(self):
        target = self.path("out.txt")
        with open(target, "w") as f:
            f.write("old")
        sprd._write_out(target, True, lambda f: f.write("new"), text=True)
        with open(target) as f:
            self.assertEqual(f.read(), "new")
        self.assertEqual(os.listdir(self.dir.name), ["out.txt"])


class Escapes(Folder):
    def setUp(self):
        super().setUp()
        cells = ",".join('"' + ("x" + v + "y").replace('"', '""') + '"' for v in HIDDEN.values())
        doc = doc_of(sheet("Bad\u202ename\x1b", rows={"0": cells}),
                     names={"N\u200bame": "Sheet1!\u202e$A$1"},
                     scripts=[{"name": "ev\u202eil.py\x1b]0;", "code": ""}])
        # ensure_ascii writes the lone surrogate as an escape the file can hold.
        self.p = self.book(None, raw=gzip.compress(json.dumps(doc, ensure_ascii=True).encode("ascii")))

    def assertAllShown(self, text):
        self.assertTrue(VISIBLE.fullmatch(text), [ch for ch in text if not VISIBLE.fullmatch(ch)])

    def test_info_shows_every_hidden_character(self):
        code, out, err = run("info", self.p)
        self.assertEqual(code, 0, err)
        self.assertAllShown(out)
        self.assertIn("'Bad\\u{202E}name\\u{001B}'", out)
        self.assertIn("N\\u{200B}ame = Sheet1!\\u{202E}$A$1", out)
        self.assertIn("ev\\u{202E}il.py\\u{001B}]0;", out)

    def test_each_kind_in_the_cells_format(self):
        code, out, err = run("read", self.p)
        self.assertEqual(code, 0, err)
        self.assertAllShown(out)
        for what, ch in HIDDEN.items():
            with self.subTest(what):
                self.assertIn("x\\u{%04X}y" % ord(ch), out)

    def test_the_screen_csv_shows_them_and_a_file_keeps_them(self):
        code, out, err = run("read", self.p, "--format", "csv")
        self.assertEqual(code, 0, err)
        self.assertAllShown(out)
        self.assertIn("x\\u{202E}y", out)
        f = self.path("out.csv")
        self.assertEqual(run("read", self.p, "--format", "csv", "--out", f)[0], 0)
        with open(f, encoding="utf-8") as h:
            got = h.read()
        self.assertIn("x\u202ey", got, "a data file holds the text exactly")
        self.assertIn("x\\u{D800}y", got, "a lone surrogate, which UTF-8 cannot hold, is shown")

    def test_json_escapes_them_and_keeps_the_text(self):
        code, out, err = run("read", self.p, "--format", "json")
        self.assertEqual(code, 0, err)
        self.assertAllShown(out)
        got = json.loads(out)
        self.assertEqual(list(got), ["Bad\u202ename\x1b"])
        self.assertEqual(sorted(got["Bad\u202ename\x1b"].values()), sorted("x" + v + "y" for v in HIDDEN.values()))

    def test_notes_and_refusals_show_them_too(self):
        code, out, err = run("read", self.p, "--sheet", "nope\x1b[2J")
        self.assertEqual(code, 1)
        self.assertAllShown(err)
        self.assertIn("the sheets are 'Bad\\u{202E}name\\u{001B}'", err)
        self.assertIn("no sheet 'nope\\u{001B}[2J'", err)

    def test_backslashes_stay_apart_from_escapes(self):
        self.assertEqual(sprd.show("a\\u{202E}b\u202e"), "a\\\\u{202E}b\\u{202E}")
        self.assertEqual(sprd.show("tab\there\nand\r"), "tab\\there\\nand\\r")
        self.assertEqual(sprd.show("plain = A1*2"), "plain = A1*2")
        self.assertEqual(sprd.show("caf\u00e9 \u4e2d"), "caf\u00e9 \u4e2d", "letters of any script are shown as they are")


class LongCells(Folder):
    def test_a_cell_of_200000_characters(self):
        big = "a" * 100_000 + ",b\"c\n" + "z" * 100_000
        cells = '"' + big.replace('"', '""') + '",after'
        p = self.book(doc_of(sheet(rows={"0": cells})))
        code, out, err = run("read", p, "--format", "json")
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(out), {"S": {"A1": big, "B1": "after"}})
        code, out, err = run("read", p)
        self.assertEqual(code, 0, err)
        self.assertIn("A1\t" + sprd.show(big) + "\n", out)
        f = self.path("o.csv")
        self.assertEqual(run("read", p, "--format", "csv", "--out", f)[0], 0)
        with open(f, encoding="utf-8", newline="") as h:
            self.assertEqual(next(csv.reader(h)), [big, "after"])

    def test_a_cell_past_the_limit_is_refused_with_a_message(self):
        p = self.book(doc_of(sheet(rows={"0": "a" * (sprd.MAX_FIELD_CHARS + 1)})))
        code, _, err = run("info", p)
        self.assertRefused(code, err, "more than 67,108,864 characters")

    def test_a_row_of_too_many_cells_is_left_out(self):
        p = self.book(doc_of(sheet(rows={"0": "1," * 1_100_000, "1": "kept", "2": '"' + "," * 2_000_000 + '",ok'})))
        code, out, err = run("read", p, "--format", "json")
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(out), {"S": {"A2": "kept", "A3": "," * 2_000_000, "B3": "ok"}})
        self.assertIn("1 row(s) could not be read", err)


class Malformed(Folder):
    def spec(self, data, raw=None):
        p = self.path("spec.json")
        with open(p, "wb") as f:
            f.write(raw if raw is not None else json.dumps(data).encode("utf-8"))
        return p

    def check(self, err, out_path=None):
        self.assertNotIn("Traceback", err)
        self.assertTrue(err.startswith("sprd.py: "), err)
        self.assertEqual(err.count("\n"), 1, "one line")
        self.assertLess(len(err), 400)

    def test_specs(self):
        bad = [
            ({"sheets": [{"name": "A", "at": 5}]}, "not a cell address"),
            ({"sheets": [{"name": "A", "at": "B"}]}, "not a cell address"),
            ({"sheets": [{"name": "A", "cells": [1, 2]}]}, "cells is an object"),
            ({"sheets": [{"name": "A", "cells": {"A1": [1]}}]}, "not a cell value"),
            ({"sheets": [{"name": "A", "rows": "abc"}]}, "rows is a list"),
            ({"sheets": [{"name": "A", "rows": [["x", ["nested"]]]}]}, "not a cell value"),
            ({"sheets": [{"name": "A", "rows": [[10 ** 400]]}]}, "too large"),
            ({"sheets": [{"name": "A", "formats": ["A1"]}]}, "formats is an object"),
            ({"sheets": [{"name": "A", "formats": {"A1:ZZZZ999999999": "0.0"}}]}, "too many formatted cells"),
            ({"sheets": [{"name": "A", "formats": {"nope": "0.0"}}]}, "not a cell address"),
            ({"sheets": [{"name": "A", "widths": {"A": "wide"}}]}, "width of column A"),
            ({"sheets": [{"name": "A", "widths": {"1": 40}}]}, "not a column letter"),
            ({"sheets": [{"name": "A", "widths": [40]}]}, "widths is an object"),
            ({"sheets": [{"name": "A", "freeze": "yes"}]}, "freeze is an object"),
            ({"sheets": [{"name": "A", "freeze": {"rows": -1}}]}, "freeze rows"),
            ({"sheets": [{"name": "A", "freeze": {"rows": "1"}}]}, "freeze rows"),
            ({"sheets": [{"name": "A"}], "names": ["Rate"]}, "names is an object"),
            ({"sheets": [{"name": "A"}], "names": {"Rate": 5}}, "its target is text"),
            ({"sheets": [{"name": "A\u202eB"}]}, "control characters"),
            ({"sheets": [{"name": "A", "cells": {"A1": 1}, "rows": [[None] * 10, [1] * 3]}], "extra": {"deep": [[[[]]]]}}, None),
            (["not", "an", "object"], "the spec needs"),
            ({"sheets": {"name": "A"}}, "the spec needs"),
            ({"sheets": [None]}, "is not an object"),
        ]
        for data, words in bad:
            with self.subTest(words=words, data=str(data)[:60]):
                code, _, err = run("write", self.spec(data), self.path("o.sprd"))
                if words is None:
                    self.assertEqual(code, 0, err)
                    os.unlink(self.path("o.sprd"))
                    continue
                self.assertEqual(code, 1)
                self.check(err)
                self.assertIn(words, err)
                self.assertFalse(os.path.exists(self.path("o.sprd")))

    def test_spec_files_that_are_not_json(self):
        for raw, words in ((b"[" * 200_000 + b"]" * 200_000, "nested too deeply"),
                           (b"\xff\xfe junk", "not UTF-8"),
                           (b"{nope", "not JSON")):
            with self.subTest(words=words):
                code, _, err = run("write", self.spec(None, raw), self.path("o.sprd"))
                self.assertEqual(code, 1)
                self.check(err)
                self.assertIn(words, err)

    def test_workbooks(self):
        deep = b'{"sheets":[' + b"[" * 200_000 + b"]" * 200_000 + b"]}"
        cases = [
            (deep, "not a .sprd workbook (the JSON is nested too deeply)"),
            (gzip.compress(b'{"sheets": [1, 2]}')[:-12], "damaged or cut short"),
            (gzip.compress(b'{"sheets": []}') + b"garbage", "damaged or cut short"),
            (b"\x1f\x8bnot really gzip", "damaged or cut short"),
            (b"\xff\xfe\x00{", "not UTF-8"),
            (b'{"sheets": 5}', "no sheets"),
            (b"[1, 2]", "no sheets"),
            (b'{"sheets": [{"name": "A", "rows": {"0": "a"}}], "x": 1e999999}', None),
        ]
        for raw, words in cases:
            with self.subTest(words=words):
                p = self.book(None, raw=raw)
                for argv in (["info", p], ["read", p, "--format", "json"]):
                    code, _, err = run(*argv)
                    if words is None:
                        self.assertEqual(code, 0, err)
                        continue
                    self.assertEqual(code, 1)
                    self.check(err)
                    self.assertIn(words, err)

    def test_odd_shapes_inside_a_workbook_are_read_around(self):
        doc = {"spredin": [[["deep"]]], "names": ["not", "a", "map"], "scripts": {"name": "x"}, "sheets": [
            "not a sheet",
            {"name": 7, "rows": ["list", "not", "map"], "fills": {"A1:A3": "=1"}, "charts": 3, "merges": True},
            {"name": "B", "rows": {"\u0661": "arabic digit", "0" * 5000: "long", "-1": "neg", "2": 5, "3": "ok"}},
            {"name": "C", "cells": {"0:0": "a", "1:x": "b", "9" * 20 + ":0": "c", "2:2": ["d"]}},
            {"name": "D", "fills": ["A1:A3", "A1:A3 x", "A0:A3 =1", "A1:A3 ={rows}", "A1:A3 =A{row-1}", 5, "B1:B3 =1"]},
        ]}
        p = self.book(doc)
        code, out, err = run("info", p)
        self.assertEqual(code, 0, err)
        self.assertIn("form: dual (file version ?)", out)
        self.assertIn("sheet 1: '' - 0 cells, 0 formulas, 1 fill lines, 1 charts, 1 merges, the fill lines could not be read, the rows could not be read", out)
        self.assertIn("sheet 2: 'B' A1:A4 - 1 cells", out)
        self.assertIn("4 row(s) could not be read", out)
        self.assertIn("sheet 3: 'C' A1:A1 - 1 cells", out)
        self.assertIn("3 cell(s) of the old cell map could not be read", out)
        self.assertIn("sheet 4: 'D' A1:B3 - 3 cells, 3 formulas", out)
        self.assertIn("6 fill line(s) left out", out)
        code, out, err = run("read", p, "--format", "json")
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(out), {"": {}, "B": {"A4": "ok"}, "C": {"A1": "a"}, "D": {"B1": "=1", "B2": "=1", "B3": "=1"}})

    def test_the_backstop_says_one_line_and_nothing_of_the_file(self):
        def boom(_args):
            raise TypeError("secret cell text 12345")
        old = sprd.cmd_info
        try:
            sprd.cmd_info = boom
            code, _, err = run("info", "whatever.sprd")
        finally:
            sprd.cmd_info = old
        self.assertEqual(code, 1)
        self.check(err)
        self.assertIn("not in a shape sprd.py can read (TypeError)", err)
        self.assertNotIn("secret", err)

    def test_max_is_not_negative(self):
        p = self.book(doc_of(sheet(rows={"0": "a"})))
        self.assertRefused(*run("read", p, "--max", "-1")[::2], "--max")


if __name__ == "__main__":
    unittest.main()
