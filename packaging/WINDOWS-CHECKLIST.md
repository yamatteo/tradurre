# Windows checklist for a release candidate

For a Claude Code agent on the developer's Windows 10 or 11 machine, working in **PowerShell** with no GUI. Every
step is commands you can copy and run as they are, plus what they should print. Steps 1–8 are for the agent; step
9 is for the developer, by hand.

## How to work

- The candidate is in `C:\tradurre-rc\`:
  - the wheel `tradurre-<version>-py3-none-any.whl`;
  - `start-tradurre.bat`, the launcher, already filled in with this version and with the wheel's `file:///` URL;
  - `smoke.py`, the browser smoke test;
  - `fixtures\`, holding `easy.source.docx`, `easy.target.pdf`, `easy.source.txt` and `easy.target.txt`;
  - this checklist.
- Write the results to `C:\tradurre-rc\RESULTS.md`. For each step, write a heading, then `PASS` or `FAIL` per
  check, the relevant output (shortened), and anything unexpected. The developer brings this file back.
- On a `FAIL`, record it and go on with the next step that doesn't depend on it. **Whatever happens, run step 8
  last**: it puts the developer's own Tradurre and data back.
- Never copy the developer's own data into `RESULTS.md`, such as titles or text from the library you back up in
  step 1. Counts are fine.
- Only one Tradurre runs at a time, on port 8000. Stop it as below, by **process id**. Never stop processes by a
  name pattern: it could kill your own shell.
- Use `curl.exe`, not `curl`: in PowerShell, `curl` is an alias of `Invoke-WebRequest`. For requests with a JSON
  body, use `Invoke-WebRequest -UseBasicParsing`, because PowerShell 5.1 strips the double quotes inside native
  command arguments.

Run this first in every new PowerShell session. It sets the paths and adds two small helpers.

```powershell
$RC = 'C:\tradurre-rc'
New-Item -ItemType Directory -Force "$RC\logs" | Out-Null
$env:PATH = "$env:USERPROFILE\.local\bin;$env:PATH"   # where uv and tradurre.exe live
$env:PYTHONUTF8 = '1'                                  # smoke.py prints arrows; redirected output is not UTF-8 otherwise
$WHEEL = (Get-ChildItem "$RC\tradurre-*.whl").Name
$VERSION = ($WHEEL -split '-')[1]
$API = 'http://127.0.0.1:8000/api'

function Wait-Tradurre($path, $seconds = 600) {
  # Waits until $API$path answers 200 (the first start after an install can take minutes).
  for ($i = 0; $i -lt $seconds; $i++) {
    if ((curl.exe -s -o NUL -w '%{http_code}' "$API$path") -eq '200') { return $true }
    Start-Sleep -Seconds 1
  }
  return $false
}

function Stop-Tradurre {
  # Stops whatever listens on port 8000, then any tradurre.exe left: both by process id.
  Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue |
    ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
  Get-Process -Name tradurre -ErrorAction SilentlyContinue |
    ForEach-Object { Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue }
  Start-Sleep -Seconds 2
  # Expected: nothing listens on 8000 any more.
  if (Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue) { 'STILL RUNNING' } else { 'stopped' }
}

"$WHEEL / $VERSION"
```

Expected: the wheel's name and its version, for example `tradurre-0.2.0rc1-py3-none-any.whl / 0.2.0rc1`.

## 1. Prepare and back up

```powershell
Test-Path "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe"
Test-Path "$env:ProgramFiles\Google\Chrome\Application\chrome.exe"
Get-Command uv.exe -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source
```

Expected: `True`, `True`, and a path to `uv.exe`.

Check whether Windows has the Visual C++ runtime that PDF support needs:

```powershell
Test-Path "$env:SystemRoot\System32\msvcp140.dll"
```

Record the answer. If it is `False`, the launcher will install the Microsoft Visual C++ Redistributable in step 3,
and Windows will ask for permission on the desktop, which you can't click. **Tell the developer before step 3** that
they need to be at the machine to click "Yes", and wait until they say they're ready.

If `uv.exe` is missing, install it with the official one-liner and run the preamble again:

```powershell
powershell -NoProfile -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Record what is installed now, so step 8 can put it back:

