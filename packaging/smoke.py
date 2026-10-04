"""Browser smoke test of an installed Tradurre (PLAN.md, "Browser smoke script").

    uv run --with playwright python packaging/smoke.py --url http://127.0.0.1:8000 --channel msedge --fixtures tests/fixtures

Drives the running app in a real browser (Edge or Chrome as installed, or Playwright's own Chromium) through one
book's life: import the .docx + .pdf checklist fixtures through the form, review, correct, undo and redo across a
reload, search, export, restore the bundle, delete. Prints `PASS <step>` or `FAIL <step>: <reason>` per step and
stops at the first failure; exits 0 when every step passed, 1 otherwise. The books it creates are deleted at the
end, also after a failure, so the library is left as it was found.
"""

import argparse
import re
import secrets
import sys
from datetime import datetime
from pathlib import Path

from playwright.sync_api import Page, expect, sync_playwright

BOM = b"\xef\xbb\xbf"


class Failed(Exception):
    pass


def _rows(page: Page) -> list[list[list[str]]]:
    """Each bead row's segment texts, [source, target] (as in `frontend/e2e/book-corrections.spec.ts`)."""
    return page.get_by_test_id("bead-row").evaluate_all(
        """els => els.map(row => ['source', 'target'].map(side =>
            [...row.querySelectorAll(`[data-cell="${side}"] [data-segment-id]`)].map(s => s.textContent)))"""
    )


def _current(page: Page):
    return page.locator('[data-testid="bead-row"][data-current="true"]')


def _book_ids(page: Page, url: str) -> set[str]:
    resp = page.request.get(f"{url}/api/v2/books")
    if not resp.ok:
        raise Failed(f"GET /api/v2/books answered {resp.status}")
    return {book["id"] for book in resp.json()}


def _download(page: Page, testid: str) -> bytes:
    page.get_by_test_id("more").click()
    with page.expect_download() as info:
        page.get_by_test_id(testid).click()
    content = Path(info.value.path()).read_bytes()
    if not content:
        raise Failed(f"{testid}: the download is empty")
    return content


