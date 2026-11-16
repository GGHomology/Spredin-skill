"""tools/make_zip.py: the same commit gives the same bytes, and a tree with
changes not committed is refused.

Each test copies make_zip.py and the skill into a new git repository in a
temporary folder, so this repository's own dist/ and history are never touched.
"""
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GIT = shutil.which("git")
# A git that reads no one's settings: no signing, hooks or templates.
ENV = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_SYSTEM=os.devnull, GIT_CONFIG_NOSYSTEM="1",
           GIT_AUTHOR_NAME="Test", GIT_AUTHOR_EMAIL="test@spredin.com", GIT_COMMITTER_NAME="Test",
           GIT_COMMITTER_EMAIL="test@spredin.com", GIT_AUTHOR_DATE="2026-01-01T00:00:00Z",
           GIT_COMMITTER_DATE="2026-01-01T00:00:00Z")


def tracked_skill_files():
    out = subprocess.run(["git", "-C", ROOT, "ls-files", "-z", "--", "skills/spredin-pro"], check=True,
                         capture_output=True, env=ENV).stdout
    return sorted(p.decode() for p in out.split(b"\0") if p)


@unittest.skipUnless(GIT, "git is not installed")
class MakeZip(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.files = tracked_skill_files()

    def tearDown(self):
        self.tmp.cleanup()

    def repo(self, name, mtime):
        """A new repository holding make_zip.py and the skill, every file dated `mtime`."""
        root = os.path.join(self.tmp.name, name)
        for rel in ["tools/make_zip.py"] + self.files:
            dst = os.path.join(root, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(os.path.join(ROOT, rel), dst)
            os.utime(dst, (mtime, mtime))
        for argv in (["init", "-q"], ["add", "-A"], ["commit", "-q", "-m", "skill"]):
            subprocess.run(["git", "-C", root, *argv], check=True, capture_output=True, env=ENV)
        return root

    def make(self, root, *args):
        p = subprocess.run([sys.executable, "-I", os.path.join(root, "tools", "make_zip.py"), *args],
                           capture_output=True, text=True, env=ENV)
        zip_path = os.path.join(root, "dist", "spredin-pro-skill.zip")
        data = None
        if p.returncode == 0:
            with open(zip_path, "rb") as f:
                data = f.read()
        return p.returncode, p.stdout, p.stderr, data

    def test_the_same_commit_gives_the_same_bytes(self):
        a = self.repo("a", 1_000_000_000)
        b = self.repo("b", 1_700_000_000)  # another folder, other file dates
        code, out, err, first = self.make(a)
        self.assertEqual(code, 0, err)
        again = self.make(a)[3]
        os.utime(os.path.join(a, "skills", "spredin-pro", "SKILL.md"), (1_800_000_000, 1_800_000_000))
        touched = self.make(a)[3]
        elsewhere = self.make(b)[3]
        self.assertEqual(first, again)
        self.assertEqual(first, touched, "a file's date does not change the zip")
        self.assertEqual(first, elsewhere, "nor the folder or machine it is built in")
        self.assertIn(f"sha256 {hashlib.sha256(first).hexdigest()}", out)

    def test_the_zip_holds_the_tracked_skill_and_nothing_else(self):
        a = self.repo("a", 1_000_000_000)
        with open(os.path.join(a, "skills", "spredin-pro", "notes.txt"), "w") as f:
            f.write("not tracked")
        os.makedirs(os.path.join(a, "skills", "spredin-pro", "__pycache__"))
        code, out, err, data = self.make(a)
        self.assertEqual(code, 0, err)
        self.assertIn("not in the zip (git does not track it): skills/spredin-pro/notes.txt", err)
        zip_path = os.path.join(a, "dist", "spredin-pro-skill.zip")
        with zipfile.ZipFile(zip_path) as z:
            infos = z.infolist()
            self.assertEqual([i.filename for i in infos], ["spredin-pro/" + os.path.relpath(p, "skills/spredin-pro") for p in self.files])
            for i in infos:
                self.assertEqual(i.date_time, (1980, 1, 1, 0, 0, 0))
                self.assertEqual(i.compress_type, zipfile.ZIP_STORED)
                self.assertEqual(i.external_attr >> 16, 0o100644)
            with open(os.path.join(ROOT, "skills", "spredin-pro", "SKILL.md"), "rb") as f:
                self.assertEqual(z.read("spredin-pro/SKILL.md"), f.read())

    def test_changes_not_committed_are_refused(self):
        a = self.repo("a", 1_000_000_000)
        clean = self.make(a)[3]
        skill_md = os.path.join(a, "skills", "spredin-pro", "SKILL.md")
        with open(skill_md, "a") as f:
            f.write("\nan edit\n")
        code, out, err, data = self.make(a)
        self.assertEqual(code, 1)
        self.assertIn("changes not committed", err)
        self.assertIn("skills/spredin-pro/SKILL.md", err)
        with open(os.path.join(a, "dist", "spredin-pro-skill.zip"), "rb") as f:
            self.assertEqual(f.read(), clean, "the refused run wrote nothing")
        # Staged but not committed is a change too.
        subprocess.run(["git", "-C", a, "add", "-A"], check=True, capture_output=True, env=ENV)
        self.assertEqual(self.make(a)[0], 1)
        # --allow-dirty takes the working copy, and says so.
        code, out, err, data = self.make(a, "--allow-dirty")
        self.assertEqual(code, 0, err)
        self.assertIn("with changes not committed", out)
        with zipfile.ZipFile(os.path.join(a, "dist", "spredin-pro-skill.zip")) as z:
            self.assertTrue(z.read("spredin-pro/SKILL.md").endswith(b"an edit\n"))

    def test_outside_a_repository_it_says_so(self):
        root = os.path.join(self.tmp.name, "plain")
        os.makedirs(os.path.join(root, "tools"))
        shutil.copy2(os.path.join(ROOT, "tools", "make_zip.py"), os.path.join(root, "tools"))
        code, out, err, data = self.make(root)
        self.assertEqual(code, 1)
        self.assertTrue(re.search(r"git could not list|git tracks no files", err), err)


if __name__ == "__main__":
    unittest.main()
