# Spredin Pro skill for Claude

A Claude skill that helps Claude work in **Spredin Pro**, the Excel-compatible
spreadsheet app: operating the app on screen (computer use), reading and writing
its files, and writing scripts for its Python panel. It is plain Markdown plus one
small Python script.

Skill 0.2.0, for Spredin Pro 1.0.4 (`VERSION`). Repository: https://github.com/GGHomology/Spredin-skill (MIT).

For Claude Desktop there is also the **Spredin connector**
(https://github.com/GGHomology/Spredin-connector): with it, Claude uses
Spredin's own tools on the open workbooks. Once the person allows Claude in
Spredin, Claude can read every open workbook without asking; each change asks
the person in Spredin first, unless they turned on "Apply assistant changes
without asking" (a script that reaches beyond the workbook still asks, unless
they allowed that too). The skill tells Claude to use those tools when they
are there.

## Install

In the Claude desktop app or on claude.ai:

1. Turn on code execution: Settings → Capabilities. Skills need it.
2. **Upload the skill**: build the zip here with `python3 tools/make_zip.py`
   (or take `spredin-pro-skill.zip` from the repository's releases, once there
   are some, and check its SHA-256 against the one published with it); then
   Customize → Skills → + → Create skill → Upload a skill, and choose the zip.

In Claude Code, copy `skills/spredin-pro` into `~/.claude/skills/`. Skills
enabled in the Claude app also reach Claude Code signed in to the same account.

`tools/make_zip.py` builds the zip from the files git tracks under
`skills/spredin-pro`, as committed (it refuses while one has changes not
committed), and the same commit always gives the same bytes; it prints the
zip's SHA-256.

Claude uses the skill when a request is about Spredin, e.g. "In Spredin, add a
total under column B" or "Make me a Spredin workbook from these CSV files".

## What is inside

```text
.claude-plugin/plugin.json        the plugin's manifest
skills/spredin-pro/SKILL.md       what Claude reads first: ways in, rules, key facts
skills/spredin-pro/references/    read when needed:
  app.md driving.md mac.md windows.md files.md engine.md examples.md links.md
  python-api.md functions.md menus.md    generated from the app's source
skills/spredin-pro/scripts/sprd.py      read and write .sprd files
tests/                            the tests (below)
tools/                            for maintainers: regenerate, check against the app, zip
```

## Safety

- The skill sends nothing anywhere and asks Claude to treat workbook text as
  data, to show scripts before running them, and to leave keys to the user.
- `sprd.py` uses only Python's standard library. It reads the one file it is
  given and writes only the file named after `write` (or `--out`), never over an
  existing file without `--replace`, through a temporary file and a rename. It
  opens no network connection and starts no program. `tests/test_skill.py`
  checks this by reading the script's code.
- A `.sprd` may come from anyone, so `sprd.py` bounds what a file can make it
  do (unzipped size, fill lines, output) and prints text with control and
  invisible characters shown as `\u{XXXX}`: see `SECURITY.md`.
- The only links are to spredin.com and the App Store page.

## Tests

```text
python3 -m unittest discover -s tests -v
```

- `test_skill.py`: the skill's shape (name, description length, size), that every
  file is reachable from SKILL.md and every relative link resolves, the link
  allowlist, no private paths or key-like text, the script's imports and calls,
  and that the generated files carry the version in `VERSION`.
- `test_sprd.py`: `sprd.py` against workbooks written by Spredin itself in each
  form it writes, and against what Spredin reads from small hand-made files
  (`tests/fixtures/rules.json`: which fill lines it keeps, the cells it gives,
  its limits on a sheet's fill lines, the dual form); a plain reference model on
  random sheets, its writer's checks, and the command line.
- `test_hostile.py`: files made to hurt it (a decompression bomb, fill lines over
  a whole sheet, a far-away cell, hidden characters, huge cells, broken shapes),
  each refused or read in bounded time and memory.
- `test_make_zip.py`: the zip is the same bytes for the same commit, and a tree
  with changes not committed is refused.
- A private word list can be added: set `SPREDIN_SKILL_DENYLIST` to a file of
  words (one a line) that must appear nowhere.
- `tests/SCENARIOS.md`: tasks to give Claude with the skill installed, and how to
  grade them.

## For maintainers (needs a Spredin Pro source checkout)

```text
cd <spredin-pro checkout>
node_modules/.bin/vite-node <this repo>/tools/gen-refs.mts           # regenerate the 3 generated files
node_modules/.bin/vite-node <this repo>/tools/gen-refs.mts --check   # fails if they are out of date
node_modules/.bin/vite-node <this repo>/tools/app-check.mts          # fixtures, rules.json, and sprd.py write read by the app
```

Run both after each Spredin release, raise `skill:` in `VERSION` and
`plugin.json`, and run the tests.

## Licence

To be chosen before the repository is published.
