import { test, expect, type APIRequestContext, type Page } from '@playwright/test'

// Beads after import and `restoreGap`: A (Chapitre un | Capitolo uno), B (Marie arriva. | Marie arrivò.),
// C (Il pleuvait. | ), D (Paul partit. Il ne dit rien. | Paul partì. Non disse niente.) as two beads D1, D2.
const SOURCE = 'Chapitre un\n\nMarie arriva.\n\nIl pleuvait.\n\nPaul partit. Il ne dit rien.'
const TARGET = 'Capitolo uno\n\nMarie arrivò.\n\nPaul partì. Non disse niente.'

const ORIGINAL = [
  [['Chapitre un'], ['Capitolo uno']],
  [['Marie arriva.'], ['Marie arrivò.']],
  [['Il pleuvait.'], []],
  [['Paul partit.'], ['Paul partì.']],
  [['Il ne dit rien.'], ['Non disse niente.']],
]
const B_MERGED = [
  ORIGINAL[0],
  [['Marie arriva.', 'Il pleuvait.'], ['Marie arrivò.']],
  ORIGINAL[3],
  ORIGINAL[4],
]

async function importBook(
  request: APIRequestContext, title: string, source = SOURCE, target = TARGET,
  gap = source === SOURCE && target === TARGET,
) {
  const res = await request.post('/api/v2/books', {
    multipart: {
      source: { name: 'fr.txt', mimeType: 'text/plain', buffer: Buffer.from(source) },
      target: { name: 'it.txt', mimeType: 'text/plain', buffer: Buffer.from(target) },
      title,
    },
  })
  expect(res.status()).toBe(201)
  const id: string = (await res.json()).id
  if (gap) await restoreGap(request, id)
  const book = await (await request.get(`/api/v2/books/${id}`)).json()
  return { id, book }
}

/** The two corrections that turn the imported layout into the one above: on so little text the length aligner pairs
 * "Il pleuvait." with "Paul partì." and puts both remaining source sentences in the last bead. */
async function restoreGap(request: APIRequestContext, id: string) {
  let book = await (await request.get(`/api/v2/books/${id}`)).json()
  const moved = await request.post(`/api/v2/books/${id}/beads/${book.beads[2].id}/move`, {
    data: { side: 'target', to: 'next' },
  })
  expect(moved.status()).toBe(200)
  book = await moved.json()
  const last = book.beads[3]
  const split = await request.post(`/api/v2/books/${id}/beads/${last.id}/split`, {
    data: { source_at: last.source[1].segment_id, target_at: last.target[1].segment_id },
  })
  expect(split.status()).toBe(200)
}

function current(page: Page) {
  return page.locator('[data-testid="bead-row"][data-current="true"]')
}

/** Each bead row's segment texts, [source, target]. */
function rows(page: Page) {
  return page.getByTestId('bead-row').evaluateAll((els) =>
    els.map((row) =>
      ['source', 'target'].map((side) =>
        [...row.querySelectorAll(`[data-cell="${side}"] [data-segment-id]`)].map((s) => s.textContent),
      ),
    ),
  )
}

async function open(page: Page, id: string) {
  await page.goto(`/book/${id}`)
  await expect(current(page)).toBeVisible()
}

test('Alt+↓ and Alt+↑ move a segment to the next and previous bead', async ({ page, request }) => {
  const { id } = await importBook(request, 'Move')
  await open(page, id)
  await page.keyboard.press('ArrowDown')  // B, source
  await page.keyboard.press('Alt+ArrowDown')
  await expect.poll(() => rows(page)).toEqual([
    ORIGINAL[0],
    [[], ['Marie arrivò.']],
    [['Marie arriva.', 'Il pleuvait.'], []],
    ORIGINAL[3],
    ORIGINAL[4],
  ])
  await page.keyboard.press('ArrowDown')  // C
  await page.keyboard.press('Alt+ArrowUp')
  await expect.poll(() => rows(page)).toEqual(ORIGINAL)
})

test('m merges with the next bead and s splits it back', async ({ page, request }) => {
  const { id } = await importBook(request, 'Merge')
  await open(page, id)
  await page.keyboard.press('ArrowDown')
  await page.keyboard.press('m')
  await expect.poll(() => rows(page)).toEqual(B_MERGED)
  await page.keyboard.press('Tab')
  await expect(page.locator('[data-current-segment="true"]')).toHaveText('Il pleuvait.')
  await page.keyboard.press('s')
  await expect.poll(() => rows(page)).toEqual(ORIGINAL)
  // The current bead is the new one, still on the segment split at.
  await expect(current(page)).toHaveAttribute('data-bead-id', await page.getByTestId('bead-row').nth(2).getAttribute('data-bead-id') ?? '')
  await expect(page.locator('[data-current-segment="true"]')).toHaveText('Il pleuvait.')
})

