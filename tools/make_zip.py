#!/usr/bin/env python3
"""Build dist/spredin-pro-skill.zip for the Claude app's "Upload a skill":
the skill folder at the top of the zip, nothing else.

    python3 tools/make_zip.py [--allow-dirty]

- Only the files git tracks under skills/spredin-pro, as the last commit holds
  them. It refuses while any of them has a change not committed (staged or
  not); --allow-dirty takes the working copies instead, for trying a change.
  Files git does not track are never in the zip (it names them).
- The same commit gives the same bytes on any machine: names in sorted order,
  a fixed date (1980-01-01), fixed permissions, and entries stored rather than
  compressed, which no zlib version changes.
- It prints the zip's SHA-256, to publish beside it.

Standard library only. It runs `git` and nothing else.
"""
import argparse
import hashlib
import io
import os
import subprocess
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILL = "skills/spredin-pro"
OUT = os.path.join(ROOT, "dist", "spredin-pro-skill.zip")
DATE = (1980, 1, 1, 0, 0, 0)
MODES = {"100644": 0o100644, "100755": 0o100755}


def git(*args):
    return subprocess.run(["git", "-C", ROOT, *args], check=True, capture_output=True).stdout


def tracked():
    """[(path, mode, blob)] of the files git tracks under the skill, sorted."""
    out = []
    for rec in git("ls-files", "-s", "-z", "--", SKILL).split(b"\0"):
        if rec:
            meta, path = rec.split(b"\t", 1)
            mode, blob, _stage = meta.decode().split()
            out.append((path.decode("utf-8"), mode, blob))
    return sorted(out)


def main(argv=None):
    p = argparse.ArgumentParser(prog="make_zip.py", description="Build the skill's zip from the files git tracks.")
    p.add_argument("--allow-dirty", action="store_true", help="take the working copies, changes and all")
    args = p.parse_args(argv)
    try:
        files = tracked()
        status = git("status", "--porcelain", "-z", "--untracked-files=all", "--", SKILL).split(b"\0")
    except (OSError, subprocess.CalledProcessError) as e:
        print(f"make_zip.py: git could not list the skill's files ({e})", file=sys.stderr)
        return 1
    changed = sorted(r[3:].decode("utf-8", "replace") for r in status if r and not r.startswith(b"??"))
    untracked = sorted(r[3:].decode("utf-8", "replace") for r in status if r.startswith(b"??"))
    if not files:
        print(f"make_zip.py: git tracks no files under {SKILL}", file=sys.stderr)
        return 1
    if changed and not args.allow_dirty:
        print("make_zip.py: these files have changes not committed; commit them, or pass --allow-dirty:", file=sys.stderr)
        for path in changed:
            print(f"  {path}", file=sys.stderr)
        return 1
    for path in untracked:
        print(f"make_zip.py: not in the zip (git does not track it): {path}", file=sys.stderr)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as z:
        for path, mode, blob in files:
            if mode not in MODES:
                print(f"make_zip.py: {path} is not a plain file (git mode {mode})", file=sys.stderr)
                return 1
            if args.allow_dirty:
                with open(os.path.join(ROOT, path), "rb") as f:
                    data = f.read()
            else:
                data = git("cat-file", "blob", blob)
            info = zipfile.ZipInfo("spredin-pro/" + os.path.relpath(path, SKILL).replace(os.sep, "/"), date_time=DATE)
            info.compress_type = zipfile.ZIP_STORED
            info.create_system = 3  # Unix, so the permissions below are read the same everywhere
            info.external_attr = MODES[mode] << 16
            z.writestr(info, data)
    data = buf.getvalue()
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "wb") as f:
        f.write(data)
    print(f"wrote {OUT} ({len(files)} files{', with changes not committed' if changed else ''})")
    print(f"sha256 {hashlib.sha256(data).hexdigest()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
