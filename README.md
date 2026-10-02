# Tradurre

A local-first workbench for literary translation. You import a source text and its translation, and Tradurre
aligns them paragraph by paragraph and sentence by sentence. You then edit both sides next to each other, and
can search everything you've translated before (translation memory).

Everything runs on your own computer. Your projects are stored in a single file,
`~/.tradurre/tradurre.db` (on Windows: `C:\Users\<you>\.tradurre\tradurre.db`). To back up your work, copy
that file.

## Install

Tradurre is installed with [uv](https://docs.astral.sh/uv/), which also takes care of Python.

**1. Install uv.**

- Windows (PowerShell): `winget install astral-sh.uv`
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

On **Windows** you can skip the terminal: download `tradurre.bat` from the release, put it on your desktop,
and double-click it.

Options: `tradurre --no-browser` doesn't open a browser, `tradurre --port 8080` uses another port.

Notes:

- Text (`.txt`) files must be saved as UTF-8. In Notepad: *Save as → Encoding: UTF-8*.
- OCR glyph recovery (`ocr` extra) also needs the Tesseract program. On Windows:
  `winget install UB-Mannheim.TesseractOCR`, then add its folder to `PATH`.
- The heavy alignment pipeline (`align` extra, `tradurre-align`) needs a GPU. Run it on e.g. Google Colab and
  import the resulting JSON in your local Tradurre.

## Development

You need [uv](https://docs.astral.sh/uv/) and [Node.js](https://nodejs.org/) 22+.

```sh
git clone https://github.com/yamatteo/tradurre.git
cd tradurre
uv sync
cd frontend && npm install && cd ..

uv run tradurre --dev            # backend with auto-reload on :8000
cd frontend && npm run dev       # frontend with hot reload on :5173 (proxies /api to :8000)

uv run pytest                    # backend tests
cd frontend && npm run test:e2e  # end-to-end tests
```

`npm run build` builds the frontend into `tradurre/static/`. `uv run tradurre` (without `--dev`) serves it from
there, which is also how it ships in the wheel.

### Releasing

Bump `version` in `pyproject.toml`, commit, then tag and push:

```sh
git tag v0.2.0 && git push origin v0.2.0
```

The `Release` workflow builds the frontend, builds the wheel with the frontend inside it, and publishes a
GitHub Release with the wheel, `tradurre.bat`, and the install command.