```powershell
$before = Get-Command tradurre.exe -ErrorAction SilentlyContinue
if ($before) { "installed: [$(tradurre.exe --version 2>$null)]" } else { 'not installed' }
```

Write the exact output in the results. An empty `[]` means an installed version with no `--version`, which can
only be v0.1.0.

Stop any running Tradurre, then move the developer's data out of the way:

```powershell
Stop-Tradurre
if (Test-Path "$env:USERPROFILE\.tradurre.before-rc") { 'BACKUP ALREADY EXISTS: stop and ask the developer' }
elseif (Test-Path "$env:USERPROFILE\.tradurre") { Rename-Item "$env:USERPROFILE\.tradurre" '.tradurre.before-rc'; 'backed up' }
else { 'no data to back up' }
```

Expected: `stopped`, then `backed up` or `no data to back up`. If it prints `BACKUP ALREADY EXISTS`, an earlier
run didn't finish step 8. Stop and ask the developer. Don't overwrite the backup.

## 2. Tradurre v0.1.0 with a project

```powershell
uv tool install --force --python 3.14 "tradurre[pdf] @ https://github.com/yamatteo/tradurre/releases/download/v0.1.0/tradurre-0.1.0-py3-none-any.whl"
Start-Process -FilePath tradurre.exe -ArgumentList '--no-browser' -WindowStyle Hidden `
  -RedirectStandardOutput "$RC\logs\v01.out.log" -RedirectStandardError "$RC\logs\v01.err.log"
Wait-Tradurre '/v1/projects'
```

Expected: the install ends with `Installed 2 executables: tradurre, tradurre-align`, then `True`.

```powershell
$r = Invoke-WebRequest -UseBasicParsing -Method Post -Uri "$API/v1/projects" -ContentType 'application/json' `
  -Body '{"title": "Checklist v0.1", "source_lang": "fr", "target_lang": "it"}'
$r.StatusCode
(Invoke-RestMethod "$API/v1/projects").title
Stop-Tradurre
```

Expected: `201`, then `Checklist v0.1`, then `stopped`.

## 3. Upgrade through the candidate's launcher

The launcher sees v0.1.0 (it has no `--version`) and installs the candidate over it. Its input comes from `NUL`,
so a `pause` on an error can't hang.

```powershell
Start-Process -FilePath cmd.exe -WindowStyle Hidden `
  -ArgumentList "/c `"$RC\start-tradurre.bat --no-browser <NUL >$RC\logs\launcher-1.log 2>&1`""
Wait-Tradurre '/v2/books'
Get-Content "$RC\logs\launcher-1.log" | Select-String 'Updating|Retrying|installed|Visual C'
tradurre.exe --version
Test-Path "$env:SystemRoot\System32\msvcp140.dll"
```

Expected:
- `True`;
- `Updating Tradurre from an older version to <VERSION>...` and `Tradurre <VERSION> is installed.`;
- if uv failed to remove the old version, `Retrying the install of Tradurre...` too. Record whether it appeared:
  it is the launcher's way around the uv error the last run hit;
- if step 1 found no runtime, the lines about installing the Visual C++ Redistributable. Record them, and whether
  the developer clicked "Yes";
- `tradurre <VERSION>`;
- `True`: the runtime is there now. If it is `False`, record why (the prompt declined, a failed download): PDF
  imports in steps 4 and 6 will then fail with a message that names the redistributable.

```powershell
curl.exe -s "$API/v2/books"
Get-ChildItem "$env:USERPROFILE\.tradurre\backups" | Select-Object -ExpandProperty Name
@'
import glob, os, sqlite3
f = glob.glob(os.path.expanduser(r'~\.tradurre\backups\tradurre-*.db'))
print(len(f), [r[0] for r in sqlite3.connect(f[0]).execute('SELECT title FROM projects')])
'@ | Set-Content "$RC\logs\snapshot.py"
uv run --no-project --python 3.14 python "$RC\logs\snapshot.py"
```

Expected:
- `[]`: migration 6 dropped the v0.1 project, which had no books;
- one `tradurre-YYYYMMDD-HHMMSS.db`, with the time in local time;
- `1 ['Checklist v0.1']`: the snapshot taken before the upgrade still holds the old project.

## 4. The browser smoke test, in Edge and in Chrome

Tradurre keeps running from step 3.

