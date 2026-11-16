"""scripts/sprd.py against workbooks written by Spredin itself.

The fixtures are made by tools/app-check.mts with the app's own writer, in each
form it writes; expected.json is every cell as the app's own reader reads them
back. The same tool checks that the app reads what `sprd.py write` makes.
"""
import contextlib
import gzip
import importlib.util
import io
import json
import os
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIX = os.path.join(ROOT, "tests", "fixtures")
SCRIPT = os.path.join(ROOT, "skills", "spredin-pro", "scripts", "sprd.py")

spec = importlib.util.spec_from_file_location("sprd", SCRIPT)
sprd = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sprd)


def run(*argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = sprd.main(list(argv))
    return code, out.getvalue(), err.getvalue()


def cells_by_label(sf, complete=False):
    return {sprd.label(r, c): v for (r, c), v in sprd.sheet_cells(sf, complete=complete).items()}


class ReadsWhatTheAppWrites(unittest.TestCase):
    def test_every_form_reads_as_the_app_reads_it(self):
        with open(os.path.join(FIX, "expected.json"), encoding="utf-8") as f:
            expected = json.load(f)
        self.assertEqual(set(expected), {"compact.sprd", "dual.sprd", "full.sprd", "plain-bom.sprd"})
        for name, want in expected.items():
            doc = sprd.load(os.path.join(FIX, name))
            complete = sprd.rows_hold_every_cell(doc)
            got = {sf["name"]: cells_by_label(sf, complete) for sf in sprd.sheet_files(doc)}
            self.assertEqual(got, want["sheets"], name)
            self.assertEqual(doc.get("names", {}), want["names"], name)

    def test_the_forms_are_what_they_say(self):
        forms = {n: sprd.form_of(sprd.load(os.path.join(FIX, n))) for n in ("compact.sprd", "dual.sprd", "full.sprd", "plain-bom.sprd")}
        self.assertEqual(forms, {"compact.sprd": "compact", "dual.sprd": "dual", "full.sprd": "full", "plain-bom.sprd": "full"})

    def test_fixtures_are_read_with_the_rule_for_their_form(self):
        # sheet_cells without `complete` reads fill lines as a compact file's;
        # the dual fixture is the same either way only because the app wrote it.
        self.assertTrue(sprd.rows_hold_every_cell(sprd.load(os.path.join(FIX, "dual.sprd"))))
        self.assertFalse(sprd.rows_hold_every_cell(sprd.load(os.path.join(FIX, "compact.sprd"))))

    def test_the_compact_stub_is_not_read_as_a_sheet(self):
        doc = sprd.load(os.path.join(FIX, "compact.sprd"))
        self.assertEqual([s["name"] for s in sprd.sheet_files(doc)], ["Sales", "Notes, 2026"])
        self.assertEqual([s["name"] for s in doc["sheets"]], ["Update Spredin"])


with open(os.path.join(FIX, "rules.json"), encoding="utf-8") as _f:
    RULES = json.load(_f)  # written by tools/app-check.mts: what the APP reads


def read_doc(doc):
    """{sheet name: {label: text}} as sprd.py reads a whole workbook."""
    complete = sprd.rows_hold_every_cell(doc)
    return {sf["name"]: {sprd.label(r, c): v for (r, c), v in sprd.sheet_cells(sf, complete=complete).items()}
            for sf in sprd.sheet_files(doc)}


class TheDualForm(unittest.TestCase):
    """A file read from `sheets` with fill lines beside its rows: the rows hold
    every cell, and a fill line may confirm a cell but never adds one."""

    def test_reads_as_the_app_reads(self):
        self.assertEqual(len(RULES["dual"]), 4)
        for case in RULES["dual"]:
            with self.subTest(doc=json.dumps(case["doc"])[:80]):
                self.assertEqual(sprd.form_of(case["doc"]), case["form"])
                self.assertEqual(read_doc(case["doc"])["S"], case["cells"])

    def test_a_cell_the_rows_leave_empty_stays_empty(self):
        doc = {"spredin": 1, "sheets": [{"name": "S", "rows": {"0": "1", "1": "=A1+1"}, "fills": ["A2:A3 =A{row-1}+1"]}]}
        self.assertEqual(read_doc(doc)["S"], {"A1": "1", "A2": "=A1+1"}, "A3 is empty, as in Spredin")
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "dual.sprd")
            with open(p, "wb") as f:
                f.write(gzip.compress(json.dumps(doc).encode("utf-8")))
            code, out, err = run("info", p)
            self.assertEqual(code, 0, err)
            self.assertIn("form: dual (file version 1): the rows hold every cell, and the fill lines add none", out)
            self.assertIn("sheet 1: 'S' A1:A2 - 2 cells, 1 formulas, 1 fill lines", out)
            code, out, err = run("read", p, "--format", "json")
            self.assertEqual(json.loads(out), {"S": {"A1": "1", "A2": "=A1+1"}})