def run(page: Page, url: str, fixtures: Path, created: list[str]) -> None:
    title = f"Smoke {secrets.token_hex(3)}"
    word = (fixtures / "easy.target.txt").read_text(encoding="utf-8").split()[-1].strip(".")
    state: dict = {}

    def step(name, fn):
        try:
            fn()
        except Exception as e:  # an assertion, a timeout or a Failed: all end the run
            reason = str(e).strip().splitlines()[0] if str(e).strip() else type(e).__name__
            print(f"FAIL {name}: {reason}", flush=True)
            raise Failed(name) from e
        print(f"PASS {name}", flush=True)

    def library_loads():
        state["before"] = _book_ids(page, url)
        page.goto(f"{url}/")
        expect(page.get_by_role("heading", name="Library")).to_be_visible()

    def import_through_the_form():
        page.get_by_role("button", name="Import a book (txt/docx/pdf)").click()
        expect(page).to_have_url(f"{url}/book/import")
        page.get_by_label("Original (French)").set_input_files(fixtures / "easy.source.docx")
        page.get_by_label("Translation (Italian)").set_input_files(fixtures / "easy.target.pdf")
        page.get_by_label("Title").fill(title)
        page.get_by_role("button", name="Import").click()
        expect(page).to_have_url(_book_url(url), timeout=30_000)
        created.append(page.url.rsplit("/", 1)[-1])
        state["id"] = created[-1]
        expect(page.get_by_test_id("book-title")).to_have_text(title)
        expect(_current(page)).to_be_visible()
        state["count"] = page.get_by_test_id("bead-row").count()
        expect(page.get_by_test_id("book-progress")).to_have_text(f"Reviewed 0 / {state['count']}")

    def next_unreviewed_and_mark():
        rows = page.get_by_test_id("bead-row")
        first = rows.nth(0).get_attribute("data-bead-id")
        second = rows.nth(1).get_attribute("data-bead-id")
        expect(_current(page)).to_have_attribute("data-bead-id", first)
        page.keyboard.press("n")
        expect(_current(page)).to_have_attribute("data-bead-id", second)
        page.keyboard.press("r")
        expect(page.get_by_test_id("book-progress")).to_have_text(f"Reviewed 1 / {state['count']}")
        expect(rows.nth(1)).to_have_attribute("data-reviewed", "true")

    def move_and_undo():
        before = _rows(page)
        # A bead with two sentences on a side, so the move leaves both beads two-sided; the source side first.
        found = next(((k, s) for s in (0, 1) for k, row in enumerate(before) if len(row[s]) >= 2), None)
        if found is None:
            raise Failed("no bead with two sentences on a side")
        target, side = found
        rows = page.get_by_test_id("bead-row")
        ids = [rows.nth(k).get_attribute("data-bead-id") for k in range(len(before))]
        at = ids.index(_current(page).get_attribute("data-bead-id"))
        for _ in range(abs(target - at)):
            page.keyboard.press("ArrowDown" if target > at else "ArrowUp")
        expect(_current(page)).to_have_attribute("data-bead-id", ids[target])
        page.keyboard.press("ArrowLeft" if side == 0 else "ArrowRight")
        expect(_current(page)).to_have_attribute("data-side", ("source", "target")[side])
        page.keyboard.press("Alt+ArrowDown")
        _wait(page, lambda: _rows(page) != before, "Alt+↓ changed nothing")
        state["moved"] = _rows(page)
        if state["moved"][target][side] != before[target][side][:-1]:
            raise Failed("Alt+↓ didn't move the bead's last sentence")
        page.keyboard.press("Control+z")
        _wait(page, lambda: _rows(page) == before, "Ctrl+Z didn't restore the beads")

    def reload_and_redo():
        page.reload()
        expect(_current(page)).to_be_visible()
        page.keyboard.press("Control+y")
        _wait(page, lambda: _rows(page) == state["moved"], "Ctrl+Y after a reload didn't redo the move")

    def search_and_open():
        page.goto(f"{url}/search?q={word}")
        group = page.locator(f'[data-testid="result-group"][data-book-id="{state["id"]}"]')
        expect(group).to_contain_text(title)
        result = page.locator(f'[data-testid="search-result"]:has([href^="/book/{state["id"]}?"])').first
        bead = result.get_attribute("data-bead-id")
        result.get_by_test_id("result-open").click()
        expect(page).to_have_url(f"{url}/book/{state['id']}?bead={bead}")
        expect(_current(page)).to_have_attribute("data-bead-id", bead)

    def export():
        txt = _download(page, "export-target-txt")
        if not txt.startswith(BOM) or len(txt) <= len(BOM):
            raise Failed("the target .txt doesn't start with a UTF-8 BOM, or has no text")
        if not _download(page, "export-target-docx").startswith(b"PK"):
            raise Failed("the target .docx is not a zip")
        bundle = _download(page, "export-bundle")
        if not bundle.startswith(b"PK"):
            raise Failed("the bundle is not a zip")
        state["bundle"] = bundle

    def restore_bundle():
        page.goto(f"{url}/")
        expect(page.get_by_role("heading", name="Library")).to_be_visible()
        page.get_by_test_id("restore-bundle-file").set_input_files(
            {"name": f"{title}.tradurre.zip", "mimeType": "application/zip", "buffer": state["bundle"]}
        )
        expect(page).to_have_url(_book_url(url), timeout=30_000)
        restored = page.url.rsplit("/", 1)[-1]
        if restored == state["id"]:
            raise Failed("the restore opened the original book")
        created.append(restored)
        state["restored"] = restored
        today = datetime.now().date().isoformat()
        expect(page.get_by_test_id("book-title")).to_have_text(f"{title} (restored {today})")
        expect(page.get_by_test_id("bead-row")).to_have_count(state["count"])

    def delete(key):
        def fn():
            page.goto(f"{url}/")
            card = page.locator(f'[data-book-id="{state[key]}"]')
            expect(card).to_be_visible()
            page.once("dialog", lambda dialog: dialog.accept())
            card.get_by_test_id("delete-book").click()
            expect(card).to_have_count(0)
            created.remove(state[key])
        return fn

    def library_as_found():
        after = _book_ids(page, url)
        if after != state["before"]:
            raise Failed(f"{len(after)} books, {len(state['before'])} before the run")

    step("library loads", library_loads)
    step("import .docx + .pdf through the form", import_through_the_form)
    step("n moves to the next unreviewed bead, r marks it", next_unreviewed_and_mark)
    step("Alt+↓ moves a sentence, Ctrl+Z undoes it", move_and_undo)
    step("reload, Ctrl+Y redoes the move", reload_and_redo)
    step(f"search {word!r}, Open lands on the bead", search_and_open)
    step("export target .txt, .docx and the bundle", export)
    step("restore the bundle as a new book", restore_bundle)
    step("delete the restored book", delete("restored"))
    step("delete the imported book", delete("id"))
    step("the library is as it was", library_as_found)


def _book_url(url: str) -> re.Pattern:
    return re.compile(re.escape(f"{url}/book/") + r"[0-9a-f-]+$")


def _wait(page: Page, condition, message: str, timeout_ms: int = 10_000) -> None:
    waited = 0
    while not condition():
        if waited >= timeout_ms:
            raise Failed(message)
        page.wait_for_timeout(100)
        waited += 100


def main() -> int:
    # Redirected output on Windows is not UTF-8 by default, and the step names have arrows.
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Browser smoke test of an installed Tradurre.")
    parser.add_argument("--url", default="http://127.0.0.1:8000", help="the running app (default %(default)s)")
    parser.add_argument("--channel", choices=["msedge", "chrome", "chromium"], default="chromium",
                        help="the installed Edge or Chrome, or Playwright's own Chromium (default %(default)s)")
    parser.add_argument("--fixtures", type=Path, default=Path("tests/fixtures"),
                        help="the folder with easy.source.docx, easy.target.pdf and easy.target.txt")
    args = parser.parse_args()
    url = args.url.rstrip("/")
    for name in ("easy.source.docx", "easy.target.pdf", "easy.target.txt"):
        if not (args.fixtures / name).is_file():
            print(f"FAIL fixtures: {args.fixtures / name} not found", flush=True)
            return 1

    expect.set_options(timeout=15_000)
    created: list[str] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(channel=None if args.channel == "chromium" else args.channel)
        try:
            page = browser.new_context(accept_downloads=True).new_page()
            try:
                run(page, url, args.fixtures, created)
            except Failed:
                return 1
            finally:
                # After a failure: don't leave the run's books in the library.
                for book_id in created:
                    page.request.delete(f"{url}/api/v2/books/{book_id}")
                    print(f"cleanup: deleted book {book_id}", flush=True)
        finally:
            browser.close()
    print("All steps passed.", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