test('r toggles the reviewed mark', async ({ page, request }) => {
  const { id, book } = await importBook(request, 'Reviewed')
  await open(page, id)
  const row = page.locator(`[data-bead-id="${book.beads[0].id}"]`)
  await page.keyboard.press('r')
  await expect(row).toHaveAttribute('data-reviewed', 'true')
  await expect(page.getByTestId('book-progress')).toHaveText('Reviewed 1 / 5')
  await page.keyboard.press('r')
  await expect(row).toHaveAttribute('data-reviewed', 'false')
  await expect(page.getByTestId('book-progress')).toHaveText('Reviewed 0 / 5')
})

test('x excludes a block and Include brings it back', async ({ page, request }) => {
  const { id, book } = await importBook(request, 'Exclude')
  await open(page, id)
  await page.getByText('Il pleuvait.').click()
  await page.keyboard.press('x')
  await expect(page.getByTestId('bead-row')).toHaveCount(4)
  // C is gone: the current bead is the one now at its index (D1).
  await expect(current(page)).toHaveAttribute('data-bead-id', String(book.beads[3].id))

  await page.getByTestId('show-excluded').check()
  // The checkbox has focus, and ↓ still moves the current bead.
  await page.keyboard.press('ArrowDown')
  await expect(current(page)).toHaveAttribute('data-bead-id', String(book.beads[4].id))

  await page.getByTestId('include').click()
  await expect(page.getByTestId('excluded-row')).toHaveCount(0)
  await expect.poll(() => rows(page)).toEqual(ORIGINAL)
})

test('a refused correction shows the server message', async ({ page, request }) => {
  const { id } = await importBook(request, 'Refused')
  await open(page, id)
  for (let k = 0; k < 4; k++) await page.keyboard.press('ArrowDown')
  await page.keyboard.press('m')
  await expect(page.getByTestId('status')).toHaveText('There is no next bead to merge with')
  await expect.poll(() => rows(page)).toEqual(ORIGINAL)
})

test('undo and redo with the keyboard and the header', async ({ page, request }) => {
  // The import as it is (no `restoreGap`), so there is nothing to undo at first.
  const imported = [
    ORIGINAL[0],
    ORIGINAL[1],
    [['Il pleuvait.'], ['Paul partì.']],
    [['Paul partit.', 'Il ne dit rien.'], ['Non disse niente.']],
  ]
  const merged = [
    ORIGINAL[0],
    [['Marie arriva.', 'Il pleuvait.'], ['Marie arrivò.', 'Paul partì.']],
    imported[3],
  ]
  const { id } = await importBook(request, 'Undo', SOURCE, TARGET, false)
  await open(page, id)
  await expect.poll(() => rows(page)).toEqual(imported)
  await expect(page.getByTestId('undo')).toBeDisabled()
  await expect(page.getByTestId('redo')).toBeDisabled()
  await page.keyboard.press('ArrowDown')
  await page.keyboard.press('m')
  await expect.poll(() => rows(page)).toEqual(merged)
  await expect(page.getByTestId('undo')).toBeEnabled()

  await page.keyboard.press('Control+z')
  await expect.poll(() => rows(page)).toEqual(imported)
  await page.keyboard.press('Control+y')
  await expect.poll(() => rows(page)).toEqual(merged)
  await page.keyboard.press('Control+z')
  await expect.poll(() => rows(page)).toEqual(imported)
  await page.keyboard.press('Control+Shift+z')
  await expect.poll(() => rows(page)).toEqual(merged)
  await page.getByTestId('undo').click()
  await expect.poll(() => rows(page)).toEqual(imported)
})

test('a header button does the same as its key', async ({ page, request }) => {
  const { id } = await importBook(request, 'Button')
  await open(page, id)
  await page.getByText('Marie arriva.').click()
  await page.getByTestId('bead-actions').locator('[data-action="merge"]').click()
  await expect.poll(() => rows(page)).toEqual(B_MERGED)
})

test('selecting a row moves no other row', async ({ page, request }) => {
  const { id } = await importBook(request, 'Layout')
  await open(page, id)  // A is current
  const below = page.getByTestId('bead-row').nth(2)
  const before = (await below.boundingBox())!.y
  await page.getByText('Marie arriva.').click()  // B, the row above it
  await expect(page.getByTestId('bead-row').nth(1)).toHaveAttribute('data-current', 'true')
  expect((await below.boundingBox())!.y).toBe(before)
})

function edited(page: Page) {
  return page.locator('[data-edited="true"]')
}

