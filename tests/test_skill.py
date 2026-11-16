"""The skill's shape, links, hygiene and the script's safety.

    python3 -m unittest discover -s tests -v
"""
import ast
import json
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILL = os.path.join(ROOT, "skills", "spredin-pro")
REFS = os.path.join(SKILL, "references")
GENERATED = ("python-api.md", "functions.md", "menus.md")
LINK_HOSTS = {"spredin.com", "apps.apple.com", "github.com"}
# github.com only for the two GGHomology repositories (test_github_links_are_ours).
GITHUB_OURS = ("https://github.com/GGHomology/Spredin-connector", "https://github.com/GGHomology/Spredin-skill")
README_HOSTS = LINK_HOSTS | {"claude.com", "claude.ai", "support.claude.com"}
SCRIPT_IMPORTS = {"argparse", "csv", "gzip", "io", "json", "os", "re", "sys", "tempfile", "zipfile"}
# tools/make_zip.py alone may also run programs, and only `git` (test_make_zip_runs_only_git);
# scripts/sprd.py, the script that ships, may not.
EXTRA_IMPORTS = {os.path.join("tools", "make_zip.py"): {"subprocess", "hashlib"}}
BANNED_NAMES = {"eval", "exec", "compile", "__import__", "breakpoint", "input"}
BANNED_ATTRS = {"system", "popen", "spawnl", "spawnv", "execv", "execl", "fork", "kill", "rmtree", "chmod", "chown", "symlink", "remove", "rename"}


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def text_files():
    for folder, dirs, files in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in {".git", "dist", "__pycache__", "fixtures"}]
        for name in files:
            if name.endswith((".md", ".py", ".json", ".mts", ".txt")) or name in {"VERSION", ".gitignore"}:
                yield os.path.join(folder, name)


def frontmatter(text):
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    if not m:
        return None, text
    fields = {}
    for line in m.group(1).splitlines():
        k, _, v = line.partition(":")
        fields[k.strip()] = v.strip()
    return fields, text[m.end():]


class Shape(unittest.TestCase):
    def setUp(self):
        self.text = read(os.path.join(SKILL, "SKILL.md"))
        self.fields, self.body = frontmatter(self.text)

    def test_frontmatter(self):
        self.assertIsNotNone(self.fields, "SKILL.md starts with --- name/description ---")
        self.assertEqual(set(self.fields), {"name", "description"})
        name = self.fields["name"]
        self.assertEqual(name, os.path.basename(SKILL), "the name is the folder's name")
        self.assertRegex(name, r"^[a-z0-9-]{1,64}$")
        self.assertNotIn(name, {"claude", "anthropic", "official", "plugin", "mcp", "test"})

    def test_description(self):
        d = self.fields["description"]
        self.assertTrue(20 <= len(d) <= 200, f"description is {len(d)} characters (one page says 200 at most)")
        self.assertNotRegex(d, r"[<>]")
        self.assertIn("Spredin", d, "Claude picks a skill by its description: it must name the app")

    def test_size(self):
        self.assertLess(len(self.text.splitlines()), 200, "SKILL.md is read whole every time: keep it short")
        for name in os.listdir(REFS):
            if name not in GENERATED:
                self.assertLess(len(read(os.path.join(REFS, name)).splitlines()), 400, name)

    def test_every_file_is_reachable_from_skill_md(self):
        for name in os.listdir(REFS):
            self.assertIn(f"references/{name}", self.text, f"SKILL.md does not point to {name}")
        for name in os.listdir(os.path.join(SKILL, "scripts")):
            if name.endswith(".py"):
                self.assertIn(f"scripts/{name}", self.text, f"SKILL.md does not point to {name}")

    def test_versions_agree(self):
        v = dict(line.split(": ", 1) for line in read(os.path.join(ROOT, "VERSION")).splitlines() if ": " in line)
        self.assertRegex(v["skill"], r"^\d+\.\d+\.\d+$")
        app = v["app"]
        self.assertRegex(app, r"^Spredin Pro \d+\.\d+\.\d+$")
        plugin = json.loads(read(os.path.join(ROOT, ".claude-plugin", "plugin.json")))
        self.assertEqual(plugin["version"], v["skill"])
        self.assertEqual(plugin["name"], "spredin")
        self.assertIn(app.split()[-1], read(os.path.join(ROOT, "README.md")))
        for name in GENERATED:
            head = read(os.path.join(REFS, name)).splitlines()[0]
            self.assertIn(f"Generated from {app} ", head, f"{name} is from another version: regenerate")


    def test_the_function_count_said_is_the_count(self):
        n = re.search(r"^(\d+) functions\.$", read(os.path.join(REFS, "functions.md")), re.M)
        self.assertIsNotNone(n)
        for name in ("SKILL.md", os.path.join("references", "engine.md")):
            for said in re.findall(r"(\d+) functions", read(os.path.join(SKILL, name))):
                self.assertEqual(said, n.group(1), f"{name} says {said} functions, functions.md has {n.group(1)}")