```powershell
uv run --no-project --python 3.14 --with playwright python "$RC\smoke.py" --channel msedge --fixtures "$RC\fixtures" *>&1 | Tee-Object "$RC\logs\smoke-edge.log"
"exit $LASTEXITCODE"
uv run --no-project --python 3.14 --with playwright python "$RC\smoke.py" --channel chrome --fixtures "$RC\fixtures" *>&1 | Tee-Object "$RC\logs\smoke-chrome.log"
"exit $LASTEXITCODE"
```

Expected: for each browser, 11 `PASS` lines, `All steps passed.` and `exit 0`. Copy both outputs into the results
in full. They hold no book text, only step names and the word searched.

If `uv run --with playwright` fails before `smoke.py` starts, with `failed to remove directory` and os error 32,
run it from a plain virtual environment instead, and record that you did:

```powershell
uv run --no-project --python 3.14 python -m venv "$RC\pw"
& "$RC\pw\Scripts\python.exe" -m pip install playwright
& "$RC\pw\Scripts\python.exe" "$RC\smoke.py" --channel msedge --fixtures "$RC\fixtures" *>&1 | Tee-Object "$RC\logs\smoke-edge.log"
"exit $LASTEXITCODE"
& "$RC\pw\Scripts\python.exe" "$RC\smoke.py" --channel chrome --fixtures "$RC\fixtures" *>&1 | Tee-Object "$RC\logs\smoke-chrome.log"
"exit $LASTEXITCODE"
```

```powershell
curl.exe -s "$API/v2/books"
```

Expected: `[]`. The smoke test deletes the books it creates.

## 5. API round trip across a restart

Import the .txt pair and mark its first bead reviewed:

```powershell
$book = curl.exe -s -F "source=@$RC\fixtures\easy.source.txt" -F "target=@$RC\fixtures\easy.target.txt" -F "title=Checklist" "$API/v2/books" | ConvertFrom-Json
"$($book.title) $($book.bead_count) beads, warnings: $($book.warnings.Count)"
$id = $book.id
$bead = (Invoke-RestMethod "$API/v2/books/$id").beads[0].id
$r = Invoke-WebRequest -UseBasicParsing -Method Post -Uri "$API/v2/books/$id/reviewed" -ContentType 'application/json' `
  -Body "{`"bead_ids`": [$bead], `"reviewed`": true}"
$r.StatusCode
(Invoke-RestMethod "$API/v2/books/$id").beads[0].reviewed
```

Expected: `Checklist 28 beads, warnings: 0`, then `200`, then `True`.

Restart through the launcher. This time it must **not** update, because the version matches:

```powershell
Stop-Tradurre
Start-Process -FilePath cmd.exe -WindowStyle Hidden `
  -ArgumentList "/c `"$RC\start-tradurre.bat --no-browser <NUL >$RC\logs\launcher-2.log 2>&1`""
Wait-Tradurre '/v2/books'
Get-Content "$RC\logs\launcher-2.log" | Select-String 'Updating|installed'
```

Expected: `stopped`, `True`, and no output from `Select-String`.

Undo survives the restart, and each start took a snapshot:

```powershell
(Invoke-WebRequest -UseBasicParsing -Method Post -Uri "$API/v2/books/$id/undo").StatusCode
(Invoke-RestMethod "$API/v2/books/$id").beads[0].reviewed
(Get-ChildItem "$env:USERPROFILE\.tradurre\backups").Count
```

Expected: `200`, `False`, `2`.

The edition export, as text and as Word. `parola` is the last word of `easy.target.txt`:

```powershell
curl.exe -s -o "$RC\logs\edition.txt" "$API/v2/books/$id/export/edition?side=target&format=txt"
curl.exe -s -o "$RC\logs\edition.docx" "$API/v2/books/$id/export/edition?side=target&format=docx"
[System.IO.File]::ReadAllBytes("$RC\logs\edition.txt")[0..2] -join ' '
(Select-String -Path "$RC\logs\edition.txt" -Pattern 'parola' -Encoding UTF8).Count
uv run --no-project --python 3.14 --with python-docx python -c "import docx; print(any('parola' in p.text for p in docx.Document(r'$RC\logs\edition.docx').paragraphs))"
```

Expected: `239 187 191` (the UTF-8 byte order mark, which Notepad and Word use to read the accents right), then
`1`, then `True`.

```powershell
curl.exe -s -o NUL -w '%{http_code}' -X DELETE "$API/v2/books/$id"
curl.exe -s "$API/v2/books"
Stop-Tradurre
```

Expected: `204`, `[]`, `stopped`.

## 6. A PDF import through the API

The PDF runtime check, without a browser. Start Tradurre again; the launcher doesn't update:

```powershell
Start-Process -FilePath cmd.exe -WindowStyle Hidden `
  -ArgumentList "/c `"$RC\start-tradurre.bat --no-browser <NUL >$RC\logs\launcher-3.log 2>&1`""