test('an edited sentence is marked; o shows its original, which Restore puts back in one undo step', async ({ page, request }) => {
  const { id } = await importBook(request, 'Original')
  await open(page, id)
  await page.keyboard.press('ArrowDown')
  await page.keyboard.press('Enter')
  await page.keyboard.press('Backspace')
  await page.keyboard.type(' tard.')
  await page.keyboard.press('Enter')
  await expect(edited(page)).toHaveCount(1)
  await expect(edited(page)).toHaveText('Marie arriva tard.')
  await page.keyboard.press('o')
  await expect(page.getByTestId('original-popover')).toBeVisible()
  await expect(page.getByTestId('original-text')).toHaveText('Marie arriva.')
  await page.getByTestId('restore-original').click()
  await expect(page.getByTestId('original-popover')).toHaveCount(0)
  await expect(edited(page)).toHaveCount(0)
  await expect.poll(() => rows(page)).toEqual(ORIGINAL)
  await expect(page.getByTestId('status')).toHaveText('Original restored (Ctrl+Z to undo)')
  await page.keyboard.press('Control+z')
  await expect(edited(page)).toHaveText('Marie arriva tard.')
})

test('o on an unedited sentence says so; a move closes the popover; the More item restores', async ({ page, request }) => {
  const { id, book } = await importBook(request, 'Original keys')
  const segment = book.beads[1].source[0].segment_id
  expect((await request.post(`/api/v2/books/${id}/segments/${segment}/edit`, { data: { text: 'Marie partit.' } })).status()).toBe(200)
  await open(page, id)
  await page.keyboard.press('o')
  await expect(page.getByTestId('status')).toHaveText('This sentence is not edited')
  await expect(page.getByTestId('original-popover')).toHaveCount(0)
  await page.keyboard.press('ArrowDown')
  await page.keyboard.press('o')
  await expect(page.getByTestId('original-popover')).toBeVisible()
  await page.keyboard.press('ArrowDown')
  await expect(page.getByTestId('original-popover')).toHaveCount(0)
  await page.keyboard.press('ArrowUp')
  await page.getByTestId('more').click()
  await page.getByTestId('restore-original-more').click()
  await expect(edited(page)).toHaveCount(0)
  await expect.poll(() => rows(page)).toEqual(ORIGINAL)
})

test('an empty original is shown as such and cannot be restored', async ({ page, request }) => {
  const { id, book } = await importBook(request, 'Original empty')
  const segment = book.beads[1].source[0].segment_id
  const base = `/api/v2/books/${id}/segments/${segment}`
  expect((await request.post(`${base}/edit`, { data: { text: 'Marie arriva. Encore.' } })).status()).toBe(200)
  expect((await request.post(`${base}/split`, { data: { offset: 'Marie arriva. '.length } })).status()).toBe(200)
  await open(page, id)
  await page.getByText('Encore.').click()
  await page.keyboard.press('o')
  await expect(page.getByTestId('original-text')).toHaveText('The original of this part is empty: it was split after an edit.')
  await expect(page.getByTestId('restore-original')).toBeDisabled()
  await page.keyboard.press('Escape')
  await expect(page.getByTestId('original-popover')).toHaveCount(0)
})

function cutSpans(page: Page) {
  return page.locator('[data-cut="true"]')
}

test('Ctrl+X cuts a sentence and Ctrl+V in the previous bead moves it there, in one undo step', async ({ page, request }) => {
  const { id } = await importBook(request, 'Cut paste')
  await open(page, id)
  await page.getByText('Il pleuvait.').click()  // C, alone on its source side
  await page.keyboard.press('Control+x')
  await expect(page.getByText('Il pleuvait.')).toHaveAttribute('data-cut', 'true')
  await expect(page.getByTestId('status')).toHaveText(
    'Sentence cut: go to the previous or next bead and press Ctrl+V (Esc cancels)')
  await page.keyboard.press('ArrowUp')  // B
  await page.keyboard.press('Control+v')
  await expect.poll(() => rows(page)).toEqual(B_MERGED)
  await expect(page.getByTestId('status')).toHaveText('Sentence moved (Ctrl+Z to undo)')
  await expect(cutSpans(page)).toHaveCount(0)
  await page.keyboard.press('Control+z')
  await expect.poll(() => rows(page)).toEqual(ORIGINAL)
})

test('Ctrl+V away from the neighbouring bead is refused and Esc cancels the cut', async ({ page, request }) => {
  const { id } = await importBook(request, 'Paste refused')
  await open(page, id)
  await page.getByText('Il pleuvait.').click()
  await page.keyboard.press('Control+x')
  await page.keyboard.press('ArrowUp')
  await page.keyboard.press('ArrowUp')  // A
  await page.keyboard.press('Control+v')
  await expect(page.getByTestId('status')).toHaveText(
    'A sentence can only move to the edge of the neighbouring bead: the text order never changes')
  await expect.poll(() => rows(page)).toEqual(ORIGINAL)
  await expect(page.getByText('Il pleuvait.')).toHaveAttribute('data-cut', 'true')
  await page.keyboard.press('Escape')
  await expect(cutSpans(page)).toHaveCount(0)
})

