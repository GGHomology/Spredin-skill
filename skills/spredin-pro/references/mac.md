# Spredin Pro on the Mac

## Getting it

- Mac App Store: https://apps.apple.com/app/id6827359146 (Spredin Pro). Needs an
  Apple silicon Mac (M1 or later) and macOS 13 or later.
- The app is called **Spredin Pro** in Finder, Spotlight and the Dock.
- For computer use, the user must allow Spredin Pro in your computer-use settings.

## Opening files from a shell

```text
open -a "Spredin Pro" ~/Documents/Budget.xlsx    # opens it in a window
open -a "Spredin Pro"                            # starts the app
```

- Opening a file that is already open brings its window forward; it does NOT
  read the file again. To see a changed file, close its window first.
- The app has no AppleScript commands beyond the standard ones (`quit` asks about
  unsaved changes). There is no command-line interface.
- Files the user saves are wherever they chose. The app keeps earlier versions and
  its settings in its own folders: do not edit those.

## Keys

| Windows Excel | Spredin Pro on the Mac | What it does |
|---|---|---|
| Ctrl+C / X / V | ⌘C / ⌘X / ⌘V | copy / cut (a move) / paste; Edit menu for Paste Values and the rest |
| Ctrl+Z / Ctrl+Y | ⌘Z / ⇧⌘Z | undo / redo |
| Ctrl+B / I / U | ⌘B / ⌘I / ⌘U | bold / italic / underline |
| F2 | fn F2, or ⌃U | edit the active cell |
| F4 | ⌘T | cycle `$` in the reference under the cursor (macOS takes F4) |
| Alt+Enter | ⌥Return | line break inside a cell |
| Ctrl+Enter | ⌘Return | the entry in every selected cell |
| Ctrl+D / Ctrl+R | ⌘D / ⌘R | fill down / right (⇧ for up / left) |
| Alt+= | ⇧⌘T | AutoSum |
| Ctrl+1 | ⌘1 | Format Cells |
| Ctrl+F / Ctrl+H | ⌘F | find and replace |
| Ctrl+S / F12 | ⌘S / ⇧⌘S | save / save as |
| Ctrl+P | ⌘P | print, with preview, or Save as PDF |
| Ctrl+Arrow / Ctrl+Shift+Arrow | ⌘Arrow / ⇧⌘Arrow | jump to / select to the edge of the data |
| Ctrl+Home / Ctrl+End | ⌘Home / ⌘End | A1 / the last used cell |
| Ctrl+A | ⌘A | the table around the active cell; again for the whole sheet |
| Shift+Space / Ctrl+Space | ⇧Space / ⌃Space | select the row / the column |
| Ctrl+PageDown / Ctrl+PageUp | ⌥→ / ⌥← (or ⌃fn↓ / ⌃fn↑) | next / previous sheet |
| F9 | fn F9, or Data → Calculate Now | calculate TODAY, NOW, RAND and what reads them again |
| (none) | ⌘K | the command palette: every command by name |
| Esc | Esc, or ⌘. | cancel; ⌘. also cancels a cut |

On a Mac keyboard the top row is for brightness, sound and the like: F2 and
F9 need fn held (unless the keyboard is set to use them as function keys).
Most Mac keyboards have no Page keys: Page Down is fn+↓. ⌃Space may be taken by
the input-source switch; click the column letter instead. The full list of
commands with their keys is in menus.md.

Pro also takes Windows Excel's Alt-key sequences on ⌥ (Settings → Excel Key
Chains): tap ⌥, then the letters, e.g. E S V for Paste Values.