class Links(unittest.TestCase):
    def test_relative_links_resolve(self):
        for path in text_files():
            if not path.endswith(".md"):
                continue
            for target in re.findall(r"\]\(([^)#\s]+)\)", read(path)):
                if re.match(r"^[a-z]+:", target):
                    continue
                full = os.path.normpath(os.path.join(os.path.dirname(path), target))
                self.assertTrue(os.path.exists(full), f"{os.path.relpath(path, ROOT)}: broken link {target}")

    def test_external_links_are_allowed_hosts(self):
        for path in text_files():
            allowed = README_HOSTS if os.path.basename(path) == "README.md" else LINK_HOSTS
            for host in re.findall(r"https?://([a-z0-9.-]+)", read(path)):
                self.assertIn(host, allowed, f"{os.path.relpath(path, ROOT)} links to {host}")

    def test_github_links_are_ours(self):
        for path in text_files():
            for url in re.findall(r"https?://github\.com/[^\s)>\]]*", read(path)):
                self.assertTrue(url.startswith(GITHUB_OURS), f"{os.path.relpath(path, ROOT)} links to {url}")


class Hygiene(unittest.TestCase):
    PATTERNS = {
        "a real home folder": r"/Users/(?!you\b)[A-Za-z0-9_.-]+|C:\\Users\\(?!%USERNAME%|you\b)",
        "a key": r"\bsk-[A-Za-z0-9_-]{16,}|\bghp_[A-Za-z0-9]{20,}|github_pat_|\bAKIA[0-9A-Z]{16}\b|\bBSA[A-Za-z0-9_-]{20,}|\btvly-[A-Za-z0-9]{10,}|-----BEGIN [A-Z ]*PRIVATE KEY",
        # A folder named as private by a common convention. Words that must not
        # appear can also be listed in a file named by SPREDIN_SKILL_DENYLIST.
        "an internal folder": r"\b[A-Za-z]+-internal\b",
        "an email address": r"[A-Za-z0-9._%+-]+@(?!spredin\.com\b)[A-Za-z0-9.-]+\.[a-z]{2,}",
    }

    def test_no_private_text(self):
        deny = []
        extra = os.environ.get("SPREDIN_SKILL_DENYLIST")
        if not extra:
            print("\n(Hygiene: SPREDIN_SKILL_DENYLIST is not set; the maintainer's private word list was not checked.)")
        if extra:
            deny = [w.strip().lower() for w in read(extra).splitlines() if w.strip() and not w.startswith("#")]
        for path in text_files():
            rel = os.path.relpath(path, ROOT)
            if rel == os.path.join("tests", "test_skill.py"):
                continue  # this file spells the patterns out
            text = read(path)
            for what, pat in self.PATTERNS.items():
                m = re.search(pat, text)
                self.assertIsNone(m, f"{rel} holds {what}: {m.group(0) if m else ''}")
            low = text.lower()
            for i, w in enumerate(deny):
                # The word itself is never printed: a failing run's log could be public.
                self.assertFalse(w in low, f"{rel} holds word {i + 1} of the private list")

    def test_fixtures_hold_only_test_data(self):
        # The fixtures are made by tools/app-check.mts from a fixed workbook.
        exp = json.loads(read(os.path.join(ROOT, "tests", "fixtures", "expected.json")))
        for f, book in exp.items():
            self.assertEqual(set(book["sheets"]), {"Sales", "Notes, 2026"}, f)


class ScriptSafety(unittest.TestCase):
    def scripts(self):
        for folder in (os.path.join(SKILL, "scripts"), os.path.join(ROOT, "tools")):
            for name in sorted(os.listdir(folder)):
                if name.endswith(".py"):
                    yield os.path.join(folder, name)

    def test_imports_and_calls(self):
        for path in self.scripts():
            allowed = SCRIPT_IMPORTS | EXTRA_IMPORTS.get(os.path.relpath(path, ROOT), set())
            tree = ast.parse(read(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for a in node.names:
                        self.assertIn(a.name.split(".")[0], allowed, f"{path}: import {a.name}")
                elif isinstance(node, ast.ImportFrom):
                    self.assertIn((node.module or "").split(".")[0], allowed, f"{path}: from {node.module}")
                elif isinstance(node, ast.Name):
                    self.assertNotIn(node.id, BANNED_NAMES, f"{path}: uses {node.id}")
                elif isinstance(node, ast.Attribute):
                    self.assertNotIn(node.attr, BANNED_ATTRS, f"{path}: uses .{node.attr}")

    def test_make_zip_runs_only_git(self):
        path = os.path.join(ROOT, "tools", "make_zip.py")
        calls = []
        for node in ast.walk(ast.parse(read(path))):
            if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "subprocess":
                self.assertIn(node.attr, {"run", "CalledProcessError"}, f"{path}: subprocess.{node.attr}")
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "run" \
                    and isinstance(node.func.value, ast.Name) and node.func.value.id == "subprocess":
                calls.append(node)
        self.assertEqual(len(calls), 1, "one place runs a program")
        call = calls[0]
        argv = call.args[0]
        self.assertIsInstance(argv, ast.List, "a list of arguments, never a command line")
        self.assertIsInstance(argv.elts[0], ast.Constant)
        self.assertEqual(argv.elts[0].value, "git")
        self.assertNotIn("shell", {k.arg for k in call.keywords})

    def test_the_skill_script_deletes_only_its_own_temp_file(self):
        src = read(os.path.join(SKILL, "scripts", "sprd.py"))
        self.assertEqual(src.count("os.unlink("), 1)
        self.assertIn("os.unlink(tmp)", src)


if __name__ == "__main__":
    unittest.main()