test('Ctrl+C copies the current sentence', async ({ page, context, request }) => {
  await context.grantPermissions(['clipboard-read', 'clipboard-write'])
  const { id } = await importBook(request, 'Copy')
  await open(page, id)
  await page.getByText('Marie arriva.').click()
  await page.keyboard.press('Control+c')
  await expect(page.getByTestId('status')).toHaveText('Sentence copied')
  expect(await page.evaluate(() => navigator.clipboard.readText())).toBe('Marie arriva.')
  await expect(cutSpans(page)).toHaveCount(0)
})

test('Ctrl+X refuses a sentence in the middle of its bead', async ({ page, request }) => {
  const { id } = await importBook(request, 'Cut middle')
  await open(page, id)  // A
  await page.keyboard.press('m')
  await expect(page.getByTestId('bead-row')).toHaveCount(4)
  await page.keyboard.press('m')
  await expect(page.getByTestId('bead-row')).toHaveCount(3)
  await page.getByText('Marie arriva.').click()
  await page.keyboard.press('Control+x')
  await expect(page.getByTestId('status')).toHaveText(
    'Only the first or last sentence of a bead can move to a neighbouring bead')
  await expect(cutSpans(page)).toHaveCount(0)
})

test('inside the sentence editor cut and paste work on the text', async ({ page, context, request }) => {
  await context.grantPermissions(['clipboard-read', 'clipboard-write'])
  const { id } = await importBook(request, 'Editor cut')
  await open(page, id)
  await page.getByText('Marie arriva.').click()
  await page.keyboard.press('Enter')
  const editor = page.getByTestId('segment-editor')
  await expect(editor).toBeFocused()
  await page.keyboard.press('Control+a')
  await page.keyboard.press('Control+x')
  await expect(editor).toHaveValue('')
  await page.keyboard.press('Control+v')
  await expect(editor).toHaveValue('Marie arriva.')
  await page.keyboard.press('Enter')
  await expect(editor).toHaveCount(0)
  await expect.poll(() => rows(page)).toEqual(ORIGINAL)
  await expect(cutSpans(page)).toHaveCount(0)
})

test('the cut survives a review mark and the paste still works', async ({ page, request }) => {
  const { id } = await importBook(request, 'Cut kept')
  await open(page, id)
  await page.getByText('Il pleuvait.').click()  // C
  await page.keyboard.press('Control+x')
  await page.keyboard.press('r')
  await expect(current(page)).toHaveAttribute('data-reviewed', 'true')
  await expect(page.getByText('Il pleuvait.')).toHaveAttribute('data-cut', 'true')
  await page.keyboard.press('ArrowUp')  // B
  await page.keyboard.press('Control+v')
  await expect.poll(() => rows(page)).toEqual(B_MERGED)
  await expect(cutSpans(page)).toHaveCount(0)
})

test('the cut follows its sentence while it stays at an edge of a bead, and is dropped in the middle', async ({ page, request }) => {
  const { id } = await importBook(request, 'Cut follows')
  await open(page, id)
  await page.getByText('Marie arriva.').click()  // B
  await page.keyboard.press('Control+x')
  await page.keyboard.press('ArrowUp')  // A
  await page.keyboard.press('m')
  await expect.poll(async () => (await rows(page))[0]![0]).toEqual(['Chapitre un', 'Marie arriva.'])
  await expect(page.getByText('Marie arriva.')).toHaveAttribute('data-cut', 'true')
  await page.keyboard.press('m')  // A takes "Il pleuvait." too: "Marie arriva." is in the middle
  await expect.poll(async () => (await rows(page))[0]![0]).toEqual(['Chapitre un', 'Marie arriva.', 'Il pleuvait.'])
  await expect(cutSpans(page)).toHaveCount(0)
})

test('Ctrl+C copies text selected in the import log, not the sentence', async ({ page, context, request }) => {
  await context.grantPermissions(['clipboard-read', 'clipboard-write'])
  const { id } = await importBook(request, 'Copy log')
  await open(page, id)
  await page.getByTestId('import-log').click()
  await expect(page.getByTestId('import-stats')).toBeVisible()
  const selected = await page.getByTestId('import-stats').evaluate((el) => {
    const range = document.createRange()
    range.selectNodeContents(el)
    const selection = document.getSelection()!
    selection.removeAllRanges()
    selection.addRange(range)
    return selection.toString()
  })
  expect(selected).not.toBe('')
  await page.keyboard.press('Control+c')
  await expect.poll(() => page.evaluate(() => navigator.clipboard.readText())).toBe(selected)
  await expect(page.getByTestId('status')).not.toHaveText('Sentence copied')
})
