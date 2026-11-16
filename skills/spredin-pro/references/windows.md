# Spredin Pro on Windows (planned)

There is no Windows version yet. This page says what is expected to differ, so
the rest of this skill can be used unchanged when it ships. When it does, trust
the app's own Help → Coming from Excel over this page for keys.

## What stays the same

The files (`.sprd`, `.xlsx`, `.csv`), the formulas and functions, the Python API,
the panels, the dialogs and `scripts/sprd.py` (run it with `python` or `py`).

## What is expected to differ

- **Keys are Windows Excel's**: Ctrl where the Mac uses ⌘; F4 cycles `$`
  references; Ctrl+Y redoes; F5 or Ctrl+G opens Go To; F12 is Save As; Alt+= is
  AutoSum; Ctrl+1 is Format Cells; Ctrl+PageUp / Ctrl+PageDown switch sheets.
- **The menu row inside the window is the only menu** (no menu bar at the top of
  the screen). Alt or F10 moves to it.
- **The command palette**: expected on Ctrl+K; check the app's Help if not.
- **Opening files from a shell**:

```text
Start-Process "$env:USERPROFILE\Documents\Budget.xlsx"     # PowerShell
start "" "%USERPROFILE%\Documents\Budget.xlsx"             # cmd
```

  Opening a file already open brings its window forward and does not read it
  again, as on the Mac.
- **Paths** use backslashes; quote paths with spaces.
- **Settings and keys** are kept in Windows' own stores (the Mac uses the
  Keychain). As on the Mac, never type keys yourself.