Wait-Tradurre '/v2/books'
$pdf = curl.exe -s -F "source=@$RC\fixtures\easy.source.docx" -F "target=@$RC\fixtures\easy.target.pdf" -F "title=Checklist PDF" "$API/v2/books" | ConvertFrom-Json
"$($pdf.title) $($pdf.bead_count) beads, warnings: $($pdf.warnings.Count)"
curl.exe -s -o NUL -w '%{http_code}' -X DELETE "$API/v2/books/$($pdf.id)"
Stop-Tradurre
```

Expected: `True`, `Checklist PDF 28 beads, warnings: 0`, `204`, `stopped`. If the import fails, record the whole
answer: it should name the Microsoft Visual C++ Redistributable.

## 7. The launcher's failure paths

Two failures, on purpose, with a copy of the launcher that wants a newer version from a wheel that doesn't exist.
Tradurre is stopped (step 6).

```powershell
(Get-Content "$RC\start-tradurre.bat") `
  -replace '^set "VERSION=.*"$', 'set "VERSION=0.2.0rc99"' `
  -replace '^set "WHEEL_URL=.*"$', 'set "WHEEL_URL=file:///C:/tradurre-rc/missing.whl"' |
  Set-Content -Encoding ASCII "$RC\logs\launcher-test.bat"
Select-String -Path "$RC\logs\launcher-test.bat" -Pattern '^set "(VERSION|WHEEL_URL)='
```

Expected: the two changed lines, with `0.2.0rc99` and `missing.whl`.

**(a) The update fails, like when offline.** Nothing is deleted, and the installed version starts:

```powershell
Start-Process -FilePath cmd.exe -WindowStyle Hidden `
  -ArgumentList "/c `"$RC\logs\launcher-test.bat --no-browser <NUL >$RC\logs\launcher-test-a.log 2>&1`""
Wait-Tradurre '/v2/books' 300
Get-Content "$RC\logs\launcher-test-a.log" | Select-String 'Updating|Could not update|Starting the installed'
Stop-Tradurre
```

Expected: `True`; `Updating Tradurre from <VERSION> to 0.2.0rc99...`, `Could not update Tradurre (see the messages
above). ...` and `Starting the installed version instead...`; `stopped`.

**(b) The installed version is broken.** The launcher must not start it, and must say the books are safe:

```powershell
$TOOLS = uv tool dir
Rename-Item "$TOOLS\tradurre\Lib\site-packages\fastapi" 'fastapi.off'
Start-Process -FilePath cmd.exe -WindowStyle Hidden `
  -ArgumentList "/c `"$RC\logs\launcher-test.bat --no-browser <NUL >$RC\logs\launcher-test-b.log 2>&1`""
