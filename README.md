# Tradurre

A local-first workbench for literary translation. You import a source text and its translation, and Tradurre
aligns them paragraph by paragraph and sentence by sentence. You then edit both sides next to each other, and
can search everything you've translated before (translation memory).

Everything runs on your own computer. Your projects are stored in a single file,
`~/.tradurre/tradurre.db` (on Windows: `%USERPROFILE%\.tradurre\tradurre.db`, which you can paste into the
Explorer address bar). To back up your work, copy that file.

## Install

### Windows: one-click launcher

Open the [latest release](https://github.com/yamatteo/tradurre/releases/latest), download
`start-tradurre.bat`, put it on your desktop, and double-click it. The first run installs uv and Tradurre (with
PDF support), then starts it; after that it just starts Tradurre.

Windows may warn "Windows protected your PC" because the file was downloaded: click *More info → Run anyway*.

To upgrade, download the newer release's `start-tradurre.bat` and double-click it: it notices that a different
version is installed and installs its own (close Tradurre first). Your projects are kept.

### From a terminal

Tradurre is installed with [uv](https://docs.astral.sh/uv/), which also takes care of Python.

**1. Install uv.**

- Windows (PowerShell): `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`
  (or, if you have winget: `winget install astral-sh.uv`)
- macOS / Linux: `curl -LsSf https://astral.sh/uv/install.sh | sh`

Then close and reopen the terminal.

**2. Install Tradurre.** Open the [latest release](https://github.com/yamatteo/tradurre/releases/latest) and
copy the install command from the release notes. It looks like this:

```sh
uv tool install --force "https://github.com/yamatteo/tradurre/releases/download/vX.Y.Z/tradurre-X.Y.Z-py3-none-any.whl"
```

To import PDFs, install the `pdf` extra instead:

```sh
uv tool install --force "tradurre[pdf] @ https://github.com/yamatteo/tradurre/releases/download/vX.Y.Z/tradurre-X.Y.Z-py3-none-any.whl"
```

If the terminal then says `tradurre` isn't found, run `uv tool update-shell` and open a new terminal.

To **upgrade**, run the same command with the newer release's link. Your projects are kept.

## Use

Run:

```sh
tradurre
```

Your browser opens on http://127.0.0.1:8000. Keep the terminal window open while you work; closing it (or
pressing Ctrl+C) stops Tradurre.

On **Windows** you can skip the terminal: double-click `start-tradurre.bat` (see [Install](#install)).

Options: `tradurre --no-browser` doesn't open a browser, `tradurre --port 8080` uses another port.

Notes:

- Text (`.txt`) files must be saved as UTF-8. In Notepad: *Save as → Encoding: UTF-8*.
- OCR glyph recovery (`ocr` extra) also needs the Tesseract program. On Windows, install it with
  `winget install UB-Mannheim.TesseractOCR` or the [UB Mannheim installer](https://github.com/UB-Mannheim/tesseract/wiki),
  then add `C:\Program Files\Tesseract-OCR` to your `PATH` (Start → "Edit environment variables for your
  account" → `Path` → *Edit* → *New*) and open a new terminal.
- The heavy alignment pipeline (`align` extra, `tradurre-align`) needs a GPU. Run it on e.g. Google Colab and
  import the resulting JSON in your local Tradurre.

## Backups

Each time it starts, Tradurre copies its database into `~/.tradurre/backups/` (on Windows:
`%USERPROFILE%\.tradurre\backups`), keeping the last 10 copies, named by the date and time they were taken (your
computer's clock). To go back to one, close Tradurre and copy it over `~/.tradurre/tradurre.db`. These copies are on
the same disk: to protect your work against losing the computer, also copy `tradurre.db` (or download a book's
bundle) somewhere else.

## Development

You need [Git](https://git-scm.com/), [uv](https://docs.astral.sh/uv/) and [Node.js](https://nodejs.org/) 22+.
The commands below work in any shell, including Windows PowerShell 5.1 (which doesn't support `&&`).

```sh
git clone https://github.com/yamatteo/tradurre.git
cd tradurre
uv sync
npm --prefix frontend install

uv run tradurre --dev                  # backend with auto-reload on :8000
npm --prefix frontend run dev          # frontend with hot reload on :5173 (proxies /api to :8000)

uv run pytest                          # backend tests
npm --prefix frontend run test:e2e     # end-to-end tests
```

`npm --prefix frontend run build` builds the frontend into `tradurre/static/`. `uv run tradurre` (without `--dev`) serves it from
there, which is also how it ships in the wheel.

### Releasing

Bump `version` in `pyproject.toml`, commit, then tag and push:

```sh
git tag v0.2.0
git push origin v0.2.0
```

The `Release` workflow builds the frontend, builds the wheel with the frontend inside it, and publishes a
GitHub Release with the wheel, `start-tradurre.bat` (the launcher with that release's wheel URL filled in), and
the install command.