@contextlib.contextmanager
def limits(**values):
    """Lower sprd.py's limits for a test, then put them back."""
    old = {k: getattr(sprd, k) for k in values}
    for k, v in values.items():
        setattr(sprd, k, v)
    try:
        yield
    finally:
        for k, v in old.items():
            setattr(sprd, k, v)


class FillLinesAsTheAppReadsThem(unittest.TestCase):
    """Each case is a sheet of a compact file and what the APP reads from it
    (tools/app-check.mts): which lines it keeps (its writer's template, and
    nothing else) and the text of every cell (the first formula moved, as the
    fill handle moves it, which spells references in capitals)."""

    def test_every_case(self):
        self.assertGreaterEqual(len(RULES["fills"]), 40)
        for case in RULES["fills"]:
            with self.subTest(case["name"]):
                far = sprd.far_names({"names": case.get("names", {})})
                sheet = sprd.Sheet({"name": case["name"], "fills": case["fills"], "rows": case.get("rows", {})}, far=far)
                self.assertEqual(sheet.left_out, case["leftOut"], "lines left out")
                self.assertEqual({sprd.label(r, c): t for r, c, t in sheet.cells()}, case["cells"])
                self.assertEqual(sheet.stats()["cells"], len(case["cells"]))

    def test_the_cases_the_audit_named(self):
        check = sprd.check_template
        self.assertIsNone(check('="Row {row}"', 0, 0, 0), "a placeholder inside quoted text")
        self.assertIsNone(check("=$B${row}", 1, 0, 0), "a placeholder for an absolute part")
        self.assertIsNone(check("={col}1*2", 1, 1, 1), "{col} in a line one column wide")
        self.assertIsNone(check("x{row}", 0, 0, 0), "a first cell that is not a formula")
        self.assertIsNone(check("=B5", 0, 0, 0), "a relative reference written out")
        self.assertEqual(check("=C{row}*D{row}", 1, 4, 4), "=C2*D2")
        self.assertEqual(check("={col-2}{row}*$D$1", 1, 4, 6), "=C2*$D$1")
        self.assertIsNone(check("={col-2}{row}*D$1", 1, 4, 6), "D is a relative column: {col-1} in a block")

    def test_a_number_the_app_may_not_hold_exactly_is_left_out(self):
        # Past 2^52 a JavaScript number may round; sprd.py does not guess.
        self.assertEqual(sprd.check_template("=A{row+1000000000000000}", 0, 0, 0), "=A1000000000000001")
        self.assertIsNone(sprd.check_template("=A{row+10000000000000000}", 0, 0, 0))
        self.assertIsNone(sprd.check_template("=$A$99999999999999999+B{row}", 0, 0, 0))

    def test_the_four_limits_as_the_app_counts_them(self):
        for case in RULES["limits"]:
            lim = case["limits"]
            with self.subTest(case["why"]), limits(MAX_FILL_CELLS=lim["cells"], MAX_FILL_COLUMNS=lim["columns"],
                                                   MAX_FILL_LINE_TEXT=lim["text"], MAX_FILL_MOVES=lim["moves"]):
                sheet = sprd.Sheet({"name": "S", "fills": case["lines"]})
                kept = [[c, f.r0, f.r1, f.text(f.r0, c)] for f in sheet.fills for c in range(f.c0, f.c1 + 1)]
                self.assertEqual(kept, case["kept"])
                self.assertEqual(sheet.left_out, case["leftOut"])

    def test_the_app_limits_are_the_apps(self):
        self.assertEqual((sprd.MAX_FILL_CELLS, sprd.MAX_FILL_COLUMNS, sprd.MAX_FILL_LINE_TEXT, sprd.MAX_FILL_MOVES),
                         (20_000_000, 20_000_000 // 3, 2 ** 31 - 1, 2 ** 31))


class Templates(unittest.TestCase):
    def test_placeholders(self):
        t = sprd.template_at
        self.assertEqual(t("=C{row}*D{row}", 1, 4), "=C2*D2")
        self.assertEqual(t("=F{row-1}+1", 9, 5), "=F9+1")
        self.assertEqual(t("={col-5}{row}*2", 3, 7), "=C4*2")
        self.assertEqual(t('="{{"&A{row}&"}}"', 2, 4), '="{"&A3&"}"')
        self.assertEqual(t("=$B$1*2", 50, 0), "=$B$1*2")

    def test_unreadable_templates(self):
        t = sprd.template_at
        self.assertIsNone(t("=A{row-1}", 0, 0), "a row above row 1")
        self.assertIsNone(t("={col-1}1", 0, 0), "a column left of A")
        self.assertIsNone(t("=A{rows}", 3, 0), "an unknown placeholder")
        self.assertIsNone(t("=A1}", 3, 0), "a lone brace")

    def test_rows_win_over_fills(self):
        sf = {"name": "S", "fills": ["A1:A3 =B{row}"], "rows": {"1": "kept"}}
        self.assertEqual(cells_by_label(sf), {"A1": "=B1", "A2": "kept", "A3": "=B3"})

    def test_legacy_cell_map(self):
        sf = {"name": "S", "cells": {"0:0": "a", "2:1": "=A1", "x": "skip", "1:1": ""}}
        self.assertEqual(cells_by_label(sf), {"A1": "a", "B3": "=A1"})


class KeepsFillLinesAsTheAppDoes(unittest.TestCase):
    def test_a_line_over_cells_an_earlier_line_covers_is_left_out(self):
        sf = {"name": "S", "fills": ["A1:A3 =B{row}", "A2:A5 =C{row}", "B1:B2 =D{row}"]}
        self.assertEqual(cells_by_label(sf), {"A1": "=B1", "A2": "=B2", "A3": "=B3", "B1": "=D1", "B2": "=D2"})

    def test_a_line_past_the_apps_bounds_is_left_out(self):
        # Row 16,777,217 is one past the app's bound for a fill line (16,777,215 from 0).
        self.assertEqual(cells_by_label({"name": "S", "fills": ["A16777215:A16777217 =1", "B1:B2 =2"]}), {"B1": "=2", "B2": "=2"})
        self.assertEqual(len(sprd.Sheet({"name": "S", "fills": ["A16777215:A16777216 =1"]}).fills), 1, "the last row is in")

    def test_a_line_whose_first_cell_is_not_a_formula_is_left_out(self):
        self.assertEqual(cells_by_label({"name": "S", "fills": ["A1:A3 x{row}", "B1:B2 =1"]}), {"B1": "=1", "B2": "=1"})

    def test_the_notes_say_what_was_left_out(self):
        sheet = sprd.Sheet({"name": "S", "fills": ["A1:A3 =1", "A1:A2 =2", "C1:C2 nope"], "rows": {"x": "a"}})
        self.assertEqual(len(sheet.notes), 2)
        self.assertIn("2 fill line(s) left out", sheet.notes[0])
        self.assertIn("1 row(s) could not be read", sheet.notes[1])


def reference(sf, box):
    """The cells as a plain model reads them: every kept fill line written out
    cell by cell (the app's keep rules, with a set of the cells taken), then the
    rows over them, then the box. Whether a template is one the app keeps is
    check_template's (tested on its own against the app, AppRules); the
    templates here are spelled as the app spells moved formulas, so reading
    the template at each cell is what the app's moved formula is."""
    import csv as _csv
    cells, taken, total, fills = {}, set(), 0, {}
    for line in sf.get("fills", []):
        rng, _, template = line.partition(" ")
        try:
            r0, c0, r1, c1 = sprd.parse_range(rng)
        except sprd.SprdError:
            continue
        first = sprd.check_template(template.lstrip(" "), r0, c0, c1)
        rect = {(r, c) for r in range(r0, r1 + 1) for c in range(c0, c1 + 1)}
        if first is None or rect & taken or total + len(rect) > sprd.MAX_FILL_CELLS:
            continue
        total += len(rect)
        taken |= rect
        longest = len(sprd.template_at(template.lstrip(" "), r1, c1))
        for r, c in rect:
            cells[(r, c)] = sprd.template_at(template.lstrip(" "), r, c)
            fills[(r, c)] = longest
    for key, line in sf.get("rows", {}).items():
        for c, t in enumerate(next(_csv.reader(io.StringIO(line, newline=""), strict=False), [])):
            if t != "":
                cells[(int(key), c)] = t
                fills.pop((int(key), c), None)
    inside = lambda k: box is None or (box[0] <= k[0] <= box[2] and box[1] <= k[1] <= box[3])
    return {k: v for k, v in cells.items() if inside(k)}, {k: v for k, v in fills.items() if inside(k)}


class ReadsLikeTheReference(unittest.TestCase):
    """Fill lines are never written out to be read: they are kept as rectangles,
    swept row by row and counted. This checks the sweep, and the counts, against
    the plain model on random sheets and random ranges."""

    def test_random_sheets(self):
        import random
        rnd = random.Random(2026)
        templates = ["=A{row}", "={col}{row-1}*2", "=$B$1", "={col}{row}&\"{{x}}\"", "=X{row+3}", "x{row}", "={rows}",
                     "=A{row-40}", "=$A{row}*{col}$1", "=SUM($B$1:B{row})", "=A5"]
        for case in range(400):
            fills = []
            for _ in range(rnd.randint(0, 8)):
                r0, c0 = rnd.randint(0, 30), rnd.randint(0, 80)
                r1, c1 = r0 + rnd.randint(0, 25), c0 + rnd.choice([0, 0, 1, 3, 70])
                fills.append(f"{sprd.label(r0, c0)}:{sprd.label(r1, c1)} {rnd.choice(templates)}")
            rows = {}
            for _ in range(rnd.randint(0, 12)):
                width = rnd.choice([1, 3, 12, 90])
                rows[str(rnd.randint(0, 60))] = ",".join(rnd.choice(["", "", "v", "=1", '"a,b"', "7"]) for _ in range(width))
            sf = {"name": "S", "fills": fills, "rows": rows}
            box = None
            if rnd.random() < 0.6:
                a, b = rnd.randint(0, 60), rnd.randint(0, 160)
                box = (a, b, a + rnd.randint(0, 30), b + rnd.randint(0, 40))
            want, want_fills = reference(sf, box)
            with self.subTest(case=case):
                sheet = sprd.Sheet(sf)
                got = list(sheet.cells(box))
                self.assertEqual([(r, c) for r, c, _ in got], sorted(want), "every cell once, in row then column order")
                self.assertEqual({(r, c): t for r, c, t in got}, want)
                s = sheet.stats(box)
                self.assertEqual(s["cells"], len(want))
                self.assertEqual(s["formulas"], sum(1 for v in want.values() if v.startswith("=")))
                self.assertEqual(s["fill_cells"], len(want_fills))
                self.assertEqual(s["fill_text"], sum(want_fills.values()))
                self.assertEqual(s["last_row"], max((r for r, _ in want), default=-1))
                self.assertEqual(s["last_col"], max((c for _, c in want), default=-1))


class Writes(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.out = os.path.join(self.dir.name, "out.sprd")

    def tearDown(self):
        self.dir.cleanup()

    def spec(self, data):
        p = os.path.join(self.dir.name, "spec.json")
        with open(p, "w", encoding="utf-8") as f:
            json.dump(data, f)
        return p

    def test_round_trip(self):
        code, out, err = run("write", os.path.join(FIX, "spec.json"), self.out)
        self.assertEqual(code, 0, err)
        with open(self.out, "rb") as f:
            self.assertEqual(f.read(2), b"\x1f\x8b", "gzipped, as the app writes")
        doc = sprd.load(self.out)
        self.assertEqual(doc["spredin"], 1)
        budget = cells_by_label(sprd.sheet_files(doc)[0])
        self.assertEqual(budget["A5"], 'Notes, "misc"')
        self.assertEqual(budget["A9"], "line one\nline two")
        self.assertEqual(budget["C3"], "398.1")
        self.assertEqual(budget["D8"], "TRUE")
        self.assertEqual(budget["B8"], "'1200")
        self.assertNotIn("B5", budget, "null is an empty cell")
        rates = cells_by_label(sprd.sheet_files(doc)[1])
        self.assertEqual(rates, {"B2": "Rate", "C2": "0.075", "B3": "Months", "C3": "12"})
        self.assertEqual(doc["names"], {"Rate": "'Rates 2026'!$C$2"})

    def test_never_over_a_file_without_replace(self):
        with open(self.out, "w") as f:
            f.write("mine")
        code, _, err = run("write", os.path.join(FIX, "spec.json"), self.out)
        self.assertEqual(code, 1)
        self.assertIn("--replace", err)
        with open(self.out) as f:
            self.assertEqual(f.read(), "mine")
        self.assertEqual(run("write", os.path.join(FIX, "spec.json"), self.out, "--replace")[0], 0)
        self.assertEqual(sorted(os.listdir(self.dir.name)), ["out.sprd"], "no temporary file left behind")

    def test_refusals(self):
        bad = [
            ({"sheets": []}, "sheets"),
            ({"sheets": [{"name": "a/b"}]}, "31 characters"),
            ({"sheets": [{"name": "A"}, {"name": "a"}]}, "two sheets"),
            ({"sheets": [{"name": "A", "rows": [[float("nan")]]}]}, "not a number"),
            ({"sheets": [{"name": "A", "rows": [[{"x": 1}]]}]}, "not a cell value"),
            ({"sheets": [{"name": "A", "cells": {"A0": 1}}]}, "not a cell address"),
            ({"sheets": [{"name": "A", "formats": {"A1": {"font": "x"}}}]}, "format for A1"),
        ]
        for data, words in bad:
            with self.subTest(words=words):
                code, _, err = run("write", self.spec(data), self.out)
                self.assertEqual(code, 1)
                self.assertIn(words, err)
                self.assertFalse(os.path.exists(self.out))

    def test_numbers_are_written_as_the_app_reads_them(self):
        self.assertEqual(sprd.cell_text(1200, "x"), "1200")
        self.assertEqual(sprd.cell_text(1200.0, "x"), "1200")
        self.assertEqual(sprd.cell_text(0.1 + 0.2, "x"), "0.30000000000000004")
        self.assertEqual(sprd.cell_text(True, "x"), "TRUE")
        self.assertEqual(sprd.encode_row(["a", "", 'say "hi"', "x,y", "", ""]), 'a,,"say ""hi""","x,y"')


class CommandLine(unittest.TestCase):
    def test_info(self):
        code, out, _ = run("info", os.path.join(FIX, "compact.sprd"))
        self.assertEqual(code, 0)
        self.assertIn("form: compact", out)
        self.assertIn("sheet 1: 'Sales' A1:H12", out)
        self.assertIn("names: Rate = Sales!$B$2", out)

    def test_read_cells_escapes_line_breaks(self):
        code, out, _ = run("read", os.path.join(FIX, "full.sprd"), "--sheet", "2")
        self.assertEqual(code, 0)
        self.assertIn('A1\tHe said "hi", then\\nleft', out)

    def test_read_range_and_csv(self):
        code, out, _ = run("read", os.path.join(FIX, "compact.sprd"), "--sheet", "sales", "--range", "D1:E3", "--format", "csv")
        self.assertEqual(code, 0)
        self.assertEqual(out.splitlines(), ["Total,Label", '=B2+C2,"=""{""&A2&""}"""', '=B3+C3,"=""{""&A3&""}"""'])

    def test_read_max(self):
        code, out, _ = run("read", os.path.join(FIX, "compact.sprd"), "--sheet", "Sales", "--max", "3")
        self.assertEqual(code, 0)
        self.assertIn("# ... 50 more", out)

    def test_unknown_sheet_names_the_sheets(self):
        code, _, err = run("read", os.path.join(FIX, "compact.sprd"), "--sheet", "Nope")
        self.assertEqual(code, 1)
        self.assertIn("'Sales', 'Notes, 2026'", err)

    def test_not_a_workbook(self):
        with tempfile.NamedTemporaryFile("wb", suffix=".sprd", delete=False) as f:
            f.write(gzip.compress(b'{"hello": 1}'))
        try:
            code, _, err = run("info", f.name)
            self.assertEqual(code, 1)
            self.assertIn("not a .sprd workbook", err)
        finally:
            os.unlink(f.name)


if __name__ == "__main__":
    unittest.main()