Wait-Tradurre '/v2/books' 120
Get-Content "$RC\logs\launcher-test-b.log" | Select-String 'Could not update|Tradurre could not be updated|Your books are safe'
Rename-Item "$TOOLS\tradurre\Lib\site-packages\fastapi.off" 'fastapi'
tradurre.exe --help > $null; "help exit $LASTEXITCODE"
Stop-Tradurre
```

Expected: `False` (nothing starts); `Could not update Tradurre ...`, `Tradurre could not be updated, and the version
installed before no longer` and `works. Your books are safe in ...`; `help exit 0` after the rename back;
`stopped`. **Make sure the rename back happens** even if a check fails: step 8 needs a working uv environment to
remove.

## 8. Restore the developer's setup (always)

Keep the candidate's data for the developer to inspect, and put the original data back:

```powershell
Stop-Tradurre
if (Test-Path "$env:USERPROFILE\.tradurre") { Move-Item "$env:USERPROFILE\.tradurre" "$RC\rc-data" }
if (Test-Path "$env:USERPROFILE\.tradurre.before-rc") { Rename-Item "$env:USERPROFILE\.tradurre.before-rc" '.tradurre'; 'data restored' } else { 'there was no data' }
```

Put back what step 1 found:

- **Not installed:** `uv tool uninstall tradurre`. Then `Get-Command tradurre.exe -ErrorAction SilentlyContinue`
  prints nothing. If the uninstall fails with `failed to remove directory` and os error 32, delete uv's folder
  for it and the commands it left, as the last run had to:

  ```powershell
  Remove-Item -Recurse -Force "$(uv tool dir)\tradurre"
  Get-ChildItem "$env:USERPROFILE\.local\bin\tradurre*.exe" | Remove-Item
  ```

  Delete only `tradurre*.exe` files that step 1 didn't find: in this case it found none.
- **Installed, empty `[]`** (v0.1.0): run step 2's `uv tool install` line again. Then `tradurre.exe --version`
  prints nothing, as before.
- **`tradurre X`:** check first that the release exists:
  `curl.exe -s -o NUL -w '%{http_code}' https://github.com/yamatteo/tradurre/releases/tag/vX`. If it's not `200`,
  the developer has a development install: don't guess. Record the step-1 output in the results and leave
  reinstalling to the developer. Otherwise run the following, replacing `X` with that version. Then
  `tradurre.exe --version` prints `tradurre X`.

  ```powershell
  uv tool install --force --python 3.14 "tradurre[pdf] @ https://github.com/yamatteo/tradurre/releases/download/vX/tradurre-X-py3-none-any.whl"
  ```

Expected: the output matches what step 1 recorded, and `%USERPROFILE%\.tradurre` is the developer's data again.
Say in the results which case applied.

## 9. By hand, for the developer

On the **Italian keyboard layout**: run the candidate once more. It runs without being installed, on a database of
its own in `C:\tradurre-rc\by-hand\`, so it changes neither your installed Tradurre nor your data, and there is
nothing to restore afterwards. In PowerShell, after the preamble at the top:

```powershell
$env:TRADURRE_DB = "$RC\by-hand\tradurre.db"
uvx --python 3.14 --from "tradurre[pdf] @ file:///C:/tradurre-rc/$WHEEL" tradurre
```

It opens the browser; Ctrl+C in PowerShell ends it. Afterwards run `Remove-Item Env:TRADURRE_DB`.

Import `fixtures\easy.source.docx` and `fixtures\easy.target.pdf` from the library page, then try each key on the
book screen and mark the last column.

| Key | Where | What should happen | OK? |
|---|---|---|---|
| ↑ / ↓ | book | the previous / next bead becomes current | |
| ← / → | book | the source / target side becomes current | |
| Tab / Shift+Tab | book | the next / previous sentence in the bead | |
| P / Shift+P | book | the next / previous likely problem | |
| N | book | the next unreviewed bead | |
| H | book | the shortcuts panel opens; Esc closes it | |
| R | book | the bead is marked reviewed; again: unreviewed | |
| Shift+R | book | everything up to here is marked reviewed | |
| Shift+↑ / Shift+↓ | book | the selection grows up / down | |
| Alt+↑ | book | the first sentence moves to the previous bead | |
| Alt+↓ | book | the last sentence moves to the next bead | |
| M | book | the bead merges with the next | |
| S | book, on a sentence after the first | the bead splits at that sentence | |
| X | book | the block is excluded | |
| O | book, on an edited sentence | its original appears; Esc closes it | |
| Ctrl+C / Ctrl+X / Ctrl+V | book | copy / cut the sentence, paste it into the neighbouring bead; Esc cancels a cut | |
| Enter | book | the sentence opens for editing | |
| Enter | editing | the edit is saved | |
| Esc | editing | the edit is cancelled | |
| Ctrl+Enter | editing | the sentence splits at the caret | |
| J | book | the sentence joins the next one | |
| Ctrl+Z | book | the last change is undone | |
| Ctrl+Y (also Ctrl+Shift+Z) | book | it is redone | |
| typing è, à, ì, ò, ù, é | editing | the letters appear, and no shortcut fires | |

Also check that the exported edition opens with its accents right: More → Export → target .txt in Notepad, and
target .docx in Word.
